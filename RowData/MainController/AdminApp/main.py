import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
WORKSPACE_ROWDATA = os.path.abspath(os.path.join(BASE_DIR, "..", ".."))
CONFIG_PATH = os.path.join(BASE_DIR, "app_config.json")


@dataclass
class ActionConfig:
    action_id: str
    label: str
    command: List[str]
    cwd: Optional[str] = None
    kind: str = "job"


@dataclass
class ActionState:
    config: ActionConfig
    process: Optional[subprocess.Popen] = None
    started_at: Optional[float] = None
    logs: List[str] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def append_log(self, line: str, limit: int) -> None:
        with self.lock:
            self.logs.append(line)
            if len(self.logs) > limit:
                overflow = len(self.logs) - limit
                if overflow > 0:
                    self.logs = self.logs[overflow:]

    def get_logs(self) -> List[str]:
        with self.lock:
            return list(self.logs)

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None


class ProcessRegistry:
    def __init__(self) -> None:
        self.actions: Dict[str, ActionState] = {}
        self.log_line_limit = 400

    def load_config(self) -> None:
        with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        self.log_line_limit = int(data.get("logLineLimit", 400))
        actions: Dict[str, ActionState] = {}
        for item in data.get("actions", []):
            action_id = item.get("id")
            if not action_id:
                continue
            cwd = self._resolve_cwd(item.get("cwd"))
            config = ActionConfig(
                action_id=action_id,
                label=item.get("label", action_id),
                command=list(item.get("command", [])),
                cwd=cwd,
                kind=item.get("kind", "job"),
            )
            actions[action_id] = ActionState(config=config)
        self.actions = actions

    def _resolve_cwd(self, raw: Optional[str]) -> Optional[str]:
        if not raw:
            return None
        if os.path.isabs(raw):
            return raw
        return os.path.abspath(os.path.join(WORKSPACE_ROWDATA, raw))

    def list_actions(self) -> List[Dict[str, object]]:
        result: List[Dict[str, object]] = []
        for action in self.actions.values():
            result.append(self._action_snapshot(action))
        return result

    def _action_snapshot(self, action: ActionState) -> Dict[str, object]:
        running = action.is_running()
        return {
            "id": action.config.action_id,
            "label": action.config.label,
            "kind": action.config.kind,
            "running": running,
            "pid": action.process.pid if running else None,
            "startedAt": action.started_at,
        }

    def get_action(self, action_id: str) -> ActionState:
        if action_id not in self.actions:
            raise KeyError(action_id)
        return self.actions[action_id]

    def start_action(self, action_id: str) -> Dict[str, object]:
        action = self.get_action(action_id)
        if action.is_running():
            raise RuntimeError("Action is already running")
        if not action.config.command:
            raise RuntimeError("Action has no command configured")
        creationflags = 0
        if os.name == "nt" and hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
        process = subprocess.Popen(
            action.config.command,
            cwd=action.config.cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            creationflags=creationflags,
        )
        action.process = process
        action.started_at = time.time()
        action.append_log("[system] started", self.log_line_limit)
        self._start_log_thread(action, process.stdout, "stdout")
        self._start_log_thread(action, process.stderr, "stderr")
        self._start_exit_thread(action)
        return self._action_snapshot(action)

    def stop_action(self, action_id: str) -> Dict[str, object]:
        action = self.get_action(action_id)
        if not action.is_running():
            raise RuntimeError("Action is not running")
        action.append_log("[system] stopping", self.log_line_limit)
        action.process.terminate()
        try:
            action.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            action.process.kill()
        return self._action_snapshot(action)

    def _start_log_thread(self, action: ActionState, stream, label: str) -> None:
        if stream is None:
            return

        def _reader() -> None:
            for line in iter(stream.readline, ""):
                sanitized = line.rstrip("\n")
                action.append_log(f"[{label}] {sanitized}", self.log_line_limit)
            stream.close()

        thread = threading.Thread(target=_reader, daemon=True)
        thread.start()

    def _start_exit_thread(self, action: ActionState) -> None:
        def _waiter() -> None:
            if action.process is None:
                return
            exit_code = action.process.wait()
            action.append_log(f"[system] exited with {exit_code}", self.log_line_limit)

        thread = threading.Thread(target=_waiter, daemon=True)
        thread.start()


registry = ProcessRegistry()
registry.load_config()

app = FastAPI()
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/actions")
def list_actions() -> List[Dict[str, object]]:
    return registry.list_actions()


@app.get("/api/actions/{action_id}")
def get_action(action_id: str) -> Dict[str, object]:
    try:
        action = registry.get_action(action_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown action")
    return registry._action_snapshot(action)


@app.post("/api/actions/{action_id}/start")
def start_action(action_id: str) -> Dict[str, object]:
    try:
        return registry.start_action(action_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown action")
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.post("/api/actions/{action_id}/stop")
def stop_action(action_id: str) -> Dict[str, object]:
    try:
        return registry.stop_action(action_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown action")
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.get("/api/actions/{action_id}/logs")
def get_logs(action_id: str) -> Dict[str, object]:
    try:
        action = registry.get_action(action_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown action")
    return {
        "id": action.config.action_id,
        "logs": action.get_logs(),
    }


@app.post("/api/reload")
def reload_config() -> Dict[str, object]:
    registry.load_config()
    return {"ok": True, "count": len(registry.actions)}
