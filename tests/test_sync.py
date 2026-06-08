from openarm_data_collection.models import CameraFrame, JointState
from openarm_data_collection.sync import TimestampSynchronizer


def test_align_keeps_frames_within_tolerance():
    joint = JointState(
        timestamp_ns=1_000_000_000,
        joint_names=("j1",),
        position=(0.1,),
        velocity=(0.2,),
        torque=(0.3,),
    )
    frame = CameraFrame("wrist_left", 1_010_000_000, [[[0, 0, 0]]], 1, 1, 1)
    sample = TimestampSynchronizer(tolerance_ms=20).align(joint, {"wrist_left": frame})
    assert "wrist_left" in sample.frames
    assert sample.frame_offsets_ns["wrist_left"] == 10_000_000


def test_align_drops_frames_outside_tolerance():
    joint = JointState(
        timestamp_ns=1_000_000_000,
        joint_names=("j1",),
        position=(0.1,),
        velocity=(0.2,),
        torque=(0.3,),
    )
    frame = CameraFrame("ceiling", 1_100_000_000, [[[0, 0, 0]]], 1, 1, 1)
    sample = TimestampSynchronizer(tolerance_ms=20).align(joint, {"ceiling": frame})
    assert sample.frames == {}
    assert sample.frame_offsets_ns == {}
