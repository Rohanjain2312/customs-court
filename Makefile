SHELL := /bin/bash
export PATH := $(HOME)/.local/bin:$(HOME)/.local/opt/lima/bin:$(PATH)
UV := uv run

.PHONY: setup data test lint eval-smoke eval-full cost demo replay build-deploy-aws build-deploy-gcp \
        deploy-aws deploy-gcp destroy-aws destroy-gcp mcp-stdio mcp-http fixture

setup:
	uv sync --extra embed --extra cloud
	cd demo/frontend && npm ci

# Full data pipeline. Every step caches raw responses on disk and resumes.
data:
	$(UV) tariffagent data hts
	$(UV) tariffagent data cross-meta
	$(UV) tariffagent data cross-text --since 2025-07-01
	$(UV) tariffagent data derive
	$(UV) python scripts/status_eval.py
	$(UV) tariffagent data status

fixture:
	$(UV) python scripts/build_fixture_db.py

test:
	$(UV) pytest -q

lint:
	$(UV) ruff check src tests scripts
	$(UV) ruff format --check src tests scripts

# Recorded responses only. No network, no spend.
eval-smoke:
	OFFLINE=true $(UV) tariffagent eval smoke

# Spends money (Anthropic and OpenAI only), capped by BUDGET_USD_* in .env.
eval-full:
	bash scripts/eval_full.sh

cost:
	@$(UV) tariffagent cost

mcp-stdio:
	$(UV) tariffagent-mcp --transport stdio

mcp-http:
	$(UV) tariffagent-mcp --transport http --host 127.0.0.1 --port 8000

demo:
	$(UV) tariffagent demo --mode replay

replay: demo

build-deploy-aws:
	bash deploy/aws/build_and_validate.sh

build-deploy-gcp:
	bash deploy/gcp/build_and_validate.sh

deploy-aws:
	bash deploy/aws/deploy.sh

deploy-gcp:
	bash deploy/gcp/deploy.sh

destroy-aws:
	bash deploy/aws/destroy.sh

destroy-gcp:
	bash deploy/gcp/destroy.sh
