#!/usr/bin/env bash
set -euo pipefail

CLUSTER="triage-lab"
CONTEXT="kind-${CLUSTER}"

# 1. 创建集群（已存在就跳过）
if kind get clusters | grep -qx "${CLUSTER}"; then
  echo "==> Cluster ${CLUSTER} already exists, skipping"
else
  echo "==> Creating cluster"
  kind create cluster --config cluster/kind-config.yaml
fi

# 2. 安装监控
echo "==> Installing kube-prometheus-stack"
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  -n monitoring --create-namespace \
  -f monitoring/values.yaml \
  --kube-context "${CONTEXT}" \
  --wait --timeout 5m

# 3. 加载 dashboard
echo "==> Loading dashboard"
kubectl create configmap demo-services-dashboard -n monitoring \
  --from-file=monitoring/dashboards/demo-services.json \
  --dry-run=client -o yaml | kubectl apply -f - --context "${CONTEXT}"
kubectl label configmap demo-services-dashboard -n monitoring \
  grafana_dashboard=1 --overwrite --context "${CONTEXT}"

# 4. 部署三个服务
echo "==> Deploying services"
./deploy.sh v1

# 5. 部署 loadgen
echo "==> Deploying loadgen"
kubectl apply -f apps/loadgen.yaml --context "${CONTEXT}"

echo "==> Setup complete"