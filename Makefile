.PHONY: help install validate test lock clean

help: ## Show this help.
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install the package in editable mode.
	pip install -e .

validate: ## Validate chunks in algo_push/ (override with DIR=...).
	python3 scripts/validate_chunks.py $(or $(DIR),algo_push/)

test: ## Run the validator against the bundled examples.
	python3 scripts/validate_chunks.py examples/

lock: ## Regenerate uv.lock.
	uv lock

clean: ## Remove build / cache artifacts.
	rm -rf build/ dist/ *.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
