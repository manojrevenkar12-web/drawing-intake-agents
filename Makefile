PY ?= python3
export PYTHONPATH := src

.PHONY: check lint test web-test data train dev heldout bench report lock-check api
check: lint lock-check test web-test
lint:
	ruff format --check src tests scripts && ruff check src tests scripts
test:
	$(PY) -m pytest -q
web-test:
	cd web && npx vitest run
lock-check:
	grep -v '^#' config/heldout.lock | sha256sum -c --quiet -
data:
	$(PY) -m dia.world.dataset
train:
	$(PY) scripts/train_regions.py final
dev:
	$(PY) scripts/evaluate.py dev
heldout:
	$(PY) scripts/evaluate.py heldout
report:
	$(PY) scripts/report.py
api:
	$(PY) -m uvicorn dia.api:app --reload
