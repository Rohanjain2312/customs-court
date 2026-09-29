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

# Customs Court demo on http://127.0.0.1:8765. Builds the frontend first if needed.
DEMO_PORT ?= 8765
DEMO_FRONTEND := demo/frontend
NODE_PATH_EXTRA := $(HOME)/.local/opt/node/bin

demo-frontend:
	@if [ ! -f $(DEMO_FRONTEND)/dist/index.html ] || [ -n "$$(find $(DEMO_FRONTEND)/src $(DEMO_FRONTEND)/index.html -newer $(DEMO_FRONTEND)/dist/index.html 2>/dev/null | head -1)" ]; then \
		export PATH=$(NODE_PATH_EXTRA):$$PATH; cd $(DEMO_FRONTEND) && ([ -d node_modules ] || npm ci) && npm run build; \
	fi

# Replay mode: recorded hearings only. No API key, no network, no spend.
replay: demo-frontend
	DEMO_MODE=replay OFFLINE=true $(UV) --extra demo python -m uvicorn demo.backend.app:app --host 127.0.0.1 --port $(DEMO_PORT)

# Live-capable: new exhibits run the real agents when ANTHROPIC_API_KEY is set,
# capped at DEMO_SESSION_CAP_USD (default 2) per browser session. Replays still work.
demo: demo-frontend
	DEMO_MODE=live $(UV) --extra demo python -m uvicorn demo.backend.app:app --host 127.0.0.1 --port $(DEMO_PORT)

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
