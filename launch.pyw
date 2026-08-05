"""
launch.pyw — 家族诊断问卷与报告系统 · 图形启动器
双击运行，自动弹出控制面板，点击"启动服务"即可。
"""
from __future__ import annotations

import socket
import subprocess
import sys
import threading
import time
import webbrowser
import tkinter as tk
from tkinter import messagebox
from pathlib import Path

# ── 路径配置 ────────────────────────────────────────────────
PROJECT_DIR = Path(__file__).resolve().parent
ROW_DATA    = PROJECT_DIR / "RowData"
CONTROLLER  = ROW_DATA / "MainController" / "MacinController.py"
VENV_WIN    = ROW_DATA / "Step1" / "Env" / "Scripts" / "python.exe"
VENV_UNIX   = ROW_DATA / "Step1" / "Env" / "bin" / "python"
PORT        = 5000
URL         = f"http://127.0.0.1:{PORT}/"


def _find_python() -> str:
    for p in (VENV_WIN, VENV_UNIX):
        if p.exists():
            return str(p)
    return sys.executable


def _port_in_use() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


# ── 主窗口 ──────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("家族诊断问卷与报告系统")
        self.resizable(False, False)
        self._proc: subprocess.Popen | None = None
        self._build_ui()
        self._refresh_status()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI 构建 ──────────────────────────────────────────────
    def _build_ui(self) -> None:
        PAD = dict(padx=16, pady=8)

        # 标题
        tk.Label(self, text="家族诊断问卷与报告系统",
                 font=("PingFang SC", 15, "bold")).pack(**PAD)

        # 状态灯 + 文字
        row = tk.Frame(self)
        row.pack(padx=16, pady=4)
        self._dot = tk.Label(row, text="●", font=("", 14))
        self._dot.pack(side="left")
        self._status_var = tk.StringVar(value="检测中…")
        tk.Label(row, textvariable=self._status_var,
                 font=("PingFang SC", 12)).pack(side="left", padx=6)

        # 网址
        url_frame = tk.Frame(self)
        url_frame.pack(padx=16, pady=2)
        tk.Label(url_frame, text="地址:", font=("PingFang SC", 11)).pack(side="left")
        url_lbl = tk.Label(url_frame, text=URL,
                           font=("PingFang SC", 11), fg="#0066cc", cursor="hand2")
        url_lbl.pack(side="left")
        url_lbl.bind("<Button-1>", lambda _: webbrowser.open(URL))

        # 密码
        tk.Label(self, text="访问密码: familyoffice",
                 font=("PingFang SC", 10), fg="#555").pack(padx=16, pady=2)

        # 按钮区
        btn_frame = tk.Frame(self)
        btn_frame.pack(padx=16, pady=12, fill="x")

        self._start_btn = tk.Button(btn_frame, text="▶  启动服务", width=14,
                                    bg="#28a745", fg="white", relief="flat",
                                    font=("PingFang SC", 11, "bold"),
                                    command=self._start)
        self._start_btn.pack(side="left", padx=4)

        self._stop_btn = tk.Button(btn_frame, text="■  停止服务", width=14,
                                   bg="#dc3545", fg="white", relief="flat",
                                   font=("PingFang SC", 11, "bold"),
                                   state="disabled", command=self._stop)
        self._stop_btn.pack(side="left", padx=4)

        tk.Button(btn_frame, text="打开浏览器", width=10,
                  relief="flat", font=("PingFang SC", 11),
                  command=lambda: webbrowser.open(URL)).pack(side="left", padx=4)

        # 日志区
        self._log = tk.Text(self, height=8, width=52, state="disabled",
                            font=("Menlo", 10), bg="#1e1e1e", fg="#d4d4d4",
                            relief="flat")
        self._log.pack(padx=16, pady=(0, 12))

    # ── 状态刷新 ─────────────────────────────────────────────
    def _refresh_status(self) -> None:
        running = _port_in_use()
        if running:
            self._dot.config(fg="#28a745")
            self._status_var.set("服务运行中")
            self._start_btn.config(state="disabled")
            self._stop_btn.config(state="normal")
        else:
            self._dot.config(fg="#dc3545")
            self._status_var.set("服务已停止")
            self._start_btn.config(state="normal")
            self._stop_btn.config(state="disabled")
        self.after(2000, self._refresh_status)

    # ── 日志追加 ─────────────────────────────────────────────
    def _log_line(self, text: str) -> None:
        self._log.config(state="normal")
        self._log.insert("end", text.rstrip() + "\n")
        self._log.see("end")
        self._log.config(state="disabled")

    # ── 启动 ─────────────────────────────────────────────────
    def _start(self) -> None:
        if _port_in_use():
            webbrowser.open(URL)
            return
        if not CONTROLLER.exists():
            messagebox.showerror("错误", f"未找到入口文件:\n{CONTROLLER}")
            return

        python_bin = _find_python()
        self._log_line(f"Python: {python_bin}")
        self._log_line("正在启动服务…")
        self._start_btn.config(state="disabled")

        self._proc = subprocess.Popen(
            [python_bin, str(CONTROLLER), "--host", "0.0.0.0", "--port", str(PORT)],
            cwd=str(ROW_DATA),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
        )
        threading.Thread(target=self._read_output, daemon=True).start()
        threading.Thread(target=self._wait_ready,  daemon=True).start()

    def _read_output(self) -> None:
        if self._proc and self._proc.stdout:
            for line in self._proc.stdout:
                self.after(0, self._log_line, line)

    def _wait_ready(self) -> None:
        deadline = time.time() + 30
        while time.time() < deadline:
            if _port_in_use():
                self.after(0, self._log_line, f"✓ 服务就绪: {URL}")
                self.after(0, webbrowser.open, URL)
                return
            time.sleep(0.5)
        self.after(0, self._log_line, "✗ 启动超时，请检查依赖是否安装完整")

    # ── 停止 ─────────────────────────────────────────────────
    def _stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            self._proc = None
            self._log_line("服务已停止")

    def _on_close(self) -> None:
        self._stop()
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
