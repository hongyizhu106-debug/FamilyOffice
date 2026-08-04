from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
import time
import webbrowser
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path


# Ensure we can import modules from Step1 when running this file directly.
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def _set_default_output_root() -> None:
    if os.environ.get("ROWDATA_OUTPUT_ROOT"):
        return
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        os.environ["ROWDATA_OUTPUT_ROOT"] = str(exe_dir / "RowData")
        if not os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(exe_dir / "ms-playwright")


_set_default_output_root()

from Step1.Constructor.Web_survey_app import BANK_PATH, app  # noqa: E402


def _preflight_steps() -> None:
    """Warm up and validate Step1/2/3 dependencies.

    Success path must be silent to keep console output clean (only the URL).
    """

    # Step1: question bank must exist.
    if not BANK_PATH.exists():
        raise FileNotFoundError(
            f"Missing question bank: {BANK_PATH} (run Step1/Constructor/Build_question_bank.py)"
        )

    # Step2: ensure singularity engine imports (rules/data are loaded lazily inside).
    try:
        import Step2.Constructor.singularity_engine as _  # noqa: F401
    except Exception as e:  # pragma: no cover
        raise RuntimeError(f"Step2 import failed: {e}") from e

    # Step3: ensure report materials are importable (used by Step4 report generation).
    try:
        import Step3.Constructor.report_materials as _  # noqa: F401
    except Exception as e:  # pragma: no cover
        raise RuntimeError(f"Step3 import failed: {e}") from e


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="MacinController",
        description="Start the Step1 web survey app (Flask) in a controlled way.",
    )
    p.add_argument(
        "--host",
        default="0.0.0.0",
        help="Bind host (default: 0.0.0.0 for LAN access)",
    )
    p.add_argument("--port", type=int, default=5000, help="Bind port (default: 5000)")
    p.add_argument(
        "--open-browser",
        action="store_true",
        help="Open the survey URL in the default browser.",
    )
    p.add_argument(
        "--no-quiet",
        action="store_true",
        help="Do not silence stdout/stderr (useful for debugging).",
    )
    p.add_argument(
        "--log-file",
        default="",
        help="Write server logs to this file (default: Step1/Rubbish/web_server_YYYYMMDD_HHMMSS.log).",
    )
    return p.parse_args(argv)


def _is_port_available(host: str, port: int) -> bool:
    # Try binding first. This is more reliable than connect()-based checks.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
        except OSError:
            return False
        return True


def _default_log_file() -> Path:
    # Keep logs next to other web artifacts.
    ts = time.strftime("%Y%m%d_%H%M%S")
    return BANK_PATH.parent.parent / "Rubbish" / f"web_server_{ts}.log"


def _configure_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8")],
    )
    # Reduce Flask/Werkzeug noise but keep important messages.
    logging.getLogger("werkzeug").setLevel(logging.INFO)


def _guess_lan_ip() -> str:
    """Best-effort LAN IP detection for friendly URLs."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"


def main() -> int:
    args = _parse_args(sys.argv[1:])

    try:
        _preflight_steps()
    except Exception as e:
        print(str(e))
        return 2

    if not (0 < int(args.port) < 65536):
        print(f"Invalid port: {args.port}")
        return 2

    if not _is_port_available(args.host, args.port):
        print(f"Port already in use: {args.host}:{args.port}")
        print("Hint: close the existing server or change --port")
        return 3

    display_host = args.host
    lan_host = _guess_lan_ip() if display_host in {"0.0.0.0", "::"} else display_host
    lan_url = f"http://{lan_host}:{args.port}/"
    local_url = f"http://127.0.0.1:{args.port}/"
    print(lan_url)
    if lan_url != local_url:
        print(local_url)
    sys.stdout.flush()

    log_path = Path(args.log_file) if args.log_file else _default_log_file()
    _configure_logging(log_path)
    logging.getLogger(__name__).info(
        "Starting web survey at %s (bank=%s)",
        lan_url,
        BANK_PATH,
    )

    if args.open_browser:
        try:
            webbrowser.open(lan_url)
        except Exception:
            logging.getLogger(__name__).exception("Failed to open browser")

    quiet = not args.no_quiet

    try:
        if quiet:
            # Suppress default noisy output
            import logging as flask_logging
            flask_logging.getLogger('werkzeug').setLevel(flask_logging.ERROR)
            
        app.run(host=args.host, port=args.port, debug=False, use_reloader=False)
    except OSError:
        logging.getLogger(__name__).exception("Server failed to start")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
