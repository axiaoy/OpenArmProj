"""HDF5 episode storage backend."""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import SynchronizedSample


class EpisodeStore:
    """Store and index recorded episodes as HDF5 files.

    Parameters:
        root: Directory where episode ``.h5`` files and ``index.json`` live.
    """

    def __init__(self, root: Path | str = "data/episodes") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / "index.json"
        if not self.index_path.exists():
            self.index_path.write_text("[]\n", encoding="utf-8")

    def list_episodes(self) -> list[dict[str, Any]]:
        """List stored episode metadata.

        Returns:
            Metadata dictionaries ordered by creation time.
        """

        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def get_episode(self, episode_id: str) -> dict[str, Any]:
        """Return metadata for one episode.

        Parameters:
            episode_id: Episode identifier returned by ``write_episode``.

        Raises:
            KeyError: If no episode with that identifier exists.
        """

        for episode in self.list_episodes():
            if episode["episode_id"] == episode_id:
                return episode
        raise KeyError(episode_id)

    def episode_path(self, episode_id: str) -> Path:
        """Return the HDF5 path for an episode.

        Parameters:
            episode_id: Episode identifier returned by ``write_episode``.
        """

        return self.root / f"{episode_id}.h5"

    def write_episode(self, samples: list[SynchronizedSample], metadata: dict[str, Any]) -> dict[str, Any]:
        """Write synchronized samples to an HDF5 episode.

        Parameters:
            samples: Ordered synchronized samples to persist.
            metadata: JSON-serializable run metadata.

        Returns:
            Metadata dictionary added to the episode index.
        """

        if not samples:
            raise ValueError("cannot write an empty episode")

        import h5py
        import numpy as np

        created_at = datetime.now(timezone.utc).isoformat()
        episode_id = f"episode_{int(time.time() * 1000)}"
        path = self.episode_path(episode_id)
        joint_names = samples[0].joint_state.joint_names
        camera_names = sorted({name for sample in samples for name in sample.frames})

        with h5py.File(path, "w") as h5:
            h5.attrs["episode_id"] = episode_id
            h5.attrs["created_at"] = created_at
            h5.attrs["metadata_json"] = json.dumps(metadata)
            h5.attrs["joint_names_json"] = json.dumps(joint_names)

            joint_group = h5.create_group("joint_states")
            joint_group.create_dataset("timestamp_ns", data=np.array([s.joint_state.timestamp_ns for s in samples], dtype=np.int64))
            joint_group.create_dataset("position", data=np.array([s.joint_state.position for s in samples], dtype=np.float32))
            joint_group.create_dataset("velocity", data=np.array([s.joint_state.velocity for s in samples], dtype=np.float32))
            joint_group.create_dataset("torque", data=np.array([s.joint_state.torque for s in samples], dtype=np.float32))

            cameras_group = h5.create_group("cameras")
            for camera_name in camera_names:
                frames = [sample.frames.get(camera_name) for sample in samples]
                present_frames = [frame for frame in frames if frame is not None]
                if not present_frames:
                    continue
                first = present_frames[0]
                frame_data = np.zeros((len(samples), first.height, first.width, 3), dtype=np.uint8)
                timestamps = np.full((len(samples),), -1, dtype=np.int64)
                present = np.zeros((len(samples),), dtype=np.bool_)

                for idx, frame in enumerate(frames):
                    if frame is None:
                        continue
                    frame_data[idx] = np.array(frame.frame, dtype=np.uint8)
                    timestamps[idx] = frame.timestamp_ns
                    present[idx] = True

                group = cameras_group.create_group(camera_name)
                group.create_dataset("frame", data=frame_data, compression="gzip", compression_opts=2)
                group.create_dataset("timestamp_ns", data=timestamps)
                group.create_dataset("present", data=present)

        summary = {
            "episode_id": episode_id,
            "created_at": created_at,
            "path": str(path),
            "sample_count": len(samples),
            "joint_count": len(joint_names),
            "camera_names": camera_names,
            "metadata": metadata,
        }
        index = self.list_episodes()
        index.append(summary)
        self.index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
        return summary


def sample_to_preview(sample: SynchronizedSample) -> dict[str, Any]:
    """Convert a synchronized sample into a dashboard/API payload.

    Parameters:
        sample: Latest synchronized sample.

    Returns:
        JSON-serializable preview of joint values and camera metadata.
    """

    return {
        "joint_state": asdict(sample.joint_state),
        "frames": {
            name: {
                "timestamp_ns": frame.timestamp_ns,
                "width": frame.width,
                "height": frame.height,
                "sequence": frame.sequence,
            }
            for name, frame in sample.frames.items()
        },
        "frame_offsets_ns": dict(sample.frame_offsets_ns),
    }
