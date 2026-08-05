#!/usr/bin/env python3
"""
一键启动 — 家族诊断问卷与报告系统
用法: python start.py [--port 5000] [--no-browser]
"""
from __future__ import annotations

import argparse
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

REPO_ROOT  = Path(__file__).resolve().parent
ROW_DATA   = REPO_ROOT / "RowData"
CONTROLLER = ROW_DATA / "MainController" / "MacinController.py"
VENV_WIN   = ROW_DATA / "Step1" / "Env" / "Scripts" / "python.exe"
VENV_UNIX  = ROW_DATA / "Step1" / "Env" / "bin" / "python"

BANNER = """
 ============================================
  家族诊断问卷与报告系统
  网页地址 : http://127.0.0.1:{port}/
  访问密码 : familyoffice
 ============================================
"""


def _find_python() -> str:
    """优先使用项目 venv，否则用当前解释器。"""
    for candidate in (VENV_WIN, VENV_UNIX):
        if candidate.exists():
            return str(candidate)
    return sys.executable


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _wait_ready(port: int, timeout: int = 30) -> bool:
    """轮询直到服务可连接，最多等待 timeout 秒。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _port_in_use(port):
            return True
        time.sleep(0.5)
    return False


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="一键启动家族诊断问卷系统")
    p.add_argument("--port",       type=int, default=5000, help="监听端口（默认 5000）")
    p.add_argument("--no-browser", action="store_true",    help="不自动打开浏览器")
    p.add_argument("--host",       default="0.0.0.0",      help="绑定地址（默认 0.0.0.0）")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    url  = f"http://127.0.0.1:{args.port}/"

    print(BANNER.format(port=args.port))

    # 如果服务已在运行，直接打开浏览器
    if _port_in_use(args.port):
        print(f" 检测到服务已在运行，直接打开浏览器: {url}")
        if not args.no_browser:
            webbrowser.open(url)
        return 0

    # 检查入口文件
    if not CONTROLLER.exists():
        print(f" [错误] 未找到入口文件: {CONTROLLER}")
        return 1

    python_bin = _find_python()
    cmd = [
        python_bin, str(CONTROLLER),
        "--host", args.host,
        "--port", str(args.port),
    ]
    print(f" 使用解释器: {python_bin}")
    print(f" 正在启动服务，请稍候...\n")

    proc = subprocess.Popen(
        cmd,
        cwd=str(ROW_DATA),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    # 等待服务就绪
    if not _wait_ready(args.port, timeout=30):
        # 打印进程输出帮助诊断
        try:
            out, _ = proc.communicate(timeout=2)
            if out:
                print(out)
        except subprocess.TimeoutExpired:
            pass
        print(" [错误] 服务启动超时，请检查依赖是否齐全（见 RowData/requirements.txt）")
        proc.terminate()
        return 1

    print(f" 服务已就绪: {url}")

    if not args.no_browser:
        webbrowser.open(url)

    print(" 按 Ctrl+C 停止服务\n")

    # 转发服务日志到控制台
    def _handle_sigint(sig, frame):  # noqa: ANN001
        print("\n 正在停止服务...")
        proc.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle_sigint)

    try:
        for line in proc.stdout:  # type: ignore[union-attr]
            sys.stdout.write(line)
            sys.stdout.flush()
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()

    return proc.returncode or 0


if __name__ == "__main__":
    raise SystemExit(main())
