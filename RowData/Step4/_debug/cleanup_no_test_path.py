from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "Step1" / "Rubbish" / "NO.TEST-STEP3-STEP4.html"
OUT = ROOT / "Step4" / "_debug" / "cleanup_no_test_path_out.txt"

lines: list[str] = []
lines.append(f"target={TARGET}")
lines.append(f"exists={TARGET.exists()}")
lines.append(f"is_file={TARGET.is_file()}")
lines.append(f"is_dir={TARGET.is_dir()}")

if TARGET.exists() and TARGET.is_dir():
    try:
        sample = list(TARGET.iterdir())[:10]
        lines.append("contents_sample=" + ", ".join(p.name for p in sample))
    except Exception as e:
        lines.append(f"iter_error={type(e).__name__}: {e}")

try:
    if TARGET.is_dir():
        shutil.rmtree(TARGET)
    elif TARGET.exists():
        TARGET.unlink()
    lines.append("delete=ok")
except Exception as e:
    lines.append(f"delete=failed {type(e).__name__}: {e}")

lines.append(f"exists_after={TARGET.exists()}")

OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(OUT)
