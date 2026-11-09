# AGENTS.md

How to work in this repository, for people and coding agents.

## Fast feedback

```bash
make lint        # ruff format --check and ruff check
make test        # all Python tests; generates a few drawings in a temp folder, reads one scan with Tesseract
make web-test    # vitest for the dashboard
make lock-check  # the held-out lock still verifies (after `make data`)
make data        # generate the development and held-out drawings into data/ (about a minute)
make dev         # read every development drawing and score it (about 20 minutes, mostly OCR)
make report      # RESULTS.md and web/public/data/dashboard.json from reports/*.json
make api         # FastAPI on :8000
```

`python scripts/train_regions.py loo` retrains the region detector five times, leaving one development layout out
each time (about 30 minutes on 2 cores); `final` trains on all of them and writes `models/regions.pt`.

## Invariants (tests enforce them)

1. **Nothing that serves reads the truth.** `dia.world` generates drawings and their truth; `dia.perceive`,
   `dia.engineering`, `dia.delivery` and the API never import it or read `data/truth/`
   (`test_nothing_that_serves_reads_the_truth`). Only `scripts/evaluate.py` and `scripts/showcase.py` compare.
2. **Only approved values reach the ERP.** A field goes into the import file only if it cleared the routing
   threshold with its value check passed, or an engineer approved it; export is blocked until the required fields
   are there, and records carry an idempotency key (`test_export_is_blocked_until_required_fields_are_approved`,
   `test_erp_records_are_fixed_width_and_idempotent`).
3. **The model reads; code decides.** An LLM may propose note requirements, but one whose quoted text is not in the
   notes, or whose standard is unknown, is rejected with a reason (`test_llm_requirements_pass_the_validator_or_are_rejected`).
   Feasibility is plain code over `config/plant.yaml`.
4. **Limits come from the standards.** ISO 286-1 and ISO 2768-1 values are tables in `dia/standards`, tested
   against published values; a class outside them is refused, not guessed.
5. **Settings in config.** Every threshold is in `config/dia.toml`; the plant's processes and stock are in
   `config/plant.yaml`; the dashboard's sizes and colours are in `web/src/theme/tokens.ts`.
6. **Generated reports.** `RESULTS.md` and `web/public/data/*` come from scripts; CI regenerates them and fails on
   a difference.

## The held-out rule

Three customer layouts (`kranich`, `meridian`, `tessaro` in `config/dia.toml`) were written with the generator
before the reader existed and have never been used to build, train or tune anything: the label vocabulary, the
region detector and the routing threshold all come from the five development layouts.

Before the held-out run, everything that decides what the reader reads (perception and engineering code, the
standards tables, the trained detector, both config files, and the held-out index) is pinned in
`config/heldout.lock` with `scripts/lock.py`. `scripts/evaluate.py heldout` checks the lock, refuses to run a
second time, and its output (`reports/heldout.json`) is published as it came out. Changing the reader after that
needs a new set of unseen layouts.

## Layout

```
config/            dia.toml (every setting), plant.yaml (processes, stock), heldout.lock
src/dia/world/     the simulated customers: layouts, parametric parts, rendering, scanning, revisions (truth side)
src/dia/perceive/  page loading and scan registration, region detector, OCR, title block, dimensions, tables
src/dia/engineering/ tolerances, revision compare, feasibility, notes (rules + LLM behind a validator)
src/dia/standards/ ISO 286-1 and ISO 2768-1 tables
src/dia/delivery/  routing, legacy ERP export, the intake desk service
scripts/           train_regions, evaluate, showcase, report, lock
models/regions.pt  the trained region detector
web/               the dashboard (React, TypeScript, Framer Motion)
deploy/k8s/        deployment and service
```
