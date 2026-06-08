const recordButton = document.getElementById("recordButton");
const pauseButton = document.getElementById("pauseButton");
const recordingState = document.getElementById("recordingState");
const episodeCount = document.getElementById("episodeCount");
const bufferedCount = document.getElementById("bufferedCount");
const cameraCount = document.getElementById("cameraCount");
const sampleAge = document.getElementById("sampleAge");
const cameraGrid = document.getElementById("cameraGrid");
const joints = document.getElementById("joints");
const cameraMeta = document.getElementById("cameraMeta");
const sampleMeta = document.getElementById("sampleMeta");
const telemetryMeta = document.getElementById("telemetryMeta");
const episodeMeta = document.getElementById("episodeMeta");
const episodes = document.getElementById("episodes");
const mode = document.getElementById("mode");

const cameraNames = ["wrist_left", "wrist_right", "ceiling", "zed_stereo"];
const chartColors = ["#126b53", "#327c92", "#8a641f", "#b23434"];
const historyLimit = 160;
const history = {
  position: [],
  velocity: [],
  torque: [],
  offset: [],
};
const charts = {
  position: document.getElementById("positionChart"),
  velocity: document.getElementById("velocityChart"),
  torque: document.getElementById("torqueChart"),
  offset: document.getElementById("offsetChart"),
};
const cameraTiles = new Map();

let recording = false;
let paused = false;
let lastEpisodeCount = -1;
let lastJointTimestampNs = null;

async function postJson(url) {
  const response = await fetch(url, { method: "POST" });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function initializeCameraTiles() {
  cameraNames.forEach((name) => {
    const tile = document.createElement("div");
    tile.className = "camera-tile";
    const img = document.createElement("img");
    img.alt = `${name} preview`;
    const title = document.createElement("strong");
    title.textContent = name;
    const meta = document.createElement("span");
    meta.textContent = "waiting";
    tile.append(img, title, meta);
    cameraGrid.appendChild(tile);
    cameraTiles.set(name, { img, meta });
  });
}

recordButton.addEventListener("click", async () => {
  recordButton.disabled = true;
  pauseButton.disabled = true;
  try {
    await postJson(recording ? "/api/recording/stop" : "/api/recording/start");
    await refresh(true);
  } finally {
    recordButton.disabled = false;
  }
});

pauseButton.addEventListener("click", async () => {
  pauseButton.disabled = true;
  try {
    await postJson(paused ? "/api/recording/resume" : "/api/recording/pause");
    await refresh();
  } finally {
    pauseButton.disabled = !recording;
  }
});

function renderJoints(jointState) {
  if (!jointState) return;
  joints.innerHTML = "";
  jointState.joint_names.forEach((name, index) => {
    const position = jointState.position[index];
    const velocity = jointState.velocity[index];
    const torque = jointState.torque[index];
    const normalized = Math.max(0, Math.min(100, 50 + position * 40));
    const item = document.createElement("div");
    item.className = "joint";
    item.innerHTML = `
      <div class="joint-name"><span>${name}</span><span>${position.toFixed(3)} rad</span></div>
      <div class="bar"><span style="width: ${normalized}%"></span></div>
      <p>${velocity.toFixed(3)} rad/s / ${torque.toFixed(3)} Nm</p>
    `;
    joints.appendChild(item);
  });
}

function renderCameras(frames, previews) {
  cameraNames.forEach((name) => {
    const tile = cameraTiles.get(name);
    const frame = frames[name];
    if (!tile) return;
    if (previews[name] && tile.img.src !== previews[name]) {
      tile.img.src = previews[name];
    }
    tile.meta.textContent = frame ? `#${frame.sequence} / ${frame.width}x${frame.height}` : "waiting";
  });
}

function pushHistory(kind, values) {
  history[kind].push(values);
  if (history[kind].length > historyLimit) {
    history[kind].shift();
  }
}

function updateTelemetry(data) {
  const joint = data.joint_state;
  if (!joint) return;
  pushHistory("position", joint.position.slice(0, 4));
  pushHistory("velocity", joint.velocity.slice(0, 4));
  pushHistory("torque", joint.torque.slice(0, 4));
  const offsetsMs = cameraNames.map((name) => (data.frame_offsets_ns?.[name] ?? 0) / 1_000_000);
  pushHistory("offset", offsetsMs);
  drawChart(charts.position, history.position, "rad");
  drawChart(charts.velocity, history.velocity, "rad/s");
  drawChart(charts.torque, history.torque, "Nm");
  drawChart(charts.offset, history.offset, "ms");
  telemetryMeta.textContent = `${history.position.length} samples`;
}

function drawChart(canvas, rows, unit) {
  if (!canvas || rows.length === 0) return;
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  const pad = 26;
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#fbfcfa";
  ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = "#e1e7df";
  ctx.lineWidth = 1;
  for (let i = 0; i < 4; i += 1) {
    const y = pad + ((height - pad * 2) * i) / 3;
    ctx.beginPath();
    ctx.moveTo(pad, y);
    ctx.lineTo(width - 8, y);
    ctx.stroke();
  }

  const flattened = rows.flat();
  const min = Math.min(...flattened, -0.001);
  const max = Math.max(...flattened, 0.001);
  const span = max - min || 1;
  const seriesCount = rows[0].length;
  for (let series = 0; series < seriesCount; series += 1) {
    ctx.strokeStyle = chartColors[series % chartColors.length];
    ctx.lineWidth = 2;
    ctx.beginPath();
    rows.forEach((row, index) => {
      const x = pad + ((width - pad - 10) * index) / Math.max(rows.length - 1, 1);
      const y = height - pad - ((row[series] - min) / span) * (height - pad * 2);
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  }

  ctx.fillStyle = "#647067";
  ctx.font = "11px system-ui, sans-serif";
  ctx.fillText(`${max.toFixed(2)} ${unit}`, 8, 14);
  ctx.fillText(min.toFixed(2), 8, height - 8);
}

async function refreshEpisodes() {
  const rows = await fetch("/api/episodes").then((response) => response.json());
  episodeMeta.textContent = rows.length ? `${rows.length} available` : "No episodes";
  episodes.innerHTML = "";
  rows.slice().reverse().forEach((episode) => {
    const row = document.createElement("div");
    row.className = "episode-row";
    row.innerHTML = `
      <div>
        <strong>${episode.episode_id}</strong>
        <span>${episode.sample_count} samples / ${episode.camera_names.join(", ")}</span>
      </div>
      <a class="button-link" href="/api/episodes/${episode.episode_id}/download">Download</a>
    `;
    episodes.appendChild(row);
  });
}

function updateRecordingState(data) {
  recording = Boolean(data.recording);
  paused = Boolean(data.paused);
  recordButton.textContent = recording ? "Stop" : "Start";
  recordButton.classList.toggle("recording", recording);
  pauseButton.textContent = paused ? "Resume" : "Pause";
  pauseButton.disabled = !recording;
  pauseButton.classList.toggle("paused", paused);
  recordingState.textContent = recording ? (paused ? "Paused" : "Recording") : "Idle";
}

async function refresh(forceEpisodes = false) {
  const data = await fetch("/api/live").then((response) => response.json());
  updateRecordingState(data);
  episodeCount.textContent = data.episode_count ?? 0;
  bufferedCount.textContent = data.buffered_samples ?? 0;
  const frames = data.frames || {};
  const previews = data.previews || {};
  const activeCameraCount = Object.keys(frames).length;
  cameraCount.textContent = activeCameraCount;
  cameraMeta.textContent = `${activeCameraCount} / 4 active`;
  mode.textContent = `${data.mode || "unknown"} collection console`;

  renderCameras(frames, previews);
  if (data.joint_state) {
    sampleMeta.textContent = `${data.joint_state.joint_names.length} joints`;
    if (lastJointTimestampNs) {
      const dtNs = data.joint_state.timestamp_ns - lastJointTimestampNs;
      sampleAge.textContent = dtNs > 0 ? `${(1_000_000_000 / dtNs).toFixed(0)} Hz` : "live";
    } else {
      sampleAge.textContent = "live";
    }
    lastJointTimestampNs = data.joint_state.timestamp_ns;
    renderJoints(data.joint_state);
    updateTelemetry(data);
  }
  if (forceEpisodes || data.episode_count !== lastEpisodeCount) {
    lastEpisodeCount = data.episode_count;
    await refreshEpisodes();
  }
}

initializeCameraTiles();
setInterval(refresh, 250);
refresh(true).catch((error) => {
  mode.textContent = error.message;
});
