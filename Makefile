.PHONY: seed dev-bank dev-ui test lint deploy demo judge

PYTHON := .venv/bin/python

seed:
	$(PYTHON) -m data.generator.main --load

# One fleet locally, on :8080. BANK selects which bank's identity, policy and ledger it uses.
dev-bank:
	BANK=$${BANK:-alpha} $(PYTHON) -m uvicorn services.bank.api.main:app --reload --port 8080

# Mission control locally, on :8081. Needs BANK_<X>_URL set, or it will look for the fleets
# through the Cloud Run API and be refused — see services/ui/main.py.
dev-ui:
	$(PYTHON) -m uvicorn services.ui.main:app --reload --port 8081

test:
	.venv/bin/pytest -q

lint:
	.venv/bin/ruff check . && .venv/bin/ruff format --check .

deploy:
	gcloud builds submit --config infra/cloudbuild.yaml --project=concordat-hack

# The golden path against the deployed fleets. ARGS=--no-approve parks it at the human gate.
demo:
	$(PYTHON) -m scripts.run_demo $(ARGS)

# What a judge runs: a real case, beat by beat, with no clone and no credentials.
judge:
	bash scripts/judge_replay.sh
