from __future__ import annotations

import json
import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from tkinter import ttk


# Allow direct execution of this file from any working directory.
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def _repo_root() -> Path:
    if getattr(sys, "frozen", False):
        meipass = sys.__dict__.get("_MEIPASS")
        if meipass:
            return Path(str(meipass))
    return Path(__file__).resolve().parents[1]


def _output_root() -> Path:
    env_override = os.environ.get("ROWDATA_OUTPUT_ROOT")
    if env_override:
        try:
            return Path(env_override).expanduser().resolve()
        except OSError:
            pass
    if getattr(sys, "frozen", False):
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / "RowData"
    return _repo_root()


def _responses_dir() -> Path:
    return _output_root() / "Rubbish"


def _report_out_dir() -> Path:
    if getattr(sys, "frozen", False):
        return _output_root() / "Reports"
    return _repo_root() / "Step4" / "_debug" / "out"


def _latest_file(directory: Path, pattern: str) -> Path | None:
    if not directory.exists():
        return None
    files = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _find_python_from_env() -> str | None:
    repo_root = _repo_root()
    candidate = repo_root / "Step1" / "Env" / "Scripts" / "python.exe"
    return str(candidate) if candidate.exists() else None


def _pick_python_runtime() -> str:
    env_python = _find_python_from_env()
    if env_python:
        try:
            import subprocess

            # Copied virtualenvs can point to a missing base interpreter.
            proc = subprocess.run(
                [env_python, "-c", "import sys; print(sys.version)"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=5,
            )
            if proc.returncode == 0:
                return env_python
        except Exception:
            pass
    return sys.executable


class LauncherApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("RowData Launcher")
        self.root.geometry("460x360")
        self.root.resizable(False, False)

        self._web_thread: threading.Thread | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(frame, text="RowData Launcher", font=("Segoe UI", 14, "bold"))
        title.pack(anchor=tk.W, pady=(0, 8))

        self.status_var = tk.StringVar(value="Ready")
        status = ttk.Label(frame, textvariable=self.status_var)
        status.pack(anchor=tk.W, pady=(0, 10))

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Button(btn_frame, text="启动网页问卷", command=self._start_web).pack(fill=tk.X, pady=4)
        ttk.Button(btn_frame, text="控制台问卷", command=self._start_cli_survey).pack(fill=tk.X, pady=4)
        ttk.Button(btn_frame, text="生成报告(固定路径)", command=self._generate_report).pack(fill=tk.X, pady=4)
        ttk.Button(btn_frame, text="校验最新报告", command=self._validate_report).pack(fill=tk.X, pady=4)
        ttk.Button(btn_frame, text="打开答卷目录", command=self._open_responses_dir).pack(fill=tk.X, pady=4)
        ttk.Button(btn_frame, text="打开报告目录", command=self._open_reports_dir).pack(fill=tk.X, pady=4)

        ttk.Separator(frame).pack(fill=tk.X, pady=10)

        ttk.Button(frame, text="退出", command=self.root.destroy).pack(anchor=tk.E)

    def _set_status(self, msg: str) -> None:
        self.status_var.set(msg)
        self.root.update_idletasks()

    def _start_web(self) -> None:
        if self._web_thread and self._web_thread.is_alive():
            messagebox.showinfo("RowData", "网页问卷已在运行。")
            return

        def _run() -> None:
            try:
                from MainController.MacinController import main

                self._set_status("网页问卷启动中...")
                # MacinController.main() reads CLI args from sys.argv.
                old_argv = sys.argv[:]
                try:
                    sys.argv = [
                        "MacinController",
                        "--host",
                        "0.0.0.0",
                        "--port",
                        "5000",
                    ]
                    main()
                finally:
                    sys.argv = old_argv
            except Exception as exc:
                messagebox.showerror("RowData", f"网页问卷启动失败: {exc}")
            finally:
                self._set_status("Ready")

        # Run the web server in a daemon thread so the UI stays responsive.
        self._web_thread = threading.Thread(target=_run, daemon=True)
        self._web_thread.start()

    def _start_cli_survey(self) -> None:
        python_exe = _pick_python_runtime()
        try:
            import subprocess

            cmd = [python_exe, str(_repo_root() / "Step1" / "Constructor" / "Survey_cli.py")]
            subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
        except Exception as exc:
            messagebox.showerror("RowData", f"控制台问卷启动失败: {exc}")

    def _generate_report(self) -> None:
        def _run() -> None:
            try:
                responses_dir = _responses_dir()
                latest = _latest_file(responses_dir, "web_response_*.json")
                if not latest:
                    messagebox.showwarning("RowData", f"未找到答卷 JSON: {responses_dir}")
                    return

                out_dir = _report_out_dir()
                out_dir.mkdir(parents=True, exist_ok=True)

                payload = json.loads(latest.read_text(encoding="utf-8"))
                from Step4.report_generator import generate_report_artifacts

                self._set_status("生成报告中...")
                artifacts = generate_report_artifacts(
                    payload=payload,
                    response_json_path=latest,
                    output_dir=out_dir,
                    report_id="ROWDATA-LAUNCHER",
                )

                msg = f"HTML: {out_dir / artifacts.html_name}"
                if artifacts.pdf_name:
                    msg += f"\nPDF: {out_dir / artifacts.pdf_name}"
                if artifacts.warnings:
                    msg += "\n\nWarnings:\n- " + "\n- ".join(artifacts.warnings[:8])
                if artifacts.error:
                    msg += f"\n\nError: {artifacts.error}"

                if artifacts.ok:
                    messagebox.showinfo("RowData", msg)
                else:
                    messagebox.showwarning("RowData", msg)
            except Exception as exc:
                messagebox.showerror("RowData", f"报告生成失败: {exc}")
            finally:
                self._set_status("Ready")

        threading.Thread(target=_run, daemon=True).start()

    def _validate_report(self) -> None:
        def _run() -> None:
            try:
                out_dir = _report_out_dir()
                latest = _latest_file(out_dir, "*.html")
                if not latest:
                    messagebox.showwarning("RowData", f"未找到报告 HTML: {out_dir}")
                    return
                from Step4.validate_report import validate_step4_html_file

                res = validate_step4_html_file(latest)
                msg = f"HTML: {latest}\nOK: {res.ok}"
                if res.errors:
                    msg += "\n\nErrors:\n- " + "\n- ".join(res.errors[:8])
                if res.warnings:
                    msg += "\n\nWarnings:\n- " + "\n- ".join(res.warnings[:8])
                if res.ok:
                    messagebox.showinfo("RowData", msg)
                else:
                    messagebox.showwarning("RowData", msg)
            except Exception as exc:
                messagebox.showerror("RowData", f"报告校验失败: {exc}")

        threading.Thread(target=_run, daemon=True).start()

    def _open_responses_dir(self) -> None:
        path = _responses_dir()
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)  # type: ignore[attr-defined]

    def _open_reports_dir(self) -> None:
        path = _report_out_dir()
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)  # type: ignore[attr-defined]


def main() -> int:
    root = tk.Tk()
    ttk.Style().theme_use("clam")
    app = LauncherApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
