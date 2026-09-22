#!/usr/bin/env bash
set -euo pipefail

# 版本号从第一个参数读取，没传就报错并提示用法
VERSION="${1:?用法: ./deploy.sh <version>，例如 ./deploy.sh v2}"
CLUSTER="triage-lab"
CONTEXT="kind-${CLUSTER}"
IMAGE="service:${VERSION}"

echo "==> Building ${IMAGE}"
docker build -t "${IMAGE}" ./service

echo "==> Loading into kind"
kind load docker-image "${IMAGE}" --name "${CLUSTER}"

for svc in inventory order gateway; do
  echo "==> Deploying ${svc}"
  helm upgrade --install "${svc}" ./charts/service \
    -n demo --create-namespace \
    -f "charts/service/values-${svc}.yaml" \
    --set image.tag="${VERSION}"
done

echo "==> Waiting for rollout"
for svc in inventory order gateway; do
  kubectl rollout status "deploy/${svc}" -n demo --timeout=120s
done

echo "==> Done: ${IMAGE}"