.PHONY: test lint sim serve policy evals evidence seed-export

lint:
	ruff check .

test: lint
	pytest -q

sim:
	python -m legacy_sim --port 8080

serve:
	python -m agentgate --port 8000

policy:
	python scripts/policy_check.py

seed-export:
	python -m legacy_sim --export legacy/seed

evals:
	python -m evals.run_evals

evidence:
	python -m evals.evidence
