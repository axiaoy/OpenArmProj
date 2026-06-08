"""Shared data models for collection, synchronization, and storage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class JointState:
    """A single robot joint-state sample.

    Parameters:
        timestamp_ns: Monotonic timestamp in nanoseconds captured near CAN decode.
        joint_names: Ordered joint names used by position, velocity, and torque.
        position: Joint positions in radians.
        velocity: Joint velocities in radians per second.
        torque: Joint torques in newton meters.
        source: Data source label, for example ``mock`` or ``socketcan``.
    """

    timestamp_ns: int
    joint_names: tuple[str, ...]
    position: tuple[float, ...]
    velocity: tuple[float, ...]
    torque: tuple[float, ...]
    source: str = "mock"


@dataclass(frozen=True)
class CameraFrame:
    """A single camera frame.

    Parameters:
        camera_name: Stable camera identifier.
        timestamp_ns: Monotonic timestamp captured at frame acquisition.
        frame: RGB image array as ``height x width x 3`` nested lists.
        width: Frame width in pixels.
        height: Frame height in pixels.
        sequence: Per-camera frame counter.
    """

    camera_name: str
    timestamp_ns: int
    frame: list[list[list[int]]]
    width: int
    height: int
    sequence: int


@dataclass(frozen=True)
class SynchronizedSample:
    """A joint sample with nearest camera frames.

    Parameters:
        joint_state: Joint sample used as the alignment anchor.
        frames: Mapping from camera name to aligned camera frame.
        frame_offsets_ns: Mapping from camera name to ``frame_ts - joint_ts``.
    """

    joint_state: JointState
    frames: Mapping[str, CameraFrame]
    frame_offsets_ns: Mapping[str, int] = field(default_factory=dict)
