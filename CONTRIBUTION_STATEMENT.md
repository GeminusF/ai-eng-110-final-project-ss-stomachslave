# Contribution Statement

**Team:** StomachSlave  
**Topic:** Topic 2 - AI Food Analyzer  
**Repository:** [https://github.com/GeminusF/ai-eng-110-final-project-ss-stomachslave](https://github.com/GeminusF/ai-eng-110-final-project-ss-stomachslave)  
**Final tag:** `v1.0-final`  
**Submission date:** 2026-05-24

---

## Basis for this statement

This statement is based on the current local git history across local refs,
including the latest pushed GitHub branches, grouped by known author aliases:

- Fereh Feyzullayev: `GeminusF` and `Fereh Feyzullayev`
- Milana Karimova: `milanakarimova` and `milana veda`
- Nicat Agayev: `Nicat-Agayev`

Local git history currently shows 48 commits after grouping aliases:
Fereh 17, Milana 16, and Nicat 15. Review metadata is not available from local
git history, so the reviewed-PR fields are intentionally left blank for the
team to complete from GitHub.

---

## Fereh Feyzullayev (`@GeminusF`)

**Owned (sole author or primary implementer of these files / PRs):**

- `foodanalyzer/offline.py`
- `foodanalyzer/providers/openrouter.py`
- `foodanalyzer/services/ai_service.py`
- `foodanalyzer/services/retry.py`
- `foodanalyzer/services/nutrition_cache.py`
- `foodanalyzer/services/rate_limiter.py`
- `foodanalyzer/concurrency/pipeline.py`
- `foodanalyzer/core/analyzer.py`
- `foodanalyzer/logging_config.py`
- `tests/test_openrouter.py`
- `tests/test_ai_service.py`
- `tests/test_cache.py`
- `tests/test_pipeline.py`
- `.github/workflows/ci.yml`
- `.github/pull_request_template.md`
- PRs owned: #3, #4, #5, #10

**Co-owned (paired or substantially edited):**

- Overall AI boundary and service wiring with the CLI/API integration.
- Test strategy for offline provider behavior, cache behavior, and analyzer edge cases.
- CI and branch-protection support after the core application was stable.

**Reviewed (PRs reviewed and merged):**

- PRs reviewed: #1, #2, #6, #9, #11

**Approximate share of commits:** 35.4%

---

## Milana Karimova (`@milanakarimova`)

**Owned:**

- `Dockerfile`
- `docker-compose.yml`
- `README.md` initial structure and final template-based rewrite
- `foodanalyzer/models.py`
- `foodanalyzer/storage/repository.py`
- `foodanalyzer/storage/schema.sql`
- `foodanalyzer/cli.py`
- `foodanalyzer/__init__.py`
- `foodanalyzer/__main__.py`
- `scripts/bench.py`
- `report/report.tex`
- `report/report.pdf`
- `tests/test_repository.py`
- `tests/test_cli.py`
- PRs owned: #2, #7, #11

**Co-owned:**

- End-to-end CLI analyzer construction with the AI service, storage, and cache layers.
- Docker and local run documentation with project setup commands.
- Analysis result model design used by CLI, API, web UI, and storage.
- Final documentation alignment between README, report, benchmark evidence, and current app behavior.

**Reviewed:**

- PRs reviewed: #3, #5, #8, #10

**Approximate share of commits:** 33.3%

---

## Nicat Agayev (`@Nicat-Agayev`)

**Owned:**

- `foodanalyzer/config.py`
- `foodanalyzer/utils/images.py`
- `foodanalyzer/api.py`
- `foodanalyzer/web_ui.py`
- `tests/test_config.py`
- `tests/test_images.py`
- `tests/test_api.py`
- `tests/test_web_ui.py`
- PRs owned: #1, #6, #8, #9

**Co-owned:**

- Upload validation and safe image handling used by both API and HTMX flows.
- User-facing analysis, history, thumbnail, and error-rendering workflows.
- FastAPI integration with the shared analyzer service and repository interface.

**Reviewed:**

- PRs reviewed: #4, #7

**Approximate share of commits:** 31.3%

---

## AI tool disclosure

We used AI coding assistants as collaborators. Each item lists the module or
file area, the assistant, and how the team handled the output.

| Module / file | Assistant | What we did with it |
|---|---|---|
| `README.md` and `report/report.tex` | ChatGPT / Codex | Drafted structure and wording; team checked claims against the current code, tests, benchmark output, and assignment rules. |
| `CODEX_RULES.md` | ChatGPT / Codex | Organized assignment constraints and team rules into a short checklist; team used it as a guardrail while keeping implementation decisions tied to the course brief and current code. |
| `plan.md` and `git_plan.md` | ChatGPT / Codex | Helped structure planning notes, work order, and git workflow reminders; these documents guided coordination and documentation, not automatic generation of the application. |
| `foodanalyzer` implementation support | ChatGPT / Codex and editor AI assistants | Used for implementation and debugging suggestions; team reviewed, adapted, and tested the resulting code before keeping it. |
| Tests and documentation | ChatGPT / Codex and editor AI assistants | Suggested candidate test cases and documentation wording; final tests/docs were checked against local pytest and coverage results. |

We affirm that we can defend every line of code in this repository during the
oral defense. "The AI wrote it" is not an answer we will use.

---

## Signatures

By signing below, we affirm that:

- The contributions described above are accurate.
- The commit percentages reflect actual work, not artificially split commits.
- Every line of code in the repository can be defended by at least one team member.
- AI assistant usage has been disclosed as described above.

| Member | Signature | Date |
|---|---|---|
| Fereh Feyzullayev | FF | 24.05.2026 |
| Milana Karimova | MK | 24.05.2026 |
| Nicat Agayev | NA | 24.05.2026 |
