.PHONY: help install dev cluster deploy seed query eval-quality eval-safety test lint clean

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

build-eval: ## Build eval/redteam Jobs Docker image (ragas, deepeval, pyrit, garak, fairlearn, promptfoo)
	docker build -f Dockerfile.eval -t oss-ai-eval-jobs:latest .

build-mlflow: ## Build prebuilt MLflow Docker image
	docker build -f Dockerfile.mlflow -t oss-ai-eval-mlflow:latest .

load-images: ## Load local images into kind
	kind load docker-image oss-ai-eval-chatbot:latest --name eval-stack
	kind load docker-image oss-ai-eval-jobs:latest --name eval-stack
	kind load docker-image oss-ai-eval-mlflow:latest --name eval-stack
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

eval-ragas: ## Run RAGAS evaluation Job
	kubectl apply -f k8s/jobs/ragas-sweep.yaml

eval-deepeval: ## Run DeepEval evaluation Job
	kubectl apply -f k8s/jobs/deepeval-sweep.yaml

eval-promptfoo: ## Run promptfoo regression sweep Job
	kubectl apply -f k8s/jobs/promptfoo-sweep.yaml

eval-quality: eval-ragas eval-promptfoo ## Run full quality cycle

safety-pyrit: ## Run PyRIT XPIA Job
	kubectl apply -f k8s/jobs/pyrit-xpia.yaml

safety-garak: ## Run Garak probe Job
	kubectl apply -f k8s/jobs/garak-probe.yaml

safety-fairlearn: ## Run Fairlearn audit Job
	kubectl apply -f k8s/jobs/fairlearn-audit.yaml

eval-safety: safety-pyrit safety-garak safety-fairlearn ## Run full safety cycle

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
