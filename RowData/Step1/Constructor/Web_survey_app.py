from __future__ import annotations

import collections
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from flask import Flask, render_template_string, request, send_from_directory, url_for

from Step1.Tools.planA_financial_analysis import generate_planA_analysis

try:
  # When imported via MainController (recommended)
  from Step2.Constructor.singularity_engine import (
    SCORING_VERSION,
    compute_singularity_stage_b_with_trace,
    compute_singularity_with_trace,
  )
except ImportError:  # pragma: no cover
  # When running this file directly, ensure repo root is importable.
  import sys
  REPO_ROOT = Path(__file__).resolve().parents[2]
  if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
  from Step2.Constructor.singularity_engine import (
    SCORING_VERSION,
    compute_singularity_stage_b_with_trace,
    compute_singularity_with_trace,
  )


SOURCE_DIR = Path(__file__).resolve().parent
SOURCE_ROOT = SOURCE_DIR.parent


def _runtime_root() -> Path:
  if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    return Path(sys._MEIPASS)
  return SOURCE_ROOT


def _resolve_data_dir(runtime_root: Path) -> Path:
  candidates = [
    runtime_root / "Step1" / "Data",
    runtime_root / "Data",
    SOURCE_ROOT / "Data",
  ]
  for cand in candidates:
    if cand.exists():
      return cand
  return candidates[0]


def _resolve_bank_path(data_dir: Path, runtime_root: Path) -> Path:
  candidates = [
    data_dir / "Question_bank.json",
    runtime_root / "Step1" / "Data" / "Question_bank.json",
    runtime_root / "Data" / "Question_bank.json",
    SOURCE_ROOT / "Data" / "Question_bank.json",
  ]
  for cand in candidates:
    if cand.exists():
      return cand

  if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    try:
      for cand in Path(sys._MEIPASS).rglob("Question_bank.json"):
        return cand
    except OSError:
      pass

  return candidates[0]


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
  return SOURCE_ROOT


RUNTIME_ROOT = _runtime_root()
DATA_DIR = _resolve_data_dir(RUNTIME_ROOT)
BANK_PATH = _resolve_bank_path(DATA_DIR, RUNTIME_ROOT)
OUTPUT_ROOT = _output_root()
RESPONSES_DIR = OUTPUT_ROOT / "Rubbish"
PROGRESS_DIR = RESPONSES_DIR
REPORTS_DIR = RESPONSES_DIR / "web_reports"
CLIENT_ID_COOKIE = "survey_client_id"
INTRO_OK_COOKIE = "survey_intro_ok"
AUTH_COOKIE = "survey_auth"
PLAN_A_STATUS_RUNNING = "running"
PLAN_A_STATUS_DONE = "done"
PLAN_A_STATUS_ERROR = "error"
PLAN_A_RETRY_SECONDS = 8 * 60

# ---------------------------------------------------------------------------
# Security: Access Password
# ---------------------------------------------------------------------------
# Fixed password for login page, or override via env var.
ACCESS_PASSWORD = os.environ.get("SURVEY_PASSWORD") or "familyoffice"
_AUTH_HMAC_KEY = hashlib.sha256(ACCESS_PASSWORD.encode()).digest()

# Security: Debug endpoint gating
DEBUG_ENABLED = os.environ.get("SURVEY_DEBUG", "0").strip() == "1"

# Security: Rate limiting (per IP, in-memory)
RATE_LIMIT_MAX = int(os.environ.get("SURVEY_RATE_LIMIT", "60"))  # requests/minute
_rate_counters: dict[str, collections.deque] = {}
_rate_lock = threading.Lock()

# Security: CSRF
_CSRF_SECRET = secrets.token_bytes(32)


INTRO_HTML = """<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>问卷信息确认</title>
  <style>
    :root { --ink:#1f2328; --muted:#5b616a; --paper:#fbf7ef; --paper2:#f6efe1; --line: rgba(31,35,40,0.18); --accent:#8b2f2f; }
    body { margin:0; padding:0; background: linear-gradient(180deg, var(--paper), var(--paper2)); color: var(--ink);
      font-family: \"Microsoft YaHei\", \"PingFang SC\", Arial, sans-serif; line-height: 1.6; }
    .wrap { max-width: 720px; margin: 28px auto; padding: 0 16px; }
    .card { background: rgba(255,255,255,0.72); border: 1px solid rgba(31,35,40,0.10); border-radius: 12px; padding: 18px 18px; }
    h1 { margin: 0 0 8px; font-size: 20px; }
    p { margin: 8px 0; color: var(--muted); }
    label { display:block; margin-top: 12px; font-weight: 600; }
    input, select { width: 100%; padding: 10px 12px; margin-top: 6px; border-radius: 10px; border: 1px solid var(--line); background: rgba(255,255,255,0.9); font-size: 14px; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .actions { margin-top: 16px; display:flex; gap: 10px; flex-wrap: wrap; }
    button { padding: 10px 14px; border-radius: 10px; border: 1px solid rgba(139,47,47,0.55); background: rgba(139,47,47,0.10); cursor:pointer; font-size: 14px; }
    .hint { font-size: 12px; color: var(--muted); margin-top: 6px; }
    .error { margin-top: 10px; background: #fff4f4; border: 1px solid #f1c4c4; padding: 10px; border-radius: 10px; }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"card\">
      <h1>进入问卷前，请确认称呼</h1>
      <p>用于生成诊断报告中的称谓与家族标识（例如：朱先生 / 朱女士）。</p>

      {% if error %}
        <div class=\"error\">{{ error }}</div>
      {% endif %}

      <form method="post" action="{{ url_for('intro_submit') }}">
        <input type="hidden" name="csrf_token" value="{{ csrf_token }}" />
        <div class=\"row\">
          <div>
            <label for=\"surname\">姓氏</label>
            <input id=\"surname\" name=\"surname\" value=\"{{ surname }}\" placeholder=\"如：朱 / 欧阳\" maxlength=\"4\" required />
            <div class=\"hint\">支持复姓（最多 4 字）。</div>
          </div>
          <div>
            <label for=\"honorific\">称谓</label>
            <select id=\"honorific\" name=\"honorific\" required>
              <option value=\"先生\" {% if honorific=='先生' %}selected{% endif %}>先生</option>
              <option value=\"女士\" {% if honorific=='女士' %}selected{% endif %}>女士</option>
            </select>
            <div class=\"hint\">将用于报告中的称呼。</div>
          </div>
        </div>

        <label for=\"has_company\">是否有上市公司</label>
        <select id=\"has_company\" name=\"has_company\">
          <option value=\"0\" {% if has_company!='1' %}selected{% endif %}>没有</option>
          <option value=\"1\" {% if has_company=='1' %}selected{% endif %}>有</option>
        </select>
        <div class=\"hint\">如果有，可输入代码并生成一份按 PlanA 规范的易读财务摘要（CN/US）。</div>

        <div class=\"row\">
          <div>
            <label for=\"market\">市场</label>
            <select id=\"market\" name=\"market\">
              <option value=\"CN\" {% if market=='CN' %}selected{% endif %}>CN（A股）</option>
              <option value=\"US\" {% if market=='US' %}selected{% endif %}>US（美股）</option>
            </select>
          </div>
          <div>
            <label for=\"symbol\">代码</label>
            <input id=\"symbol\" name=\"symbol\" value=\"{{ symbol }}\" placeholder=\"CN: 000001.SZ / US: NVDA\" />
            <div class=\"hint\">CN 请填写 Tushare ts_code（如 600519.SH）。</div>
          </div>
        </div>

        <label for=\"period\">报告期（YYYYMMDD）</label>
        <input id=\"period\" name=\"period\" value=\"{{ period }}\" placeholder=\"如：20241231 / 20250930\" />
        <div class=\"hint\">建议：年报 1231；季报 0331/0630/0930。</div>

        {% if company_status == 'running' %}
          <div class=\"hint\" style=\"margin-top:14px;\">PlanA 正在后台生成，可直接开始答题，完成后会自动写入报告。</div>
        {% endif %}

        {% if company_error %}
          <div class=\"error\" style=\"margin-top:14px;\">上市公司财务摘要生成失败：{{ company_error }}</div>
        {% endif %}

        <div class=\"actions\">
          <button type=\"submit\">开始作答</button>
          <button type=\"button\" onclick=\"window.location.href='{{ url_for('intro_skip') }}'\">跳过（使用默认占位）</button>
        </div>
      </form>
    </div>
  </div>
</body>
</html>"""


HTML = """<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{{ bank.title }}</title>
  <style>
    :root {
      --ink: #1f2328;
      --muted: #5b616a;
      --paper: #fbf7ef;
      --paper-2: #f6efe1;
      --line: rgba(31, 35, 40, 0.18);
      --line-soft: rgba(31, 35, 40, 0.10);
      --accent: #8b2f2f; /* 朱砂/印泥感 */
      --accent-2: #335c4a; /* 墨绿点缀 */
    }

    body {
      margin: 0;
      padding: 0;
      line-height: 1.6;
      color: var(--ink);
      background:
        radial-gradient(1200px 500px at 20% 0%, rgba(139, 47, 47, 0.06), transparent 55%),
        radial-gradient(900px 420px at 90% 15%, rgba(51, 92, 74, 0.05), transparent 60%),
        linear-gradient(180deg, var(--paper), var(--paper-2));
      font-family: "STSong", "Songti SC", "SimSun", "Noto Serif SC", serif;
    }

    .page {
      max-width: 960px;
      margin: 24px auto;
      padding: 0 16px 96px; /* 底部留白给右下角按钮 */
    }

    .header {
      position: relative;
      padding: 16px 18px;
      border: 1px solid var(--line-soft);
      border-radius: 12px;
      background: rgba(255, 255, 255, 0.55);
      backdrop-filter: blur(2px);
    }

    h1 { margin: 0 0 6px; letter-spacing: 0.5px; }
    .subtitle { margin: 0; color: var(--muted); font-size: 13px; }

    .q {
      margin-top: 16px;
      padding: 16px 18px;
      border: 1px solid var(--line-soft);
      border-radius: 12px;
      background: rgba(255, 255, 255, 0.62);
      box-shadow: 0 10px 22px rgba(31, 35, 40, 0.06);
    }
    .q-title { margin: 0 0 8px; font-weight: 600; }
    .opt { display: block; margin: 8px 0; }
    .meta { color: #555; font-size: 12px; margin-top: 6px; }
    .error { background: #fff4f4; border: 1px solid #f1c4c4; padding: 10px; margin: 12px 0; }
    .actions { margin-top: 14px; display: flex; gap: 10px; flex-wrap: wrap; }
    button { padding: 10px 16px; font-family: inherit; }
    .nav-btn { padding: 10px 16px; border: 1px solid #ccc; background: #f8f8f8; cursor: pointer; }
    .nav-btn[disabled] { opacity: 0.5; cursor: not-allowed; }

    .nav-btn {
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.70);
      border-radius: 10px;
      transition: transform 120ms ease, box-shadow 120ms ease;
    }
    .nav-btn:hover { transform: translateY(-1px); box-shadow: 0 8px 18px rgba(31, 35, 40, 0.08); }

    .floating-save {
      position: fixed;
      right: 24px;
      bottom: 24px;
      z-index: 20;
      display: flex;
      gap: 10px;
      align-items: center;
    }
    .save-btn {
      border: 1px solid rgba(139, 47, 47, 0.55);
      background: rgba(139, 47, 47, 0.10);
      color: var(--ink);
      border-radius: 12px;
      padding: 12px 18px;
      cursor: pointer;
      box-shadow: 0 10px 26px rgba(31, 35, 40, 0.14);
      transition: transform 120ms ease, box-shadow 120ms ease;
    }
    .save-btn:hover { transform: translateY(-1px); box-shadow: 0 14px 34px rgba(31, 35, 40, 0.18); }
    .end-btn {
      border: 1px solid rgba(139, 47, 47, 0.75);
      background: rgba(139, 47, 47, 0.16);
      color: var(--ink);
      border-radius: 12px;
      padding: 12px 18px;
      cursor: pointer;
      box-shadow: 0 10px 26px rgba(31, 35, 40, 0.14);
      transition: transform 120ms ease, box-shadow 120ms ease;
    }
    .end-btn:hover { transform: translateY(-1px); box-shadow: 0 14px 34px rgba(31, 35, 40, 0.18); }

    .save-status {
      font-size: 12px;
      color: var(--muted);
      background: rgba(255,255,255,0.65);
      padding: 8px 10px;
      border-radius: 10px;
      border: 1px solid var(--line-soft);
      min-width: 110px;
      text-align: center;
    }

    .sidebar {
      position: fixed;
      right: 24px;
      top: 24px;
      width: 240px;
      max-height: 80vh;
      overflow: auto;
      background: rgba(255, 255, 255, 0.80);
      border: 1px solid var(--line-soft);
      box-shadow: 0 4px 12px rgba(0,0,0,0.08);
      border-radius: 8px;
      padding: 12px;
      font-size: 13px;
    }
    .sidebar h4 { margin: 0 0 8px; font-size: 14px; }
    .catalog-group { margin-bottom: 10px; }
    .catalog-title { font-weight: 600; margin: 8px 0 4px; }
    .catalog-list { display: flex; flex-wrap: wrap; gap: 6px; }
    .catalog-item {
      display: inline-block;
      min-width: 28px;
      text-align: center;
      padding: 4px 6px;
      border-radius: 6px;
      border: 1px solid #ddd;
      color: #333;
      text-decoration: none;
    }
    .catalog-item.current { background: rgba(139, 47, 47, 0.10); border-color: rgba(139, 47, 47, 0.35); }
    .catalog-item.answered { background: rgba(51, 92, 74, 0.08); border-color: rgba(51, 92, 74, 0.30); }
    .progress { color: #555; margin-bottom: 8px; }
    .page.with-sidebar { padding-right: 280px; }

    @media (max-width: 980px) {
      .sidebar { display: none; }
      .page.with-sidebar { padding-right: 16px; }
    }
  </style>
</head>
<body>
  <div class=\"page with-sidebar\">
    <div class=\"header\">
      <h1>{{ bank.title }}</h1>
      <p class=\"subtitle\">一题一页 · 支持跳题 · 右下角可随时保存并结束</p>
    </div>

    {% if error %}
      <div class=\"error\">{{ error }}</div>
    {% endif %}

    <form id="survey-form" method="post" action="{{ url_for('submit') }}">
      <input type="hidden" name="csrf_token" value="{{ csrf_token }}" />
      <div class=\"q\">
        <div class=\"meta\">第 {{ current_index }} / {{ total_count }} 题 · {{ current.section_title }} / {{ current.group_title }}</div>
        <p class=\"q-title\">{{ current.number }}. {{ current.text }}</p>
        {% for opt in current.options %}
          <label class=\"opt\">
            <input type=\"radio\" name=\"{{ current.id }}\" value=\"{{ opt.key }}\" {% if answers.get(current.id)==opt.key %}checked{% endif %}>
            {{ opt.key }}. {{ opt.label }}
          </label>
        {% endfor %}
      </div>

      <div class=\"actions\">
        <button type=\"button\" class=\"nav-btn\" id=\"prev-btn\" {% if not prev_url %}disabled{% endif %}>上一题</button>
        <button type=\"button\" class=\"nav-btn\" id=\"next-btn\" {% if not next_url %}disabled{% endif %}>下一题</button>
      </div>
    </form>
  </div>

  <div class=\"floating-save\">
    <div class="save-status" id="save-status">未保存</div>
    <button type="button" class="save-btn" id="save-btn">保存</button>
    <button type="submit" form="survey-form" class="end-btn" id="end-btn">提前结束</button>
  </div>

  <aside class=\"sidebar\">
    <h4>目录</h4>
    <div class=\"progress\" id=\"progress-text\">已答 0/{{ total_count }}</div>
    {% for section in bank.sections %}
      <div class=\"catalog-group\">
        <div class=\"catalog-title\">{{ section.title }}</div>
        {% for group in section.groups %}
          <div class=\"catalog-title\">{{ group.title }}</div>
          <div class=\"catalog-list\">
            {% for q in group.questions %}
              <a class=\"catalog-item {% if q.id==current.id %}current{% endif %}\" data-qid=\"{{ q.id }}\" href=\"{{ url_for('index', q=q.index) }}\">{{ q.number }}</a>
            {% endfor %}
          </div>
        {% endfor %}
      </div>
    {% endfor %}
  </aside>

  <script>
    const questionIds = {{ question_ids | tojson }};
    const prevUrl = {{ prev_url | tojson }};
    const nextUrl = {{ next_url | tojson }};

    const answers = {{ answers | tojson }};

    function saveProgress(questionId, choice) {
      fetch("{{ url_for('progress') }}", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": "{{ csrf_token }}" },
        credentials: "same-origin",
        body: JSON.stringify({ question_id: questionId, choice: choice })
      }).catch(() => { /* ignore */ });
    }

    function updateCatalog(answers) {
      let count = 0;
      questionIds.forEach((qid) => {
        if (answers[qid]) count += 1;
      });
      document.getElementById("progress-text").textContent = `已答 ${count}/${questionIds.length}`;
      document.querySelectorAll(".catalog-item").forEach((el) => {
        const qid = el.getAttribute("data-qid");
        if (answers[qid]) {
          el.classList.add("answered");
        } else {
          el.classList.remove("answered");
        }
      });
    }

    document.querySelectorAll("input[type=radio]").forEach((radio) => {
      const qid = radio.name;
      if (answers[qid] && answers[qid] === radio.value) {
        radio.checked = true;
      }
      radio.addEventListener("change", () => {
        answers[qid] = radio.value;
        saveProgress(qid, radio.value);
        updateCatalog(answers);
      });
    });

    updateCatalog(answers);

    const prevBtn = document.getElementById("prev-btn");
    const nextBtn = document.getElementById("next-btn");
    if (prevBtn && prevUrl) {
      prevBtn.addEventListener("click", () => {
        window.location.href = prevUrl;
      });
    }
    if (nextBtn && nextUrl) {
      nextBtn.addEventListener("click", () => {
        window.location.href = nextUrl;
      });
    }

    const sidebar = document.querySelector(".sidebar");
    const storageKey = "survey_sidebar_scroll";
    const lastKey = "survey_sidebar_last_qid";
    if (sidebar) {
      const saved = localStorage.getItem(storageKey);
      if (saved !== null) {
        const pos = parseInt(saved, 10);
        if (!Number.isNaN(pos)) {
          sidebar.scrollTop = pos;
        }
      }

      const lastQid = localStorage.getItem(lastKey);
      const lastItem = lastQid ? sidebar.querySelector(`.catalog-item[data-qid="${lastQid}"]`) : null;
      const currentItem = sidebar.querySelector(".catalog-item.current");
      const focusItem = lastItem || currentItem;
      if (focusItem) {
        requestAnimationFrame(() => {
          focusItem.scrollIntoView({ block: "center" });
        });
      }

      sidebar.addEventListener("scroll", () => {
        localStorage.setItem(storageKey, String(sidebar.scrollTop));
      });

      sidebar.addEventListener("click", (event) => {
        const target = event.target;
        if (target && target.matches && target.matches(".catalog-item")) {
          const qid = target.getAttribute("data-qid");
          if (qid) {
            localStorage.setItem(lastKey, qid);
          }
        }
      });
    }

    document.getElementById("survey-form").addEventListener("submit", (event) => {
      const form = event.target;
      const existingInputs = new Set(
        Array.from(form.querySelectorAll("input[name]")).map((el) => el.name)
      );
      const container = document.createElement("div");
      container.style.display = "none";

      Object.entries(answers).forEach(([qid, val]) => {
        if (!val) return;
        if (existingInputs.has(qid)) return;
        const input = document.createElement("input");
        input.type = "hidden";
        input.name = qid;
        input.value = val;
        container.appendChild(input);
      });

      form.appendChild(container);
    });

    function setSaveStatus(text) {
      const el = document.getElementById("save-status");
      if (el) el.textContent = text;
    }

    async function saveAll() {
      try {
        setSaveStatus("保存中...");
        const res = await fetch("{{ url_for('save') }}", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": "{{ csrf_token }}" },
          credentials: "same-origin",
          body: JSON.stringify({ answers })
        });
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        const data = await res.json();
        if (!data || data.ok !== true) {
          throw new Error(data && data.error ? data.error : "save failed");
        }
        const now = new Date();
        const hh = String(now.getHours()).padStart(2, "0");
        const mm = String(now.getMinutes()).padStart(2, "0");
        const ss = String(now.getSeconds()).padStart(2, "0");
        setSaveStatus(`已保存 ${hh}:${mm}:${ss}`);
      } catch (e) {
        setSaveStatus("保存失败");
        alert("保存失败，请重试");
      }
    }

    const saveBtn = document.getElementById("save-btn");
    if (saveBtn) {
      saveBtn.addEventListener("click", () => {
        saveAll();
      });
    }
  </script>
</body>
</html>"""


THANK_YOU_HTML = """<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>已提交</title>
  <style>
    body { max-width: 720px; margin: 24px auto; padding: 0 16px; line-height: 1.5; }
    a { word-break: break-all; }
    .debug { margin-top: 18px; font-size: 12px; color: #666; }
  </style>
</head>
<body>
  <h1>保存成功</h1>
  <p>本次已保存 {{ answered_count }}/{{ total_count }} 题。</p>
  {% if stage_b and stage_b.ok %}
    <h3>奇点风险系数（阶段B：按指标去重）</h3>
    <p>奇点风险系数：<strong>{{ stage_b.overall_score }}/100</strong></p>
    <ul>
      {% for name, score in stage_b.category_scores.items() %}
        <li><strong>{{ name }}</strong>（{{ score }}/100）</li>
      {% endfor %}
    </ul>
  {% endif %}
  <p>作答已保存到本地文件：</p>
  <p><strong>{{ saved_path }}</strong></p>

  {% if report %}
    <h3>诊断报告导出</h3>
    {% if report.ok %}
      <p>报告编号：<strong>{{ report.report_id }}</strong></p>
      <ul>
        {% if report.html %}
          <li><a href="{{ url_for('artifact', filename=report.html) }}">下载 HTML 报告</a></li>
        {% endif %}
        {% if report.pdf %}
          <li><a href="{{ url_for('artifact', filename=report.pdf) }}">下载 PDF 报告</a></li>
        {% endif %}
        {% if report.png %}
          <li><a href="{{ url_for('artifact', filename=report.png) }}">下载网页截图 PNG</a></li>
        {% endif %}
      </ul>
      {% if report.warnings %}
        <p><em>导出提示：</em> {{ report.warnings | join('；') }}</p>
      {% endif %}
    {% else %}
      <p><strong>报告导出未完成：</strong> {{ report.error }}</p>
    {% endif %}
  {% endif %}
  <p><a href=\"{{ url_for('index') }}\">返回问卷</a></p>
  <p class=\"debug\">scoring_version: <strong>{{ scoring_version }}</strong></p>
</body>
</html>"""


def load_bank() -> dict[str, Any]:
    return json.loads(BANK_PATH.read_text(encoding="utf-8"))


def _progress_path(client_id: str) -> Path:
    return PROGRESS_DIR / f"web_progress_{client_id}.json"


def _load_progress(client_id: str) -> dict[str, str]:
    path = _progress_path(client_id)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

def _save_progress(client_id: str, answers: dict[str, str]) -> None:
    PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
    _progress_path(client_id).write_text(json.dumps(answers, ensure_ascii=False, indent=2), encoding="utf-8")

def _profile_path(client_id: str) -> Path:
    return PROGRESS_DIR / f"web_profile_{client_id}.json"

def _load_profile(client_id: str) -> dict[str, Any]:
    path = _profile_path(client_id)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

def _save_profile(client_id: str, profile: dict[str, Any]) -> None:
    PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
    _profile_path(client_id).write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")


def _planA_job_key(market: str, symbol: str, period: str) -> str:
  return f"{(market or '').strip().upper()}:{(symbol or '').strip().upper()}:{(period or '').strip()}"


def _parse_iso_dt(value: str | None) -> datetime | None:
  if not isinstance(value, str) or not value.strip():
    return None
  try:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
  except ValueError:
    return None


def _planA_is_stale_running(planA: dict[str, Any]) -> bool:
  if not isinstance(planA, dict):
    return False
  if planA.get("status") != PLAN_A_STATUS_RUNNING:
    return False
  if any(planA.get(k) for k in ("analysis_text", "pdf_path", "html_path", "json_path")):
    return False
  started_at = _parse_iso_dt(planA.get("started_at"))
  if started_at is None:
    return True
  now = datetime.now(timezone.utc)
  return (now - started_at).total_seconds() >= PLAN_A_RETRY_SECONDS


def _maybe_restart_planA(*, client_id: str, prof: dict[str, Any]) -> bool:
  planA = prof.get("listed_company_planA", {})
  if not _planA_is_stale_running(planA):
    return False
  market = str(prof.get("company_market") or "CN").strip().upper()
  symbol = str(prof.get("company_symbol") or "").strip().upper()
  period = str(prof.get("company_period") or "").strip()
  if not symbol or not period:
    return False

  job_key = _planA_job_key(market, symbol, period)
  report_id = f"ROWSTEP1-{(prof.get('surname') or '').strip()}{(prof.get('honorific') or '').strip()}"
  planA.update(
    {
      "status": PLAN_A_STATUS_RUNNING,
      "job_key": job_key,
      "started_at": datetime.now(timezone.utc).isoformat(),
      "market": market,
      "symbol": symbol,
      "period": period,
      "error": None,
    }
  )
  prof["listed_company_planA"] = planA
  _save_profile(client_id, prof)

  _start_planA_generation(
    client_id=client_id,
    market=market,
    symbol=symbol,
    period=period,
    report_id=report_id,
    job_key=job_key,
  )
  return True


def _planA_has_payload(planA: dict[str, Any]) -> bool:
  if not isinstance(planA, dict):
    return False
  for k in ("analysis_text", "pdf_path", "html_path", "json_path", "error"):
    if isinstance(planA.get(k), str) and planA.get(k):
      return True
  return False


def _ensure_planA_for_report(*, client_id: str, prof: dict[str, Any]) -> dict[str, Any] | None:
  planA = prof.get("listed_company_planA", {})
  if _planA_has_payload(planA):
    return planA

  market = str(prof.get("company_market") or "CN").strip().upper()
  symbol = str(prof.get("company_symbol") or "").strip().upper()
  period = str(prof.get("company_period") or "").strip()
  if not symbol or not period:
    return planA

  report_id = f"ROWSTEP1-{(prof.get('surname') or '').strip()}{(prof.get('honorific') or '').strip()}"
  completed_at = datetime.now(timezone.utc).isoformat()
  try:
    res = generate_planA_analysis(market=market, symbol=symbol, period=period, report_id=report_id)
  except Exception as e:  # pragma: no cover
    planA.update({"status": PLAN_A_STATUS_ERROR, "error": str(e), "completed_at": completed_at})
  else:
    planA = planA or {}
    if res.ok:
      planA.update(
        {
          "status": PLAN_A_STATUS_DONE,
          "analysis_text": res.analysis_text,
          "pdf_path": res.pdf_path,
          "html_path": res.html_path,
          "json_path": res.json_path,
          "error": None,
          "completed_at": completed_at,
        }
      )
    else:
      planA.update({"status": PLAN_A_STATUS_ERROR, "error": res.error, "completed_at": completed_at})

  prof["listed_company_planA"] = planA
  _save_profile(client_id, prof)
  return planA


def _start_planA_generation(
  *,
  client_id: str,
  market: str,
  symbol: str,
  period: str,
  report_id: str,
  job_key: str,
) -> None:
  def _worker() -> None:
    try:
      res = generate_planA_analysis(market=market, symbol=symbol, period=period, report_id=report_id)
    except Exception as e:  # pragma: no cover
      res = None
      err = str(e)
    else:
      err = None

    prof = _load_profile(client_id)
    current = prof.get("listed_company_planA", {})
    if current.get("job_key") != job_key:
      return

    completed_at = datetime.now(timezone.utc).isoformat()
    if res is None:
      current.update({"status": PLAN_A_STATUS_ERROR, "error": err, "completed_at": completed_at})
    elif res.ok:
      current.update(
        {
          "status": PLAN_A_STATUS_DONE,
          "analysis_text": res.analysis_text,
          "pdf_path": res.pdf_path,
          "html_path": res.html_path,
          "json_path": res.json_path,
          "error": None,
          "completed_at": completed_at,
        }
      )
    else:
      current.update({"status": PLAN_A_STATUS_ERROR, "error": res.error, "completed_at": completed_at})

    prof["listed_company_planA"] = current
    _save_profile(client_id, prof)

  thread = threading.Thread(target=_worker, daemon=True)
  thread.start()


def _get_or_create_client_id() -> str:
    cid = request.cookies.get(CLIENT_ID_COOKIE)
    if cid and isinstance(cid, str) and cid.strip():
        return cid.strip()
    return uuid4().hex


def iter_questions(bank: dict[str, Any]):
    for section in bank.get("sections", []):
        for group in section.get("groups", []):
            for q in group.get("questions", []):
                yield q


def iter_questions_with_context(bank: dict[str, Any]):
    for section in bank.get("sections", []):
        for group in section.get("groups", []):
            for q in group.get("questions", []):
                yield {
                    **q,
                    "section_title": section.get("title", ""),
                    "group_title": group.get("title", ""),
                }


def _option_label(q: dict[str, Any], key: str) -> str:
    for opt in q.get("options", []):
        if opt.get("key") == key:
            return str(opt.get("label") or "")
    return ""


def _choice_weight(choice: str, *, option_keys: list[str]) -> float:
  """Map a chosen option to a fractional weight.

  Rule requested:
    - 4 options => per step 25%: A=0.25, B=0.50, C=0.75, D=1.00
    - 2 options => per step 50%: A=0.50, B=1.00
  Generalized: weight = (rank_index starting at 1) / option_count
  """

  keys = [k.strip().upper() for k in (option_keys or []) if isinstance(k, str) and k.strip()]
  if not keys:
    return 1.0

  c = (choice or "").strip().upper()
  try:
    idx = keys.index(c) + 1
  except ValueError:
    # Fallback: A->1, B->2, ...
    if len(c) == 1 and "A" <= c <= "Z":
      idx = (ord(c) - ord("A")) + 1
    else:
      idx = 1

  if idx < 1:
    idx = 1
  if idx > len(keys):
    idx = len(keys)

  return round(idx / len(keys), 6)


_MAPPING_ITEM_RE = re.compile(r"^\s*(?P<code>[^（(]+?)\s*[（(].*[）)]\s*$")


def _mapping_code(item: str) -> str:
    """Return only the mapping code part, stripping the human name.

    Examples:
    - "M1-D1-T1-I1（决策权基尼系数）" -> "M1-D1-T1-I1"
    - "M1-D1-T1-I1(Decision...)" -> "M1-D1-T1-I1"
    - If no parentheses are present, returns the stripped string.
    """

    s = item.strip()
    m = _MAPPING_ITEM_RE.match(s)
    if m:
        return m.group("code").strip()
    return s


app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
logging.getLogger("werkzeug").setLevel(logging.ERROR)


# ---------------------------------------------------------------------------
# Security Middleware
# ---------------------------------------------------------------------------

def _sign_auth(client_id: str) -> str:
    """Create HMAC signature for authenticated session."""
    return hmac.new(_AUTH_HMAC_KEY, client_id.encode(), hashlib.sha256).hexdigest()


def _verify_auth_cookie() -> bool:
    """Check whether the request carries a valid auth cookie."""
    val = request.cookies.get(AUTH_COOKIE, "")
    if ":" not in val:
        return False
    cid, sig = val.rsplit(":", 1)
    expected = _sign_auth(cid)
    return hmac.compare_digest(sig, expected)


def _make_auth_cookie_value(client_id: str) -> str:
    return f"{client_id}:{_sign_auth(client_id)}"


def _check_rate_limit() -> bool:
    """Return True if the request should be allowed."""
    ip = request.remote_addr or "unknown"
    now = time.monotonic()
    with _rate_lock:
        dq = _rate_counters.setdefault(ip, collections.deque())
        # Purge entries older than 60s
        while dq and dq[0] < now - 60:
            dq.popleft()
        if len(dq) >= RATE_LIMIT_MAX:
            return False
        dq.append(now)
    return True


def _generate_csrf_token() -> str:
    """Generate a per-session CSRF token."""
    from flask import session
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(32)
    return session["_csrf"]


def _validate_csrf() -> bool:
    """Validate CSRF token from form data or X-CSRF-Token header."""
    from flask import session
    expected = session.get("_csrf", "")
    if not expected:
        return False
    token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
    return hmac.compare_digest(token, expected)


_LOGIN_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>请输入访问密码</title>
  <style>
    :root { --ink:#1f2328; --muted:#5b616a; --paper:#fbf7ef; --paper2:#f6efe1; --line: rgba(31,35,40,0.18); --accent:#8b2f2f; }
    body { margin:0; padding:0; background: linear-gradient(180deg, var(--paper), var(--paper2)); color: var(--ink);
      font-family: "Microsoft YaHei", "PingFang SC", Arial, sans-serif; line-height: 1.6; }
    .wrap { max-width: 400px; margin: 80px auto; padding: 0 16px; }
    .card { background: rgba(255,255,255,0.72); border: 1px solid rgba(31,35,40,0.10); border-radius: 12px; padding: 28px 24px; text-align: center; }
    h1 { margin: 0 0 6px; font-size: 20px; }
    p { margin: 8px 0 16px; color: var(--muted); font-size: 14px; }
    input[type=password] { width: 100%; padding: 12px 14px; margin-bottom: 12px; border-radius: 10px; border: 1px solid var(--line);
      background: rgba(255,255,255,0.9); font-size: 15px; box-sizing: border-box; }
    button { width: 100%; padding: 12px; border-radius: 10px; border: 1px solid rgba(139,47,47,0.55);
      background: rgba(139,47,47,0.10); cursor:pointer; font-size: 15px; }
    button:hover { background: rgba(139,47,47,0.18); }
    .error { margin-bottom: 12px; background: #fff4f4; border: 1px solid #f1c4c4; padding: 8px; border-radius: 8px; font-size: 13px; color: #a33; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>🔒 问卷访问验证</h1>
      <p>请输入管理员提供的访问密码</p>
      {% if error %}<div class="error">{{ error }}</div>{% endif %}
      <form method="post" action="/login">
        <input type="hidden" name="csrf_token" value="{{ csrf_token }}" />
        <input type="password" name="password" placeholder="请输入密码" autofocus required />
        <button type="submit">进入问卷</button>
      </form>
    </div>
  </div>
</body>
</html>"""


@app.before_request
def _security_before_request():
    """Enforce password auth and rate limiting."""
    # Rate limiting
    if not _check_rate_limit():
        return app.response_class("请求过于频繁，请稍后再试", status=429, mimetype="text/plain")

    # Allow login page itself without auth
    if request.path == "/login":
        return None

    # Check auth cookie
    if _verify_auth_cookie():
        request._survey_new_auth = False  # type: ignore[attr-defined]
        return None

    # Not authenticated — show login page
    return app.make_response((render_template_string(_LOGIN_HTML, error=None), 403))


@app.post("/login")
def login():
    """Handle password login form submission."""
    if not _validate_csrf():
        return app.response_class("CSRF validation failed", status=403, mimetype="text/plain")
    password = (request.form.get("password") or "").strip()
    if not hmac.compare_digest(password, ACCESS_PASSWORD):
        return app.make_response(
            (render_template_string(_LOGIN_HTML, error="密码错误，请重试"), 403)
        )
    # Password correct — set auth cookie and redirect to home
    client_id = _get_or_create_client_id()
    from flask import redirect
    response = redirect(url_for("index"))
    response.set_cookie(
        AUTH_COOKIE,
        _make_auth_cookie_value(client_id),
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        samesite="Lax",
    )
    response.set_cookie(CLIENT_ID_COOKIE, client_id, max_age=60 * 60 * 24 * 30, httponly=True, samesite="Lax")
    return response


@app.after_request
def _security_after_request(response):
    """Add security headers to every response."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'"
    )
    return response


# Inject csrf_token into Jinja templates
@app.context_processor
def _inject_csrf():
    return {"csrf_token": _generate_csrf_token()}


@app.get("/_debug/info")
def debug_info():
  """Lightweight runtime info — only available when SURVEY_DEBUG=1."""
  if not DEBUG_ENABLED:
    return app.response_class("Not Found", status=404, mimetype="text/plain")

  import sys
  import os

  try:
    from Step2.Constructor import singularity_engine as se
    se_file = os.path.abspath(getattr(se, "__file__", "") or "")
    scoring_version = getattr(se, "SCORING_VERSION", None)
  except Exception as e:  # pragma: no cover
    se_file = None
    scoring_version = None
    se = None
    err = repr(e)
  else:
    err = None

  payload = {
    "utc": datetime.now(timezone.utc).isoformat(),
    "python_executable": sys.executable,
    "python_version": sys.version,
    "cwd": os.getcwd(),
    "singularity_engine_file": se_file,
    "singularity_engine_scoring_version": scoring_version,
    "import_error": err,
  }

  return app.response_class(
    response=json.dumps(payload, ensure_ascii=False, indent=2),
    mimetype="application/json",
  )


def _normalize_surname(s: str) -> str:
  # Keep it conservative: strip spaces and common punctuation.
  if not isinstance(s, str):
    return ""
  v = s.strip()
  v = re.sub(r"\s+", "", v)
  v = v.replace("·", "")
  return v


@app.get("/intro")
def intro():
  client_id = _get_or_create_client_id()
  prof = _load_profile(client_id)
  _maybe_restart_planA(client_id=client_id, prof=prof)
  resp = render_template_string(
    INTRO_HTML,
    error=request.args.get("error"),
    surname=str(prof.get("surname") or ""),
    honorific=str(prof.get("honorific") or "先生"),
    has_company=str(prof.get("has_company") or "0"),
    market=str(prof.get("company_market") or "CN"),
    symbol=str(prof.get("company_symbol") or ""),
    period=str(prof.get("company_period") or ""),
    company_analysis=str((prof.get("listed_company_planA") or {}).get("analysis_text") or ""),
    company_pdf=str((prof.get("listed_company_planA") or {}).get("pdf_path") or ""),
    company_html=str((prof.get("listed_company_planA") or {}).get("html_path") or ""),
    company_json=str((prof.get("listed_company_planA") or {}).get("json_path") or ""),
    company_status=str((prof.get("listed_company_planA") or {}).get("status") or ""),
    company_error=str((prof.get("listed_company_planA") or {}).get("error") or ""),
  )
  response = app.make_response(resp)
  if request.cookies.get(CLIENT_ID_COOKIE) != client_id:
    response.set_cookie(CLIENT_ID_COOKIE, client_id, max_age=60 * 60 * 24 * 30, httponly=True, samesite="Lax")
  return response


@app.post("/intro")
def intro_submit():
  if not _validate_csrf():
    return app.response_class("CSRF validation failed", status=403, mimetype="text/plain")
  client_id = _get_or_create_client_id()
  surname = _normalize_surname(str(request.form.get("surname") or ""))
  honorific = str(request.form.get("honorific") or "").strip()
  has_company = str(request.form.get("has_company") or "0").strip()
  company_market = str(request.form.get("market") or "").strip().upper() or "CN"
  company_symbol = str(request.form.get("symbol") or "").strip().upper()
  company_period = str(request.form.get("period") or "").strip()

  if not surname:
    return app.make_response(("", 302, {"Location": url_for("intro", error="请填写姓氏") }))
  if honorific not in {"先生", "女士"}:
    honorific = "先生"

  # Listed company validation (only when user selects 'has')
  if has_company == "1":
    if company_market not in {"CN", "US"}:
      return app.make_response(("", 302, {"Location": url_for("intro", error="市场需为 CN 或 US") }))
    if not company_symbol:
      return app.make_response(("", 302, {"Location": url_for("intro", error="已选择有上市公司，请填写代码") }))
    if not re.fullmatch(r"\d{8}", company_period):
      return app.make_response(("", 302, {"Location": url_for("intro", error="报告期需为 YYYYMMDD（如20241231）") }))

  existing_prof = _load_profile(client_id)
  existing_planA = existing_prof.get("listed_company_planA", {})

  prof = {
    "surname": surname,
    "honorific": honorific,
    "respondent_display": f"{surname}{honorific}",
    "has_company": has_company,
    "company_market": company_market,
    "company_symbol": company_symbol,
    "company_period": company_period,
  }

  # If user provided a listed company, generate a PlanA analysis.
  start_planA_job = False
  planA_job_params: dict[str, str] = {}

  if has_company == "1" and company_symbol and company_period:
    job_key = _planA_job_key(company_market, company_symbol, company_period)
    report_id = f"ROWSTEP1-{surname}{honorific}"

    reuse_existing = False
    if existing_planA and existing_planA.get("job_key") == job_key:
      status = existing_planA.get("status")
      if status == PLAN_A_STATUS_DONE:
        reuse_existing = True
      elif status == PLAN_A_STATUS_RUNNING and not _planA_is_stale_running(existing_planA):
        reuse_existing = True

    if reuse_existing:
      prof["listed_company_planA"] = existing_planA
    else:
      prof["listed_company_planA"] = {
        "status": PLAN_A_STATUS_RUNNING,
        "job_key": job_key,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "market": company_market,
        "symbol": company_symbol,
        "period": company_period,
      }
      start_planA_job = True
      planA_job_params = {
        "client_id": client_id,
        "market": company_market,
        "symbol": company_symbol,
        "period": company_period,
        "report_id": report_id,
        "job_key": job_key,
      }
  else:
    prof.pop("listed_company_planA", None)

  _save_profile(client_id, prof)

  if start_planA_job:
    _start_planA_generation(**planA_job_params)

  response = app.make_response(("", 302, {"Location": url_for("index") }))
  response.set_cookie(INTRO_OK_COOKIE, "1", httponly=True, samesite="Lax")
  if request.cookies.get(CLIENT_ID_COOKIE) != client_id:
    response.set_cookie(CLIENT_ID_COOKIE, client_id, max_age=60 * 60 * 24 * 30, httponly=True, samesite="Lax")
  return response


@app.get("/intro/skip")
def intro_skip():
  client_id = _get_or_create_client_id()
  prof = {
    "surname": "某",
    "honorific": "先生",
    "respondent_display": "某先生",
    "has_company": "0",
    "company_market": "CN",
    "company_symbol": "",
    "company_period": "",
  }
  _save_profile(client_id, prof)

  response = app.make_response(("", 302, {"Location": url_for("index") }))
  response.set_cookie(INTRO_OK_COOKIE, "1", httponly=True, samesite="Lax")
  if request.cookies.get(CLIENT_ID_COOKIE) != client_id:
    response.set_cookie(CLIENT_ID_COOKIE, client_id, max_age=60 * 60 * 24 * 30, httponly=True, samesite="Lax")
  return response


@app.get("/")
def index():
  client_id = _get_or_create_client_id()
  prof = _load_profile(client_id)
  _maybe_restart_planA(client_id=client_id, prof=prof)

  # Always show the intro module unless just completed in this session.
  if request.cookies.get(INTRO_OK_COOKIE) != "1":
    return app.make_response(("", 302, {"Location": url_for("intro")}))

  bank = load_bank()
  answers: dict[str, str] = _load_progress(client_id)
  error = request.args.get("error")

  flat = list(iter_questions_with_context(bank))
  total_count = len(flat)

  q_index_raw = request.args.get("q", "1")
  try:
    q_index = int(q_index_raw)
  except ValueError:
    q_index = 1
  if q_index < 1:
    q_index = 1
  if q_index > total_count:
    q_index = total_count if total_count else 1

  current = flat[q_index - 1] if flat else {}
  if isinstance(current, dict):
    mappings = current.get("mappings")
    if isinstance(mappings, list):
      current["mapping_codes"] = [_mapping_code(x) for x in mappings if isinstance(x, str) and x.strip()]
    else:
      current["mapping_codes"] = []

  id_to_index = {q["id"]: i + 1 for i, q in enumerate(flat)}
  for section in bank.get("sections", []):
    for group in section.get("groups", []):
      for q in group.get("questions", []):
        q["index"] = id_to_index.get(q.get("id"), 1)

  prev_url = url_for("index", q=q_index - 1) if q_index > 1 else None
  next_url = url_for("index", q=q_index + 1) if q_index < total_count else None

  question_ids = [q["id"] for q in flat]
  resp = render_template_string(
    HTML,
    bank=bank,
    answers=answers,
    error=error,
    current=current,
    current_index=q_index,
    total_count=total_count,
    prev_url=prev_url,
    next_url=next_url,
    question_ids=question_ids,
    profile=prof,
  )
  response = app.make_response(resp)
  if request.cookies.get(CLIENT_ID_COOKIE) != client_id:
    response.set_cookie(CLIENT_ID_COOKIE, client_id, max_age=60 * 60 * 24 * 30, httponly=True, samesite="Lax")
  return response


@app.post("/progress")
def progress():
    if not _validate_csrf():
        return {"ok": False, "error": "CSRF validation failed"}, 403
    client_id = _get_or_create_client_id()
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return {"ok": False, "error": "invalid json"}, 400

    qid = payload.get("question_id")
    choice = payload.get("choice")
    if not isinstance(qid, str) or not qid.strip():
        return {"ok": False, "error": "missing question_id"}, 400
    if not isinstance(choice, str) or not choice.strip():
        return {"ok": False, "error": "missing choice"}, 400

    answers = _load_progress(client_id)
    answers[qid] = choice
    _save_progress(client_id, answers)

    response = app.make_response({"ok": True})
    if request.cookies.get(CLIENT_ID_COOKIE) != client_id:
        response.set_cookie(CLIENT_ID_COOKIE, client_id, max_age=60 * 60 * 24 * 30, httponly=True, samesite="Lax")
    return response


@app.post("/save")
def save():
    if not _validate_csrf():
        return {"ok": False, "error": "CSRF validation failed"}, 403
    client_id = _get_or_create_client_id()
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return {"ok": False, "error": "invalid json"}, 400

    answers_in = payload.get("answers")
    if not isinstance(answers_in, dict):
        return {"ok": False, "error": "missing answers"}, 400

    answers_out = {k: v for k, v in answers_in.items() if k.strip() and v.strip()}

    _save_progress(client_id, answers_out)
    response = app.make_response({"ok": True})
    if request.cookies.get(CLIENT_ID_COOKIE) != client_id:
        response.set_cookie(CLIENT_ID_COOKIE, client_id, max_age=60 * 60 * 24 * 30, httponly=True, samesite="Lax")
    return response


@app.post("/submit")
def submit():
  if not _validate_csrf():
    return app.response_class("CSRF validation failed", status=403, mimetype="text/plain")
  client_id = _get_or_create_client_id()
  bank = load_bank()
  form = request.form

  prof = _load_profile(client_id)
  surname = _normalize_surname(str(prof.get("surname") or ""))
  honorific = str(prof.get("honorific") or "").strip()
  respondent_display = str(prof.get("respondent_display") or "").strip()
  has_company = str(prof.get("has_company") or "0").strip()
  company_market = str(prof.get("company_market") or "").strip().upper()
  company_symbol = str(prof.get("company_symbol") or "").strip().upper()
  company_period = str(prof.get("company_period") or "").strip()
  listed_company_planA = prof.get("listed_company_planA", {})

  questions_by_id = {q["id"]: q for q in iter_questions(bank)}

  # New export schema (per your request): only collect user choice + mapping codes.
  answers_out: list[dict[str, Any]] = []
  code_weights: dict[str, float] = {}
  answered_count = 0

  flat = list(iter_questions_with_context(bank))
  total_count = len(flat)

  if has_company == "1":
    listed_company_planA = _ensure_planA_for_report(client_id=client_id, prof=prof)

  for q in flat:
    qid = q["id"]
    choice = form.get(qid) or ""
    if not choice:
      continue

    answered_count += 1
    src = questions_by_id.get(qid, q)

    # Determine per-question fractional weight from option count
    option_keys = [opt.get("key", "").strip().upper() for opt in src.get("options", []) if opt.get("key")]
    cw = _choice_weight(choice, option_keys=option_keys)
    
    # Extract codes and aggregate code_weights functionally
    code_list = [_mapping_code(item) for item in src.get("mappings", []) if item.strip()]
    codes = [c for c in code_list if c]
    for code in codes:
        code_weights[code] = float(code_weights.get(code, 0.0)) + float(cw)

    answers_out.append(
      {
        "question_id": qid,
        "question_number": q.get("number"),
        "choice": choice,
        "choice_weight": cw,
        "option_count": len(option_keys),
        "codes": codes,
      }
    )

  completed_at = datetime.now(timezone.utc)
  payload = {
    "completed_at": completed_at.isoformat(),
    "bank_file": str(BANK_PATH.name),
    "total_count": total_count,
    "answered_count": answered_count,
    "answers": answers_out,
    "code_weights": code_weights,
    "has_company": has_company,
    "company_market": company_market,
    "company_symbol": company_symbol,
    "company_period": company_period,
  }

  if has_company == "1":
    payload["listed_company_planA"] = listed_company_planA or {}

  if surname:
    if honorific not in {"先生", "女士"}:
      honorific = "先生"
    if not respondent_display:
      respondent_display = f"{surname}{honorific}"
    payload["respondent"] = {
      "surname": surname,
      "honorific": honorific,
      "display": respondent_display,
    }
    # Default family rendering values for Step4, unless caller already provided them.
    payload.setdefault("family_name", f"{surname}家族")
    payload.setdefault("family_abbr", surname)
    payload.setdefault("family_badge_text", surname)

  stage_a = compute_singularity_with_trace(answers=answers_out, code_weights=code_weights)
  stage_b = compute_singularity_stage_b_with_trace(answers=answers_out)
  payload["singularity_stage_a"] = stage_a
  payload["singularity_stage_b"] = stage_b
  # Keep legacy key for older tooling; point it to Stage A by default.
  payload["singularity"] = stage_a

  RESPONSES_DIR.mkdir(parents=True, exist_ok=True)
  out_name = f"web_response_{completed_at.strftime('%Y%m%d_%H%M%S')}.json"
  out_path = RESPONSES_DIR / out_name

  report: dict[str, Any] | None = None
  try:
    from Step4.report_generator import generate_report_artifacts

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    # Step4 doc suggests a visible report number like "NO.XX-YYYY-NNN"; we use a deterministic timestamp form.
    report_id = f"NO.WEB-{completed_at.strftime('%Y%m%d')}-{completed_at.strftime('%H%M%S')}-{client_id[:4].upper()}"
    artifacts = generate_report_artifacts(
      payload=payload,
      response_json_path=out_path,
      output_dir=REPORTS_DIR,
      report_id=report_id,
      title=f"{payload.get('family_name', 'XXX家族')}･永续传承诊断报告",
    )
    report = {
      "ok": bool(artifacts.ok),
      "report_id": artifacts.report_id,
      "html": artifacts.html_name,
      "pdf": artifacts.pdf_name,
      "png": artifacts.png_name,
      "warnings": artifacts.warnings,
      "error": artifacts.error,
    }
    payload["report_artifacts"] = report
  except Exception as e:
    report = {"ok": False, "error": f"report generation failed: {e}"}
    payload["report_artifacts"] = report

  out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

  # User chose to finish: clear server-side progress for this client.
  try:
    _progress_path(client_id).unlink(missing_ok=True)
  except OSError:
    pass
  try:
    _profile_path(client_id).unlink(missing_ok=True)
  except OSError:
    pass

  return render_template_string(
    THANK_YOU_HTML,
    saved_path="已保存到服务器",
    answered_count=answered_count,
    total_count=total_count,
    stage_a=stage_a,
    stage_b=stage_b,
    report=report,
    scoring_version=SCORING_VERSION,
  )


@app.get("/artifacts/<path:filename>")
def artifact(filename: str):
    # Security: validate filename to prevent path traversal
    if ".." in filename or filename.startswith("/") or filename.startswith("\\"):
        return app.response_class("Forbidden", status=403, mimetype="text/plain")
    # Only allow known safe extensions
    allowed_ext = {".html", ".pdf", ".png", ".json"}
    ext = os.path.splitext(filename)[1].lower()
    if ext not in allowed_ext:
        return app.response_class("Forbidden", status=403, mimetype="text/plain")
    return send_from_directory(str(REPORTS_DIR), filename, as_attachment=True)


def main() -> None:
    if not BANK_PATH.exists():
        raise SystemExit(f"Missing {BANK_PATH}. Run Build_question_bank.py first.")
    port = int(os.environ.get("PORT", "5000"))
    print(f"\n{'=' * 56}")
    print(f"  [锁] 访问密码: {ACCESS_PASSWORD}")
    print(f"  本地链接: http://localhost:{port}/")
    print(f"  Debug 模式: {'ON' if DEBUG_ENABLED else 'OFF'}")
    print(f"  速率限制: {RATE_LIMIT_MAX} 次/分钟")
    print(f"{'=' * 56}\n")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
