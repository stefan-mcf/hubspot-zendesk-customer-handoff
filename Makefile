.PHONY: test plan validate

PYTHON ?= python3

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v

plan:
	PYTHONPATH=src $(PYTHON) -m customer_handoff.cli plan \
		--dataset examples/controlled-handoff.json \
		--output-root build/plan

validate: test
	$(PYTHON) validate_public.py

