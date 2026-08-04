# AGENTS.md

This file defines durable instructions for Codex and other coding agents working in this repository.

## Project mission

This repository is the **FamilyOffice 家族诊断问卷与报告系统**. It collects structured family governance and risk indicator data through a web survey, scores it with the Singularity Engine, and generates diagnostic PDF/HTML reports.

Primary users: family office advisors and their clients.

Most important quality goals: **data integrity, scoring correctness, report accuracy, security**.

---

## Repository structure

```
FamilyOffice/
├─ AGENTS.md                        # This file
├─ 一键启动-Web版问卷与报告.bat       # One-click launcher (opens browser to :5000)
├─ 停止问卷.ps1                      # Stop the survey service
├─ tools/                           # Utility scripts and documentation
│  ├─ render_math.py
│  ├─ render_math_concepts.py
│  └─ Codex企业级提示词与约束框架.md
├─ FamilyOfficeVersion2/            # Reference data (jump.json, questions.json)
├─ MyFinancialProject/              # MCP financial data tools (separate concern)
└─ RowData/                         # Core survey/report system
   ├─ Start_Web.bat
   ├─ MainController/MacinController.py   # Entry point, starts Flask on :5000
   ├─ Step1/Constructor/Web_survey_app.py # Flask app (auth, survey, submit)
   ├─ Step1/Data/Question_bank.json       # 622 indicator questions
   ├─ Step1/Data/jump.json               # 2-level skip logic (dim/type gates)
   ├─ Step2/Constructor/singularity_engine.py  # Scoring engine
   ├─ Step3/                        # PDF text extraction
   └─ Step4/report_generator.py     # Report artifact generation
```

---

## Architectural boundaries

- **Web layer** (`Web_survey_app.py`): HTTP routing, auth, CSRF, rate limiting, session cookies. Must not contain scoring or report logic.
- **Scoring layer** (`singularity_engine.py`): Pure computation from answer weights to singularity scores. Must not perform I/O or know about HTTP.
- **Report layer** (`Step4/report_generator.py`): Renders HTML/PDF from a scored payload dict. Must not modify the payload.
- **Data layer** (`Step1/Data/`): JSON source files are the single source of truth for questions and jump logic. Do not generate or infer question content.

---

## Critical rules

- **Never invent or alter indicator data.** Question text, option keys, and mapping codes must come from `Question_bank.json` exactly.
- **Never invent or alter scoring weights.** Weight computation lives in `_choice_weight()` and `singularity_engine.py`. Changes require before/after examples.
- **Never weaken security controls.** Do not lower rate limits, remove CSRF validation, weaken HMAC auth, or bypass the login gate.
- **Never delete user response files** without an explicit user instruction. The `Rubbish/` directory stores client submissions.
- **Preserve the `jump.json` gate structure.** Filter questions route users; changing gate logic changes which indicator questions are shown.

---

## Working agreements

- Inspect relevant files before editing.
- Make the smallest change that satisfies the request.
- Do not refactor code unrelated to the current task.
- Do not add new Python packages without explicit approval.
- Do not change the JSON schema of `Question_bank.json` or `jump.json` without updating all consumers.
- If a change affects scoring output, show old value → new value with a sample payload.

---

## Implementation rules

- Follow existing patterns in `Web_survey_app.py` (Flask routes, template strings, cookie handling).
- Data validation happens at HTTP boundaries (`Web_survey_app.py`), not inside the scoring engine.
- New routes must include CSRF validation (`_validate_csrf()`).
- New routes must respect the auth gate (`_verify_auth_cookie()`).
- Secrets and passwords must never appear in logs or HTTP responses.

---

## Verification

Before finishing, run the narrowest relevant check:

- Start the service: `cd RowData && Step1\Env\Scripts\python.exe MainController\MacinController.py`
- Navigate to `http://127.0.0.1:5000/` and verify the login page appears.
- For scoring changes: run `Step2/Constructor/singularity_engine.py` standalone with a sample payload and compare output.

If a check cannot be run, report: the exact command, why it was skipped, and what risk remains.

---

## Security rules

- Do not print `ACCESS_PASSWORD` or any cookie value in logs.
- Do not add endpoints that bypass `_security_before_request()`.
- Do not allow path traversal in `/artifacts/<filename>` — the existing safeguard must be preserved.
- Rate limit (`RATE_LIMIT_MAX`) must not be set below 60 req/min in production config.

---

## Git and release rules

- Never commit directly to `main`.
- Do not commit `Rubbish/` response files or `web_progress_*.json` client state.
- Do not commit `.env` files or files containing `ACCESS_PASSWORD` overrides.
- Summarize changed files and verification in the final response.

---

## Subsystem notes

### `RowData/Step1/Constructor/Web_survey_app.py`
Central file. Contains Flask app, all routes, HTML templates (inline strings), auth, CSRF, rate limiting. Changes here have the widest blast radius — prefer minimal edits.

### `RowData/Step2/Constructor/singularity_engine.py`
Pure scoring logic. No Flask imports. Any change requires a numeric regression check.

### `RowData/Step1/Data/jump.json`
Defines 2-level (dimension → type) skip gates. Structure: `module → dimensions[] → {filter_question, types[]} → {filter_question, indicators[]}`. Indicators are codes like `M1-D1-T1-I1` that map to questions in `Question_bank.json`.

---

## Final response format

End with:
- Summary of what changed.
- Files changed.
- Verification performed or skipped (with reason).
- Known risks or follow-ups.
