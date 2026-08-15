.PHONY: seed dev-bank dev-ui test lint deploy demo

PYTHON := .venv/bin/python

seed:
	$(PYTHON) -m data.generator.main --load

dev-bank:
	BANK=$${BANK:-alpha} $(PYTHON) -m services.bank.api.main

dev-ui:
	cd ui && npm run dev

test:
	.venv/bin/pytest -q

lint:
	.venv/bin/ruff check . && .venv/bin/ruff format --check .

deploy:
	gcloud builds submit --config infra/cloudbuild.yaml

demo:
	$(PYTHON) -m scripts.run_demo
