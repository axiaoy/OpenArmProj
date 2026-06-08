# OpenArm 2.0 Data Collection Pipeline

A simulated data collection platform for OpenArm 2.0 teleoperation demonstrations. The project is structured around the same interfaces that would be used on hardware: CAN FD joint-state providers, multi-camera frame providers, timestamp synchronization, episode storage, a REST backend, and an operator dashboard.

The implementation is runnable without robot hardware. Hardware-specific behavior is isolated behind adapter boundaries and clearly marked as simulated in episode metadata.

## Completed Scope

| Area | Status | Notes |
| --- | --- | --- |
| CAN setup | Simulated | Command sequence follows the OpenArm 2.0 setup flow; hardware verification steps are documented below. |
| CAN data reading | Simulated | Generates 16 OpenArm-like joints with position, velocity, and torque at a nominal 100 Hz. |
| Multi-camera sync | Simulated | Four independent camera streams: wrist left, wrist right, ceiling, and ZED stereo. |
| Storage backend | Implemented | HDF5 episodes with joint arrays, camera tensors, timestamps, presence masks, and metadata. |
| REST API | Implemented | Live state, recording controls, pause/resume, episode listing, metadata, and HDF5 downloads. |
| Monitoring dashboard | Implemented | Four camera previews, live joint state, rolling telemetry plots, recording controls, and download links. |
| Unit tests | Implemented | CLI, synchronization, recorder behavior, API/storage, downloads, pause/resume, and camera previews. |

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn openarm_data_collection.api:app --reload --host 127.0.0.1 --port 8000
```

Dashboard:

```text
http://127.0.0.1:8000
```

Tests:

```bash
pytest
```

## Task 1: CAN Interface Setup

Task 1 is simulated in this submission because no OpenArm hardware is attached. The setup command still mirrors the OpenArm 2.0 flow so the same wrapper can be used on the robot.

Dry-run artifact:

```bash
python -m openarm_data_collection.cli setup-can --dry-run
```

Expected output:

```text
+ openarm-can-cli can_configure
+ ip link show can0
+ ip link show can1
+ openarm-can-cli -i can0 set_zero --arm
+ openarm-can-cli -i can1 set_zero --arm
```

Hardware command sequence:

```bash
openarm-can-cli can_configure
ip link show can0
ip link show can1
openarm-can-cli -i can0 set_zero --arm
openarm-can-cli -i can1 set_zero --arm
```

### Hardware Verification Artifact

On a robot machine, the verification artifact should show three facts:

1. `can0` is present and `UP`.
2. `can1` is present and `UP`.
3. `set_zero --arm` completed for both interfaces.

A terminal-output artifact can be captured with:

```bash
python -m openarm_data_collection.cli setup-can | tee openarm_can_setup_output.txt
```

A screenshot artifact should show the same terminal output: `ip link show can0`, `ip link show can1`, both interfaces in `UP` state, and both zero-position commands. This repository does not include a real hardware screenshot because the run was performed without attached OpenArm hardware.

## System Architecture

```text
CAN provider       Camera providers
     |                   |
     v                   v
 JointState       CameraFrame streams
     \                 /
      \               /
       TimestampSynchronizer
                |
                v
      DataCollectionService
       |        |        |
       v        v        v
     HDF5     REST     Dashboard
```

Main modules:

- `can.py`: `JointStateProvider`, deterministic mock stream, and `SocketCANJointStateProvider` hardware boundary.
- `cameras.py`: camera provider abstraction and four-camera simulator.
- `sync.py`: timestamp tolerance and frame alignment.
- `recorder.py`: background sampler, recording state, pause/resume, and live preview payloads.
- `storage.py`: HDF5 episode writer and metadata index.
- `api.py`: FastAPI routes for live state, controls, episode metadata, and downloads.
- `static/`: operator dashboard with camera previews and rolling telemetry plots.

## Hardware And Embedded Considerations

The CAN setup wrapper uses `openarm-can-cli can_configure` rather than hand-writing `ip link set ... type can bitrate ...` commands directly. The reason is that `can_configure` is the documented single entry-point in the OpenArm 2.0 setup guide and encapsulates the correct CAN FD bitrate (5 Mbps data-phase), sample-point tuning, and hardware-specific flags for the arm's motor controllers. Writing these by hand risks subtle misconfiguration — for example, setting the wrong data-phase bitrate or omitting `fd on` — which would cause the Damiao motors to silently drop frames rather than error loudly.

The mock CAN provider emits joint states through the same `JointStateProvider.read()` contract expected from a real adapter:

```text
timestamp_ns, joint_names, position[], velocity[], torque[], source
```

The real hardware path belongs in `SocketCANJointStateProvider`. CAN FD frame parsing is intentionally left as a placeholder rather than guessed from the DaMiao protocol documentation. The reason is that the OpenArm 2.0 `openarm_can` C++ library handles motor-ID mapping, MIT-mode fixed-point decoding, and error-frame filtering in ways that are difficult to replicate correctly without running against real hardware. Shipping plausible-looking but unverified frame parsing would make bugs harder to find during hardware bring-up — the deliberate gap makes the boundary obvious.

Real-time awareness in the current design:

- Sampling runs in a background thread separate from request handling so that slow HTTP clients cannot cause joint-state samples to be dropped.
- Timestamps are captured with `time.monotonic_ns()` at the moment of acquisition, not at the moment of serialisation — this matters because serialisation can be deferred by GIL contention or I/O scheduling.
- Camera alignment has an explicit tolerance window so that a delayed frame is recorded as absent rather than silently misaligned with the wrong joint state.
- Pause stops episode writes without stopping live monitoring, preserving operator situational awareness during breaks in a teleoperation session.
- The dashboard reports buffered sample count and estimated joint update rate so the operator can detect a CAN drop-out before starting a valuable demonstration.

## Data Pipeline

### Timestamping Strategy

`time.monotonic_ns()` is used for all alignment rather than `time.time()` or `datetime.now()`. The reason is that wall-clock time is subject to NTP steps and leap-second corrections, both of which can cause timestamps to go backwards or jump forward by tens of milliseconds. For a 100 Hz joint stream, a 10 ms NTP correction is a full sample period — it would corrupt the ordering of any data logged across that boundary. Monotonic time is guaranteed to never go backwards within a process lifetime, making it safe to use as the sort key for episode reconstruction and camera alignment.

UTC wall-clock time is stored only as human-readable metadata on the episode, not as the alignment key.

### Synchronization Strategy

Joint state is used as the anchor stream rather than a separate wall-clock heartbeat. The reason is that joint state is the highest-rate and most latency-sensitive signal in the system — it is the ground truth for what the arm was doing. Anchoring on it means every stored sample is guaranteed to have a valid joint observation; camera frames are the ones that may be absent, which is the correct trade-off for a robot learning dataset.

Each camera keeps its most recently acquired frame. At each joint tick the synchronizer includes a camera frame only when its timestamp falls within the configured tolerance (default 50 ms). When a frame is too old, the episode records it as absent via a `present` mask rather than interpolating or repeating the last frame. This is important for training: a policy that sees a repeated frame looks at stale visual information but does not know it is stale. An absent mask tells the training code to handle the gap explicitly.

The 50 ms tolerance is wide enough to accommodate the lowest-rate camera (ceiling at 15 FPS = 67 ms period) while still being tight enough to reject frames that are more than one period old. On real hardware this window should be tuned based on measured inter-frame jitter rather than the nominal rate.

Camera frame rates in the simulator:

- wrist left: 30 FPS
- wrist right: 30 FPS
- ceiling: 15 FPS
- ZED stereo: 20 FPS
- joints: nominal 100 Hz

### Storage Format: HDF5

HDF5 was chosen over MCAP, zarr, and raw file-per-frame layouts for three concrete reasons.

**Training read access.** Robot learning training loops read episodes as dense arrays — position over the whole episode, images as a tensor stack. HDF5 stores these natively as chunked, compressed datasets that can be sliced with a single library call. MCAP requires deserialising a message stream and reassembling arrays in Python, which adds CPU cost and code complexity for what is the dominant access pattern.

**Single-file portability.** Each episode is one `.h5` file containing joint arrays, camera tensors, timestamps, presence masks, and metadata. This makes episodes trivially copyable, hashable, and inspectable with standard tools (`h5dump`, `h5ls`, the HDF5 VSCode extension). A zarr episode is a directory tree, which is awkward to move between machines and error-prone to partially-copy.

**Incremental writes without pre-allocation.** HDF5 datasets with `maxshape=None` and `resize()` support appending samples without knowing the episode length in advance. This means recording can be stopped at any point — including on a crash — and the file will contain all samples written up to that moment. A raw numpy `.npy` file requires pre-allocating the full array or rewriting the file on close.

The main trade-off is that HDF5 is a poor fit for concurrent multi-writer access or cloud-native object-store workflows. If the platform scales to multiple simultaneous collection stations writing to shared storage, MCAP (which is append-only by design) or zarr (which supports object-store backends like S3) would be the right migration target. For a single-station local collection workflow, HDF5's simplicity and training-loop compatibility outweigh those concerns.

Episode layout:

```text
/joint_states/timestamp_ns
/joint_states/position
/joint_states/velocity
/joint_states/torque
/cameras/{camera_name}/timestamp_ns
/cameras/{camera_name}/present
/cameras/{camera_name}/frame
/metadata attrs
```

## Backend API

The API surface is intentionally small. Each route maps to one operator action or one data access pattern, with no routes that combine multiple concerns.

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/live` | Live joints, cameras, previews, recording state, and counts. |
| `POST` | `/api/recording/start` | Start buffering a new episode. |
| `POST` | `/api/recording/pause` | Pause appending samples while live monitoring continues. |
| `POST` | `/api/recording/resume` | Resume appending samples. |
| `POST` | `/api/recording/stop` | Stop recording and persist an HDF5 episode. |
| `GET` | `/api/episodes` | List episode metadata. |
| `GET` | `/api/episodes/{episode_id}` | Fetch one episode's metadata. |
| `GET` | `/api/episodes/{episode_id}/download` | Download the HDF5 file. |

Pause and resume are separate routes from stop rather than parameters on a single route. The reason is that they have different side effects: pause preserves the in-progress episode buffer so the operator can resume without losing the samples already collected, while stop finalises and persists the file. Collapsing them into one route with a `state` parameter would make it easy to accidentally discard an in-progress episode by sending the wrong value.

Error handling is explicit for missing episodes: metadata and download routes return `404` when an unknown `episode_id` is requested. Empty recordings return a structured response with `sample_count: 0` instead of writing a zero-row HDF5 file, because zero-row datasets cause silent failures in some numpy and h5py slice operations during training.

Collected data can be fetched from the dashboard's Download button or directly:

```bash
curl http://127.0.0.1:8000/api/episodes
curl -o episode.h5 http://127.0.0.1:8000/api/episodes/{episode_id}/download
```

## Frontend Dashboard

The dashboard is built as an operator console rather than a monitoring page. The distinction matters for how controls are laid out: the operator is performing a repetitive collect → review → collect workflow, so recording controls, live camera previews, and episode status are all visible simultaneously without requiring navigation between views.

Four camera previews are shown simultaneously rather than a single switchable view. The reason is that teleoperation demonstrations frequently have the wrist cameras partially occluded or pointing away from the object of interest. An operator who can only see one camera at a time will miss occlusion events that corrupt a demonstration. Showing all four cameras means the operator can abort and re-collect before saving an episode where a critical view was blocked.

Rolling plots show position, velocity, torque, and camera timestamp offsets rather than only the current value. Current values tell the operator the arm's state right now; rolling plots tell them whether the arm has been moving smoothly or whether there have been velocity spikes, torque limits, or camera frame drops in the last few seconds. The latter is much more useful for deciding whether a demonstration is worth keeping.

Camera DOM nodes are created once and updated in place, and plots are drawn with browser-native canvas. This avoids pulling in a charting library, which matters because the dashboard runs on the robot's onboard computer alongside the CAN reader, camera capture, and the API server. A heavy frontend dependency would compete for CPU and memory on a machine that already has a demanding real-time workload.

## Unit Test Coverage

Unit tests are included under `tests/`:

- `test_cli.py`: simulated CAN setup command sequence.
- `test_sync.py`: timestamp tolerance and frame dropping behavior.
- `test_api_storage.py`: recording flow, pause/resume endpoints, HDF5 persistence, metadata retrieval, and downloads.
- `test_recorder.py`: four-camera preview payloads, pause/resume buffering behavior, and preview encoding.

Current verification:

```text
7 passed
```

## Known Limitations

- **CAN FD frame decoding is unverified on real hardware.** The `SocketCANJointStateProvider` placeholder is intentional — guessing the DaMiao frame schema without hardware to test against would produce code that looks correct but fails silently during bring-up.
- **Camera capture is software-generated.** Real Arducam and ZED providers would need the respective SDKs. The provider interface is designed to accept them as drop-in replacements.
- **No authentication model.** In a lab with multiple operators, episode ownership and operator identity in metadata would be the first addition.
- **No calibration metadata in episodes.** Extrinsic camera calibration and robot URDF version should be stored per-episode so that a dataset collected across a robot reconfiguration remains usable.
- **Canvas plots, not a full observability stack.** For production data collection, Grafana or a similar tool with persistent telemetry history would catch issues (intermittent CAN drop-outs, camera degradation) that only appear over many sessions.

## Next Steps

Given hardware access, the next engineering steps in priority order would be:

1. **Implement `SocketCANJointStateProvider.read()`** using the OpenArm CAN bindings. This is the single highest-leverage step because all other hardware work depends on having verified joint state.
2. **Add Arducam and ZED SDK camera providers** behind the existing `CameraProvider` interface.
3. **Tune the synchronization tolerance window** based on measured inter-frame jitter rather than nominal rates, and add a per-camera jitter histogram to the dashboard.
4. **Store calibration metadata per episode**: extrinsic camera calibration, URDF hash, and operator/session ID.
5. **Add operational telemetry**: dropped-frame counters, CAN receive latency histograms, and disk-space alerts surfaced on the dashboard.
6. **Add a replay and inspection tool** for recorded HDF5 episodes so operators can review demonstrations before committing them to a training dataset.
7. **Evaluate MCAP or zarr** if the collection workflow scales to multiple simultaneous stations or cloud-based dataset storage.# OpenArmProj
# OpenArmProj
# OpenArmProj
# OpenArmProj
