#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:?用法: ./faults/fault.sh <inject|recover> <scenario>}"
SCENARIO="${2:?场景: memory-leak | bad-deploy | slow-dependency | misconfig-loop}"
CONTEXT="kind-triage-lab"
NS="demo"
GROUND_TRUTH="faults/ground-truth.jsonl"

# load generator to inject faults
set_fault() {
  local svc="$1" body="$2"
  kubectl exec -n "$NS" deploy/loadgen --context "$CONTEXT" -- \
    curl -s -X POST "http://${svc}/admin/fault" \
    -H "Content-Type: application/json" -d "$body"
  echo
}

# record ground truth for eval later
record() {
  local target="$1" root_cause="$2"
  printf '{"scenario":"%s","target":"%s","root_cause":"%s","injected_at":"%s"}\n' \
    "$SCENARIO" "$target" "$root_cause" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$GROUND_TRUTH"
}

# rollback with Helm
rollback() {
  helm rollback "$1" -n "$NS" --kube-context "$CONTEXT" --wait
}

case "${ACTION}:${SCENARIO}" in
  inject:memory-leak)
    set_fault order '{"leakMbPerSec": 5}'
    record order "memory leak in order causing OOMKilled restarts"
    ;;
  recover:memory-leak)
    set_fault order '{"leakMbPerSec": 0}'
    ;;

  inject:bad-deploy)
    helm upgrade order ./charts/service -n "$NS" --reuse-values \
      -f faults/values-bad-pricing.yaml --kube-context "$CONTEXT" --wait
    record order "bad deploy: new order release enabled FEATURE_NEW_PRICING, causing errors"
    ;;
  recover:bad-deploy)
    rollback order
    ;;

  inject:slow-dependency)
    set_fault inventory '{"latencyMs": 3000}'
    record inventory "inventory latency causing upstream timeouts"
    ;;
  recover:slow-dependency)
    set_fault inventory '{"latencyMs": 0}'
    ;;

  inject:misconfig-loop)
    helm upgrade inventory ./charts/service -n "$NS" --reuse-values \
      --set downstreamUrl=http://inventory --kube-context "$CONTEXT" --wait
    record inventory "misconfigured DOWNSTREAM_URL: inventory calls itself in a loop"
    ;;
  recover:misconfig-loop)
    rollback inventory
    ;;

  *)
    echo "Unknown command: ${ACTION} ${SCENARIO}"
    exit 1
    ;;
esac

echo "==> ${ACTION} ${SCENARIO} done"