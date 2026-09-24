# Incident Triage Agent

An LLM agent that investigates Kubernetes incidents automatically. Given an alert, it queries Prometheus, inspects pod state, reads logs, and produces a root-cause report with the evidence it used.

The repo includes everything needed to reproduce incidents locally: a kind cluster, a three-service demo app with metrics, a Prometheus/Grafana stack, four reproducible fault scenarios, and an eval harness that scores the agent against known ground truth.

## How it works

```
loadgen → gateway → order → inventory        (namespace: demo)
                   │
                   ▼
        Prometheus + Grafana + Alertmanager  (namespace: monitoring)
                   │
                   ▼
            Triage agent (Claude + 5 read-only tools)
                   │
                   ▼
            Root-cause report
```

The agent has five tools, all read-only and scoped to one namespace by RBAC:

| Tool                     | Purpose                                                 |
| ------------------------ | ------------------------------------------------------- |
| `query_prometheus`       | Current value of a metric                               |
| `query_prometheus_range` | How a metric changed over time                          |
| `list_pods`              | Pod health, restart counts, why the last container died |
| `get_pod_logs`           | Application logs, including a crashed container's       |
| `get_events`             | Kubernetes events: kills, probe failures, backoff       |

## Requirements

- Docker, kind, kubectl, Helm
- Node.js 22+ (to build the demo service)
- Python 3.9+
- An Anthropic API key

## Setup

```bash
./setup.sh
```

This creates the kind cluster, installs kube-prometheus-stack, deploys the three demo services and the load generator, and provisions the Grafana dashboard and alert rules.

Then set up the agent:

```bash
cd agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # add your ANTHROPIC_API_KEY
```

Open Prometheus and Grafana in separate terminals (the agent needs Prometheus reachable):

```bash
kubectl port-forward -n monitoring svc/monitoring-kube-prometheus-prometheus 9090
kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80   # admin / admin
```

## Running an investigation

Inject a fault, wait a couple of minutes for the alerts to fire, then run the agent:

```bash
./faults/fault.sh inject slow-dependency
# wait ~2 min
cd agent && python agent.py
./faults/fault.sh recover slow-dependency
```

Available scenarios:

| Scenario          | What it simulates                                   |
| ----------------- | --------------------------------------------------- |
| `memory-leak`     | order leaks memory and gets OOMKilled               |
| `slow-dependency` | inventory becomes slow, upstream services time out  |
| `bad-deploy`      | a new order release starts failing ~30% of requests |
| `misconfig-loop`  | inventory is misconfigured to call itself           |

Only inject one scenario at a time, and recover it before injecting the next.

## Running the eval

```bash
cd agent && python eval.py
```

Runs every scenario end to end, scores each report against ground truth with an LLM judge (0 = wrong service, 1 = right service wrong cause, 2 = both right), and writes results to `eval/results.jsonl`. Takes roughly 50 minutes.

Latest run (9 runs, `claude-haiku-4-5`): correct service in 78% of runs, mean score 1.22/2, ~3.6 tool-calling steps, ~15s and ~$0.03 per investigation.

## Teardown

```bash
./teardown.sh
```

## Layout

```
cluster/          kind cluster config
service/          demo service (TypeScript) + Dockerfile
charts/service/   Helm chart, deployed three times with different values
monitoring/       Prometheus values, alert rules, Grafana dashboard
apps/             load generator
faults/           fault injection scripts + ground truth
agent/            agent loop, tools, RBAC, eval harness
eval/             eval results
```

## Notes

- All three services run the same image. `SERVICE_NAME` and `DOWNSTREAM_URL` decide which role a pod plays.
- After changing service code, redeploy with a new tag: `./deploy.sh v7`.
- The agent's ServiceAccount has `get`/`list` only, on pods, logs, events, deployments and replicasets in the `demo` namespace. It cannot write anything or read secrets.
