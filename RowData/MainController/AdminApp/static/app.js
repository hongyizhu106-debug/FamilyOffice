const grid = document.getElementById("action-grid");
const logsOutput = document.getElementById("logs-output");
const logsMeta = document.getElementById("logs-meta");
const refreshButton = document.getElementById("refresh");
const reloadButton = document.getElementById("reload");

let selectedActionId = null;

async function fetchActions() {
  const response = await fetch("/api/actions");
  if (!response.ok) {
    throw new Error("Failed to load actions");
  }
  return response.json();
}

async function fetchLogs(actionId) {
  const response = await fetch(`/api/actions/${actionId}/logs`);
  if (!response.ok) {
    throw new Error("Failed to load logs");
  }
  return response.json();
}

function renderCards(actions) {
  grid.innerHTML = "";
  actions.forEach((action) => {
    const card = document.createElement("div");
    card.className = "card";

    const title = document.createElement("h3");
    title.textContent = action.label;

    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = `${action.kind.toUpperCase()} · ${action.id}`;

    const status = document.createElement("div");
    status.className = "status";
    const dot = document.createElement("span");
    dot.className = "status-dot" + (action.running ? " running" : "");
    const text = document.createElement("span");
    text.textContent = action.running ? "Running" : "Stopped";
    status.appendChild(dot);
    status.appendChild(text);

    const actionsRow = document.createElement("div");
    actionsRow.className = "card-actions";

    const startBtn = document.createElement("button");
    startBtn.className = "primary";
    startBtn.textContent = "Start";
    startBtn.disabled = action.running;
    startBtn.addEventListener("click", () => startAction(action.id));

    const stopBtn = document.createElement("button");
    stopBtn.className = "ghost";
    stopBtn.textContent = "Stop";
    stopBtn.disabled = !action.running;
    stopBtn.addEventListener("click", () => stopAction(action.id));

    const viewBtn = document.createElement("button");
    viewBtn.className = "ghost";
    viewBtn.textContent = "View Logs";
    viewBtn.addEventListener("click", () => selectLogs(action.id, action.label));

    actionsRow.appendChild(startBtn);
    actionsRow.appendChild(stopBtn);
    actionsRow.appendChild(viewBtn);

    card.appendChild(title);
    card.appendChild(meta);
    card.appendChild(status);
    card.appendChild(actionsRow);

    grid.appendChild(card);
  });
}

async function refreshAll() {
  try {
    const actions = await fetchActions();
    renderCards(actions);
    if (selectedActionId) {
      await updateLogs(selectedActionId);
    }
  } catch (err) {
    console.error(err);
  }
}

async function startAction(actionId) {
  await fetch(`/api/actions/${actionId}/start`, { method: "POST" });
  await refreshAll();
}

async function stopAction(actionId) {
  await fetch(`/api/actions/${actionId}/stop`, { method: "POST" });
  await refreshAll();
}

async function selectLogs(actionId, label) {
  selectedActionId = actionId;
  logsMeta.textContent = `Streaming ${label}`;
  await updateLogs(actionId);
}

async function updateLogs(actionId) {
  const data = await fetchLogs(actionId);
  logsOutput.textContent = data.logs.length ? data.logs.join("\n") : "No logs yet.";
}

refreshButton.addEventListener("click", refreshAll);
reloadButton.addEventListener("click", async () => {
  await fetch("/api/reload", { method: "POST" });
  await refreshAll();
});

setInterval(refreshAll, 2500);
refreshAll();
