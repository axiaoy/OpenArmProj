"""Background sampling and recording orchestration."""

from __future__ import annotations

import base64
import threading
import time
from typing import Any

from .cameras import MockMultiCameraSystem
from .can import JointStateProvider, MockCANJointStateProvider
from .models import CameraFrame, SynchronizedSample
from .storage import EpisodeStore, sample_to_preview
from .sync import TimestampSynchronizer


class DataCollectionService:
    """Coordinates CAN, cameras, synchronization, recording, and storage.

    Parameters:
        joint_provider: Provider used to read joint states.
        camera_system: Multi-camera source used to poll latest frames.
        store: Episode storage backend.
        synchronizer: Timestamp alignment policy.
    """

    def __init__(
        self,
        joint_provider: JointStateProvider | None = None,
        camera_system: MockMultiCameraSystem | None = None,
        store: EpisodeStore | None = None,
        synchronizer: TimestampSynchronizer | None = None,
    ) -> None:
        self.joint_provider = joint_provider or MockCANJointStateProvider()
        self.camera_system = camera_system or MockMultiCameraSystem()
        self.store = store or EpisodeStore()
        self.synchronizer = synchronizer or TimestampSynchronizer()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._latest: SynchronizedSample | None = None
        self._recording_samples: list[SynchronizedSample] = []
        self._recording_started_ns: int | None = None
        self._is_recording = False
        self._is_paused = False
        self._pause_started_ns: int | None = None
        self._paused_duration_ns = 0

    def start_background(self) -> None:
        """Start the sampler thread if it is not already running."""

        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="openarm-sampler", daemon=True)
        self._thread.start()

    def stop_background(self) -> None:
        """Stop the sampler thread and wait briefly for shutdown."""

        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def start_recording(self) -> dict[str, Any]:
        """Begin buffering synchronized samples for a new episode.

        Returns:
            Recording state summary.
        """

        with self._lock:
            self._recording_samples = []
            self._recording_started_ns = time.monotonic_ns()
            self._is_recording = True
            self._is_paused = False
            self._pause_started_ns = None
            self._paused_duration_ns = 0
            return {"recording": True, "paused": False, "started_ns": self._recording_started_ns}

    def pause_recording(self) -> dict[str, Any]:
        """Pause appending samples to the active recording.

        Returns:
            Recording state summary. Calling pause when no recording is active
            leaves the service idle and returns the current state.
        """

        with self._lock:
            if not self._is_recording:
                return {"recording": False, "paused": False}
            if not self._is_paused:
                self._is_paused = True
                self._pause_started_ns = time.monotonic_ns()
            return {"recording": True, "paused": True, "buffered_samples": len(self._recording_samples)}

    def resume_recording(self) -> dict[str, Any]:
        """Resume appending samples to the active recording.

        Returns:
            Recording state summary including current buffered sample count.
        """

        with self._lock:
            if not self._is_recording:
                return {"recording": False, "paused": False}
            if self._is_paused:
                now_ns = time.monotonic_ns()
                if self._pause_started_ns is not None:
                    self._paused_duration_ns += now_ns - self._pause_started_ns
                self._pause_started_ns = None
                self._is_paused = False
            return {"recording": True, "paused": False, "buffered_samples": len(self._recording_samples)}

    def stop_recording(self) -> dict[str, Any]:
        """Stop recording and persist the buffered episode.

        Returns:
            Episode metadata summary. If no samples were captured, returns a
            non-persisted summary with ``sample_count`` zero.
        """

        with self._lock:
            samples = list(self._recording_samples)
            started_ns = self._recording_started_ns
            self._recording_samples = []
            self._recording_started_ns = None
            self._is_recording = False
            if self._is_paused and self._pause_started_ns is not None:
                self._paused_duration_ns += time.monotonic_ns() - self._pause_started_ns
            paused_duration_ns = self._paused_duration_ns
            self._is_paused = False
            self._pause_started_ns = None
            self._paused_duration_ns = 0

        if not samples:
            return {"recording": False, "paused": False, "sample_count": 0, "episode": None}

        metadata = {
            "simulated": True,
            "can_interfaces": ["can0", "can1"],
            "camera_names": ["wrist_left", "wrist_right", "ceiling", "zed_stereo"],
            "started_ns": started_ns,
            "ended_ns": time.monotonic_ns(),
            "paused_duration_ns": paused_duration_ns,
            "sync_tolerance_ms": self.synchronizer.tolerance_ns / 1_000_000,
        }
        episode = self.store.write_episode(samples, metadata)
        return {"recording": False, "paused": False, "sample_count": len(samples), "episode": episode}

    def live_payload(self) -> dict[str, Any]:
        """Return the latest dashboard/API state.

        Returns:
            JSON-serializable state containing joint values, per-camera previews,
            recording status, pause status, and episode count.
        """

        with self._lock:
            latest = self._latest
            recording = self._is_recording
            paused = self._is_paused
            buffered = len(self._recording_samples)

        payload: dict[str, Any] = {
            "recording": recording,
            "paused": paused,
            "buffered_samples": buffered,
            "episode_count": len(self.store.list_episodes()),
            "mode": "simulated",
        }
        if latest:
            payload.update(sample_to_preview(latest))
            payload["previews"] = {
                name: frame_to_bmp_data_url(frame)
                for name, frame in latest.frames.items()
            }
        return payload

    def _run(self) -> None:
        while not self._stop.is_set():
            joint_state = self.joint_provider.read()
            frames = self.camera_system.poll()
            sample = self.synchronizer.align(joint_state, frames)
            with self._lock:
                self._latest = sample
                if self._is_recording and not self._is_paused:
                    self._recording_samples.append(sample)


def frame_to_bmp_data_url(frame: CameraFrame) -> str:
    """Encode an RGB frame as a browser-displayable BMP data URL.

    Parameters:
        frame: RGB frame to encode.

    Returns:
        ``data:image/bmp;base64,...`` URL for dashboard preview.
    """

    width = frame.width
    height = frame.height
    row_size = (width * 3 + 3) & ~3
    pixel_size = row_size * height
    file_size = 54 + pixel_size
    header = bytearray()
    header.extend(b"BM")
    header.extend(file_size.to_bytes(4, "little"))
    header.extend((0).to_bytes(4, "little"))
    header.extend((54).to_bytes(4, "little"))
    header.extend((40).to_bytes(4, "little"))
    header.extend(width.to_bytes(4, "little", signed=True))
    header.extend(height.to_bytes(4, "little", signed=True))
    header.extend((1).to_bytes(2, "little"))
    header.extend((24).to_bytes(2, "little"))
    header.extend((0).to_bytes(4, "little"))
    header.extend(pixel_size.to_bytes(4, "little"))
    header.extend((2835).to_bytes(4, "little", signed=True))
    header.extend((2835).to_bytes(4, "little", signed=True))
    header.extend((0).to_bytes(4, "little"))
    header.extend((0).to_bytes(4, "little"))

    body = bytearray()
    padding = b"\x00" * (row_size - width * 3)
    for row in reversed(frame.frame):
        for pixel in row:
            red, green, blue = pixel
            body.extend(bytes((blue, green, red)))
        body.extend(padding)
    encoded = base64.b64encode(header + body).decode("ascii")
    return f"data:image/bmp;base64,{encoded}"
