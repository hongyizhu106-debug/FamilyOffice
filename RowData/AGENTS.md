# AGENTS.md (RowData subsystem override)

Rules here apply to all files under `RowData/`.

---

## Local architecture

- Entry point: `MainController/MacinController.py` → starts Flask on `0.0.0.0:5000`.
- Survey flow: `/intro` → `/` (question pages) → `/submit` → thank-you page.
- Persistence: JSON files in `Rubbish/` (progress, profile, response, reports).

## Extra restrictions

- Do not change the cookie names (`survey_client_id`, `survey_auth`, `survey_intro_ok`) without updating every consumer.
- Do not change the `/artifacts/` path-safety check (prevents directory traversal).
- Do not change `SCORING_VERSION` in `singularity_engine.py` without bumping the version string.
- Do not modify `Question_bank.json` question `id` fields — they are used as form field names and progress keys.

## Required verification for this subsystem

- Start service and complete a full survey submission end-to-end.
- Check that a `web_response_*.json` file appears in `RowData/Rubbish/`.
- For scoring changes, compare `singularity_stage_a.overall_score` before and after with the same answers.
