# Productionization 8-hour plan

Date: 2026-05-31
Branch: `fix/multilevel-cascade-regression`

## Refined definition of done

A pipeline is production-ready when all of these are true:

1. `pipelines/registry.json` passes `check_registry_consistency.py --strict-artifacts`.
2. Every `ship-*` registry role has an exact committed `tests/quality_gates/runs/<hash>/run.json` receipt with `verdict=PASS`.
3. Release candidates additionally pass `audit_ship_pipelines.py --strict`: current `gates.json` hash and a `docs/claims_log.md` entry for the same pipeline/run hash.
4. Operations dashboards are generated from committed data or explicitly marked local-only.
5. CI protects the production metadata path and is green after each productionization commit.
6. Any visual-quality claim still follows the root `CLAUDE.md` rule: run the full gate and inspect the worst visual diff before claiming.

## 8-hour burn-down

| Timebox | Work | Output |
|---:|---|---|
| 0:00-1:00 | Lock production definition and audit scope. | This plan plus README alignment. |
| 1:00-2:30 | Harden `audit_ship_pipelines.py` so it ignores untracked local runs by default and has strict release mode. | CI-safe audit plus strict burn-down list. |
| 2:30-3:30 | Make ship receipts reproducible: commit missing run receipts or demote roles that are not real ship candidates. | No `ship-*` role depends on scratch output. |
| 3:30-4:30 | Add CI/docs wiring for the ship audit once default mode is clean. | CI catches missing/failed committed ship receipts. |
| 4:30-5:30 | Dashboard production pass: verify ops matrix generation, document local-only artifact inputs, and add a smoke check for bad placeholders. | Dashboard is reproducible and auditable. |
| 5:30-6:30 | UPRESABLE handoff pass: document primary artifact paths, bottlenecks, and release checklist. | Clear handoff for size/timing/FPS/storage claims. |
| 6:30-7:30 | Chroma artifact decision: locate final Lab-chroma checkpoint or record it as blocked; do not register without artifact/hash/gate. | Chroma path has a concrete next action. |
| 7:30-8:00 | Final validation: run strict registry, ship audit, dashboard smoke, push, and monitor CI. | Green branch with a short residual-risk list. |

## Current strict burn-down

As of this plan, strict ship audit is expected to fail for older ship receipts
whose `gates_sha` predates the current `gates.json`, and for ship roles that
have not been logged through `run_gate.py --claim`. That is intentional: default
audit protects CI; strict audit is the production release checklist.
