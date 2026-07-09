# Setup Guide

## Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| Docker | 24+ | Build container images |
| kind | 0.20+ | Local Kubernetes cluster |
| kubectl | 1.28+ | Cluster management |
| Python | 3.11+ | Application runtime |
| Node.js | 18+ | promptfoo CLI |
| DVC | 3.55+ | Data versioning |
| gcloud CLI | Latest | Vertex AI authentication |

## Step 1: Clone and Install

```bash
git clone <repo-url> && cd oss-ai-eval-stack
python -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"
```

## Step 2: Vertex AI Credentials

1. Create a GCP project with Vertex AI API enabled
2. Create a service account with `Vertex AI User` role
3. Download the JSON key file
4. Save it as `service-account.json` in the project root (gitignored)

```bash
export VERTEX_PROJECT_ID="your-gcp-project-id"
export GOOGLE_APPLICATION_CREDENTIALS="./service-account.json"
```

Verify access:
```bash
python -c "
from google.cloud import aiplatform
aiplatform.init(project='$VERTEX_PROJECT_ID')
print('Vertex AI connected successfully')
"
```

## Step 3: LangSmith Setup

1. Sign up at [smith.langchain.com](https://smith.langchain.com) (free Developer tier)
2. Get your API key from Settings → API Keys
3. Set environment variables:

```bash
export LANGSMITH_API_KEY="lsv2_pt_..."
export LANGSMITH_PROJECT="oss-ai-eval-stack"
export LANGSMITH_TRACING="true"
```

## Step 4: Create Kubernetes Cluster

```bash
kind create cluster --name eval-stack
kubectl cluster-info --context kind-eval-stack
```

## Step 5: Create Kubernetes Secrets

```bash
# Vertex AI credentials
kubectl create secret generic vertex-credentials \
  --from-file=service-account.json=./service-account.json \
  --from-literal=project-id=$VERTEX_PROJECT_ID

# LangSmith API key
kubectl create secret generic langsmith-credentials \
  --from-literal=api-key=$LANGSMITH_API_KEY
```

## Step 6: Build and Load Images

```bash
# Build the chatbot image
docker build -f Dockerfile.chatbot -t oss-ai-eval-chatbot:latest .

# Load it into kind
kind load docker-image oss-ai-eval-chatbot:latest --name eval-stack
```

## Step 7: Deploy Services

```bash
# Deploy in order: data stores first, then app
kubectl apply -f k8s/chroma-deployment.yaml
kubectl wait --for=condition=ready pod -l app=chroma --timeout=60s

kubectl apply -f k8s/mlflow-deployment.yaml
kubectl wait --for=condition=ready pod -l app=mlflow --timeout=120s

kubectl apply -f k8s/chatbot-deployment.yaml
kubectl wait --for=condition=ready pod -l app=chatbot --timeout=60s
```

## Step 8: Seed the Knowledge Base

```bash
# Port-forward Chroma
kubectl port-forward svc/chroma 8001:8001 &

# Run the seed script
CHROMA_HOST=localhost CHROMA_PORT=8001 python scripts/seed_chroma.py
```

## Step 9: Create Golden Dataset ConfigMap

```bash
kubectl create configmap golden-dataset \
  --from-file=golden_dataset.json=./data/golden_dataset.json
```

## Step 10: Test

```bash
# Port-forward the chatbot
kubectl port-forward svc/chatbot 8000:8000 &

# Send a test query
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What is retrieval-augmented generation?"}' | python -m json.tool

# Or use the Makefile
make query Q="What is RAG?"
```

## Step 11: Run an Eval Cycle

```bash
# Quality cycle
kubectl apply -f k8s/jobs/ragas-sweep.yaml
kubectl logs -f job/ragas-sweep

# Safety cycle
kubectl apply -f k8s/jobs/pyrit-xpia.yaml
kubectl logs -f job/pyrit-xpia
```

## Step 12: Check MLflow

```bash
# Port-forward MLflow
kubectl port-forward svc/mlflow 5000:5000 &

# Open http://localhost:5000 in your browser
```

## Troubleshooting

### Pods stuck in Pending
```bash
kubectl describe pod <pod-name>
# Usually image pull issues on kind — re-run `kind load docker-image`
```

### Chroma connection refused
```bash
# Verify Chroma is ready
kubectl get pods -l app=chroma
kubectl logs -l app=chroma
```

### MLflow SQLite lock
```bash
# Only one eval Job at a time!
kubectl get jobs
# Delete stuck jobs
kubectl delete job <job-name>
```

### Vertex AI permission denied
```bash
# Verify service account has correct roles
gcloud projects get-iam-policy $VERTEX_PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:$(gcloud iam service-accounts list --format='value(email)' | head -1)"
```
