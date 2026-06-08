"""FastAPI application for OpenArm data collection."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .recorder import DataCollectionService

STATIC_DIR = Path(__file__).parent / "static"
service = DataCollectionService()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Start and stop background simulated sampling with the API process."""

    service.start_background()
    try:
        yield
    finally:
        service.stop_background()


app = FastAPI(title="OpenArm 2.0 Data Collection API", version="0.1.0", lifespan=lifespan)


@app.get("/api/live")
def get_live() -> dict:
    """Return latest joint, camera, recording, and episode-count state."""

    return service.live_payload()


@app.post("/api/recording/start")
def start_recording() -> dict:
    """Start collecting samples for a new episode."""

    return service.start_recording()


@app.post("/api/recording/pause")
def pause_recording() -> dict:
    """Pause appending samples to the active episode."""

    return service.pause_recording()


@app.post("/api/recording/resume")
def resume_recording() -> dict:
    """Resume appending samples to the active episode."""

    return service.resume_recording()


@app.post("/api/recording/stop")
def stop_recording() -> dict:
    """Stop recording and persist the episode if samples were captured."""

    return service.stop_recording()


@app.get("/api/episodes")
def list_episodes() -> list[dict]:
    """List recorded episode metadata."""

    return service.store.list_episodes()


@app.get("/api/episodes/{episode_id}")
def get_episode(episode_id: str) -> dict:
    """Return metadata for one recorded episode.

    Parameters:
        episode_id: Episode identifier from ``GET /api/episodes``.
    """

    try:
        return service.store.get_episode(episode_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="episode not found") from exc


@app.get("/api/episodes/{episode_id}/download")
def download_episode(episode_id: str) -> FileResponse:
    """Download one episode HDF5 file.

    Parameters:
        episode_id: Episode identifier from ``GET /api/episodes``.
    """

    try:
        service.store.get_episode(episode_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="episode not found") from exc
    path = service.store.episode_path(episode_id)
    return FileResponse(path, media_type="application/x-hdf5", filename=path.name)


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
