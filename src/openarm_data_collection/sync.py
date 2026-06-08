"""Timestamp alignment for joint states and camera frames."""

from __future__ import annotations

from .models import CameraFrame, JointState, SynchronizedSample


class TimestampSynchronizer:
    """Nearest-frame synchronizer around a joint-state anchor.

    Parameters:
        tolerance_ms: Maximum absolute timestamp offset allowed between a joint
            state and camera frame.
    """

    def __init__(self, tolerance_ms: float = 50.0) -> None:
        self.tolerance_ns = int(tolerance_ms * 1_000_000)

    def align(self, joint_state: JointState, latest_frames: dict[str, CameraFrame]) -> SynchronizedSample:
        """Align latest camera frames with a joint state.

        Parameters:
            joint_state: Joint sample used as the synchronization anchor.
            latest_frames: Latest known frame per camera.

        Returns:
            ``SynchronizedSample`` containing frames within tolerance.
        """

        aligned: dict[str, CameraFrame] = {}
        offsets: dict[str, int] = {}
        for name, frame in latest_frames.items():
            offset = frame.timestamp_ns - joint_state.timestamp_ns
            if abs(offset) <= self.tolerance_ns:
                aligned[name] = frame
                offsets[name] = offset
        return SynchronizedSample(joint_state=joint_state, frames=aligned, frame_offsets_ns=offsets)
