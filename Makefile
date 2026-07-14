.PHONY: help install dev cluster deploy seed query guard-no-cron eval-quality eval-safety eval-quality-wait eval-safety-wait test lint clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Setup ──────────────────────────────────────────────

install: ## Install production dependencies
	pip install -e .

dev: ## Install all dependencies (dev + eval + redteam)
	pip install -e ".[all]"

# ── Cluster ────────────────────────────────────────────

cluster: ## Create kind cluster
	kind create cluster --name eval-stack
	kubectl cluster-info --context kind-eval-stack

cluster-delete: ## Delete kind cluster
	kind delete cluster --name eval-stack

# ── Deploy ─────────────────────────────────────────────

deploy: ## Deploy all standing services
	kubectl apply -f k8s/chroma-deployment.yaml
	kubectl apply -f k8s/mlflow-deployment.yaml
	kubectl apply -f k8s/chatbot-deployment.yaml

deploy-chroma: ## Deploy Chroma only
	kubectl apply -f k8s/chroma-deployment.yaml

deploy-mlflow: ## Deploy MLflow only
	kubectl apply -f k8s/mlflow-deployment.yaml

deploy-chatbot: ## Deploy chatbot only
	kubectl apply -f k8s/chatbot-deployment.yaml

# ── Build & Load ───────────────────────────────────────

build-chatbot: ## Build chatbot Docker image
	docker build -f Dockerfile.chatbot -t oss-ai-eval-chatbot:latest .

build-eval: ## Build eval/redteam Jobs Docker image (ragas, deepeval, pyrit, garak, fairlearn)
	docker build -f Dockerfile.eval --build-arg GIT_COMMIT=$$(git rev-parse --short HEAD) -t oss-ai-eval-jobs:latest .

build-promptfoo: ## Build promptfoo Jobs Docker image (separate from build-eval — see docs/known-limitations.md)
	docker build -f Dockerfile.promptfoo --build-arg GIT_COMMIT=$$(git rev-parse --short HEAD) -t oss-ai-eval-promptfoo:latest .

build-mlflow: ## Build prebuilt MLflow Docker image
	docker build -f Dockerfile.mlflow -t oss-ai-eval-mlflow:latest .

load-images: ## Load local images into kind
	kind load docker-image oss-ai-eval-chatbot:latest --name eval-stack
	kind load docker-image oss-ai-eval-jobs:latest --name eval-stack
	kind load docker-image oss-ai-eval-promptfoo:latest --name eval-stack
	kind load docker-image oss-ai-eval-mlflow:latest --name eval-stack

# ── Data ───────────────────────────────────────────────

seed: ## Seed Chroma with sample documents
	python scripts/seed_chroma.py

dvc-pull: ## Pull DVC-tracked data
	dvc pull

dvc-push: ## Push DVC-tracked data
	dvc push

# ── Run ────────────────────────────────────────────────

port-forward: ## Port-forward all services
	@echo "Chatbot: http://localhost:8000"
	@echo "MLflow:  http://localhost:5000"
	kubectl port-forward svc/chatbot 8000:8000 &
	kubectl port-forward svc/mlflow 5000:5000 &

query: ## Send a test query to the chatbot
	curl -s -X POST http://localhost:8000/query \
		-H "Content-Type: application/json" \
		-d '{"question": "$(Q)"}' | python -m json.tool

# ── Eval ───────────────────────────────────────────────

guard-no-cron: ## Fail if any CronJob is scheduled on the cluster (Codespaces must only run Jobs on-demand)
	@if kubectl get cronjobs -A --no-headers 2>/dev/null | grep -q .; then \
		echo "ERROR: CronJob(s) found on the cluster. A Codespace auto-stops on idle" ; \
		echo "regardless of internal activity, so a schedule left running here either" ; \
		echo "never fires (machine stopped) or silently burns free hours (kept connected" ; \
		echo "to make it fire). Remove it: kubectl delete cronjob --all -A" ; \
		kubectl get cronjobs -A; \
		exit 1; \
	fi

eval-ragas: guard-no-cron ## Run RAGAS evaluation Job
	kubectl apply -f k8s/jobs/ragas-sweep.yaml

eval-deepeval: guard-no-cron ## Run DeepEval evaluation Job
	kubectl apply -f k8s/jobs/deepeval-sweep.yaml

eval-promptfoo: guard-no-cron ## Run promptfoo regression sweep Job
	kubectl apply -f k8s/jobs/promptfoo-sweep.yaml

eval-quality: eval-ragas eval-promptfoo ## Run full quality cycle

eval-quality-wait: eval-quality ## Run quality cycle and block until its Jobs finish (success or failure)
	kubectl wait --for=condition=complete --timeout=45m job/ragas-sweep job/promptfoo-sweep

safety-pyrit: guard-no-cron ## Run PyRIT XPIA Job
	kubectl apply -f k8s/jobs/pyrit-xpia.yaml

safety-garak: guard-no-cron ## Run Garak probe Job
	kubectl apply -f k8s/jobs/garak-probe.yaml

safety-fairlearn: guard-no-cron ## Run Fairlearn audit Job
	kubectl apply -f k8s/jobs/fairlearn-audit.yaml

eval-safety: safety-pyrit safety-garak safety-fairlearn ## Run full safety cycle

eval-safety-wait: eval-safety ## Run safety cycle and block until its Jobs finish (success or failure)
	kubectl wait --for=condition=complete --timeout=45m job/pyrit-xpia job/garak-probe job/fairlearn-audit

# ── Dev ────────────────────────────────────────────────

test: ## Run tests
	pytest tests/ -v --tb=short

lint: ## Run linters
	ruff check src/ tests/ scripts/
	ruff format --check src/ tests/ scripts/
	mypy src/

format: ## Auto-format code
	ruff check --fix src/ tests/ scripts/
	ruff format src/ tests/ scripts/

clean: ## Clean build artifacts
	rm -rf dist/ build/ *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
