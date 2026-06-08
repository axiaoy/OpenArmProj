"""Camera providers and four-camera simulation for OpenArm collection."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

from .models import CameraFrame


class CameraProvider(ABC):
    """Interface for camera frame acquisition."""

    @abstractmethod
    def capture(self) -> CameraFrame | None:
        """Capture or return the latest available frame.

        Returns:
            A ``CameraFrame`` when a new frame is available, otherwise ``None``.
        """


class MockCamera(CameraProvider):
    """Small RGB camera simulator with independent frame rate.

    Parameters:
        name: Stable camera identifier.
        fps: Simulated frame rate.
        width: Frame width in pixels.
        height: Frame height in pixels.
        color_seed: Integer used to create distinct color patterns.
    """

    def __init__(self, name: str, fps: float, width: int = 64, height: int = 48, color_seed: int = 0) -> None:
        self.name = name
        self.period_ns = int(1_000_000_000 / fps)
        self.width = width
        self.height = height
        self.color_seed = color_seed
        self._last_frame_ns = 0
        self._sequence = 0

    def capture(self) -> CameraFrame | None:
        """Return a new synthetic RGB frame if the camera period elapsed."""

        now_ns = time.monotonic_ns()
        if self._last_frame_ns and now_ns - self._last_frame_ns < self.period_ns:
            return None

        self._last_frame_ns = now_ns
        self._sequence += 1
        return CameraFrame(
            camera_name=self.name,
            timestamp_ns=now_ns,
            frame=self._make_frame(self._sequence),
            width=self.width,
            height=self.height,
            sequence=self._sequence,
        )

    def _make_frame(self, sequence: int) -> list[list[list[int]]]:
        frame: list[list[list[int]]] = []
        for y in range(self.height):
            row: list[list[int]] = []
            for x in range(self.width):
                row.append(
                    [
                        (x * 3 + sequence * 5 + self.color_seed) % 256,
                        (y * 4 + sequence * 3 + self.color_seed * 2) % 256,
                        ((x + y) * 2 + sequence * 7 + self.color_seed * 3) % 256,
                    ]
                )
            frame.append(row)
        return frame


class MockMultiCameraSystem:
    """Four-camera OpenArm simulator.

    Parameters:
        cameras: Optional camera providers. If omitted, creates wrist left,
            wrist right, ceiling, and ZED stereo simulators.
    """

    def __init__(self, cameras: tuple[CameraProvider, ...] | None = None) -> None:
        self.cameras = cameras or (
            MockCamera("wrist_left", fps=30, color_seed=10),
            MockCamera("wrist_right", fps=30, color_seed=70),
            MockCamera("ceiling", fps=15, color_seed=130),
            MockCamera("zed_stereo", fps=20, width=80, height=48, color_seed=190),
        )
        self.latest: dict[str, CameraFrame] = {}

    def poll(self) -> dict[str, CameraFrame]:
        """Poll all cameras and update the latest-frame cache.

        Returns:
            Mapping of camera name to latest frame.
        """

        for camera in self.cameras:
            frame = camera.capture()
            if frame is not None:
                self.latest[frame.camera_name] = frame
        return dict(self.latest)
