import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from anthropic import Anthropic

from agent import run_agent

load_dotenv()   # 读取 .env 文件里的变量

client = Anthropic()

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_FILE = REPO_ROOT / "eval" / "results.jsonl"
RUNS = 2
WAIT_AFTER_INJECT = 120     # 等指标稳定
WAIT_AFTER_RECOVER = 90     # 等系统恢复干净

SCENARIOS = [
    {
        "name": "memory-leak",
        "alert": "PodRestarting: order is restarting (severity: critical)",
        "expected_service": "order",
        "root_cause": "memory leak in order causing OOMKilled restarts",
    },
    {
        "name": "slow-dependency",
        "alert": "HighErrorRate: gateway error rate is high (severity: critical)",
        "expected_service": "inventory",
        "root_cause": "inventory latency (~3s) causing upstream timeouts in order and gateway",
    },
    {
        "name": "bad-deploy",
        "alert": "HighErrorRate: gateway error rate is high (severity: critical)",
        "expected_service": "order",
        "root_cause": "a new order deployment enabled FEATURE_NEW_PRICING, causing ~30% of requests to fail with 500",
    },
    {
        "name": "misconfig-loop",
        "alert": "HighErrorRate: gateway error rate is high (severity: critical)",
        "expected_service": "inventory",
        "root_cause": "inventory misconfigured with DOWNSTREAM_URL pointing to itself, causing a request loop that exhausts memory and triggers OOMKilled",
    },
]


def fault(action: str, name: str):
    subprocess.run(
        ["./faults/fault.sh", action, name],
        cwd=REPO_ROOT,
        check=True,
    )


def save(record: dict):
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "a") as f:
        f.write(json.dumps(record) + "\n")


def run_once(scenario: dict, run_index: int):
    name = scenario["name"]
    print(f"\n########## {name} run {run_index} ##########")

    fault("inject", name)
    print(f"injected, waiting {WAIT_AFTER_INJECT}s ...")
    time.sleep(WAIT_AFTER_INJECT)

    try:
        result = run_agent(scenario["alert"])
    finally:
        # 不管 Agent 是否出错，都要恢复，否则后面的场景全乱
        fault("recover", name)
    
    prompt = f"""
    Ground truth root cause: {scenario["root_cause"]}
    Agent's report: {result["summary"]}

    Score the agent's root cause identification:
    2 = correctly identified both the service and the nature of the problem
    1 = correct service, but wrong or vague explanation of the cause
    0 = wrong service

    Respond with only a JSON object: {{"score": 0|1|2, "reason": "..."}}
    """

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        system="You are evaluating an SRE agent's root cause analysis. Respond with only a JSON object, no other text.",
        messages=[{"role": "user", "content": prompt}],
    )
    summary = "".join(b.text for b in response.content if b.type == "text")
    score, reason = None, None
    try:
        text = summary.strip()
        if text.startswith("```"):
            text = text.split("```")[1].removeprefix("json").strip()
        parsed = json.loads(text)
        score, reason = parsed["score"], parsed["reason"]
    except Exception as e:
        score, reason = None, f"judge parse failed: {e}"

    record = {
        "scenario": name,
        "run": run_index,
        "expected_service": scenario["expected_service"],
        "timestamp": datetime.now().isoformat(),
        "root_cause_score": score,
        "root_cause_reason": reason,
        **result,
    }
    save(record)

    print(f"recovered, waiting {WAIT_AFTER_RECOVER}s ...")
    time.sleep(WAIT_AFTER_RECOVER)


if __name__ == "__main__":
    for scenario in SCENARIOS:
        for i in range(1, RUNS + 1):
            run_once(scenario, i)
    print(f"\nDone. Results: {RESULTS_FILE}")