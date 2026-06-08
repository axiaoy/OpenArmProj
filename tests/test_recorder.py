import time
from pathlib import Path

from openarm_data_collection.recorder import DataCollectionService, frame_to_bmp_data_url
from openarm_data_collection.storage import EpisodeStore


def wait_for_buffer(service: DataCollectionService, minimum: int, timeout_s: float = 1.0) -> int:
    deadline = time.monotonic() + timeout_s
    latest = 0
    while time.monotonic() < deadline:
        latest = service.live_payload().get("buffered_samples", 0)
        if latest >= minimum:
            return latest
        time.sleep(0.02)
    return latest


def test_live_payload_has_all_four_camera_previews(tmp_path: Path):
    service = DataCollectionService(store=EpisodeStore(tmp_path))
    service.start_background()
    try:
        deadline = time.monotonic() + 1.0
        payload = {}
        while time.monotonic() < deadline:
            payload = service.live_payload()
            if len(payload.get("previews", {})) == 4:
                break
            time.sleep(0.02)
        assert set(payload["previews"]) == {"wrist_left", "wrist_right", "ceiling", "zed_stereo"}
        assert all(value.startswith("data:image/bmp;base64,") for value in payload["previews"].values())
    finally:
        service.stop_background()


def test_pause_prevents_buffer_growth_then_resume_continues(tmp_path: Path):
    service = DataCollectionService(store=EpisodeStore(tmp_path))
    service.start_background()
    try:
        assert service.start_recording()["recording"] is True
        before_pause = wait_for_buffer(service, minimum=2)
        assert before_pause >= 2

        paused = service.pause_recording()
        assert paused["recording"] is True
        assert paused["paused"] is True
        paused_count = paused["buffered_samples"]
        time.sleep(0.12)
        assert service.live_payload()["buffered_samples"] <= paused_count + 1

        resumed = service.resume_recording()
        assert resumed["recording"] is True
        assert resumed["paused"] is False
        after_resume = wait_for_buffer(service, minimum=paused_count + 2)
        assert after_resume >= paused_count + 2
    finally:
        service.stop_recording()
        service.stop_background()


def test_bmp_preview_encoder_has_data_url_prefix():
    from openarm_data_collection.models import CameraFrame

    frame = CameraFrame("test", 1, [[[255, 0, 0]]], 1, 1, 1)
    assert frame_to_bmp_data_url(frame).startswith("data:image/bmp;base64,")
