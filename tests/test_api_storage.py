import time
from pathlib import Path

from fastapi.testclient import TestClient

from openarm_data_collection.api import app, service
from openarm_data_collection.storage import EpisodeStore


def test_recording_creates_downloadable_episode(tmp_path: Path):
    original_store = service.store
    service.store = EpisodeStore(tmp_path)
    service.start_background()
    client = TestClient(app)
    try:
        assert client.post("/api/recording/start").status_code == 200
        live = {}
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            live = client.get("/api/live").json()
            if live.get("buffered_samples", 0) >= 1:
                break
            time.sleep(0.02)
        assert live["recording"] is True
        assert live["buffered_samples"] >= 1
        assert len(live["previews"]) == 4

        pause = client.post("/api/recording/pause").json()
        assert pause["paused"] is True
        resume = client.post("/api/recording/resume").json()
        assert resume["paused"] is False

        stopped = client.post("/api/recording/stop").json()
        assert stopped["recording"] is False
        assert stopped["sample_count"] >= 1

        episodes = client.get("/api/episodes").json()
        assert len(episodes) == 1
        episode_id = episodes[0]["episode_id"]
        assert client.get(f"/api/episodes/{episode_id}").status_code == 200
        download = client.get(f"/api/episodes/{episode_id}/download")
        assert download.status_code == 200
        assert download.content.startswith(b"\x89HDF")
    finally:
        service.stop_background()
        service.store = original_store
