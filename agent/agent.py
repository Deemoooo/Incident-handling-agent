import json
from datetime import datetime
from dotenv import load_dotenv
from anthropic import Anthropic
from tools import TOOLS, TOOL_FUNCTIONS

load_dotenv()   # 读取 .env 文件里的变量

client = Anthropic()   # 自动读取环境变量 ANTHROPIC_API_KEY

SYSTEM_PROMPT = """You are an SRE incident triage agent investigating alerts from a Kubernetes cluster.

The system under investigation:
- Three Node.js services in the `demo` namespace forming a chain: gateway -> order -> inventory
- A load generator continuously calls gateway's /api/work endpoint

Investigate the alert using the available tools and determine the root cause.

When investigating a metric around a specific event, use a short time range with a small step (e.g. minutes=10, step=15) to avoid missing fast changes.

Always check whether the affected service was recently deployed or restarted. 
Compare pod start times across services — a pod that started much more recently than its peers suggests a recent deployment, which is a common cause of new errors.

When you have enough evidence to identify which service is the root cause and what is wrong with it, stop investigating and write your report. 
Do not re-run queries you have already run. It is better to conclude with medium confidence than to keep gathering data.

Aim to conclude within 5 tool-calling steps. Never call the same tool with similar arguments twice — if you already have the data, use it.

End your investigation with a report in exactly this format:

## Summary
## Root cause
(which service, and what is wrong with it)
## Evidence
## Confidence
(high / medium / low)
## Recommended action
"""

MAX_STEPS = 10

def run_agent(alert: str) -> dict:
    messages = [{"role": "user", "content": f"Alert fired:\n{alert}"}]

    input_tokens = 0
    output_tokens = 0
    tool_calls = []
    total_steps = 0
    summary = ""
    current_time = datetime.now()
    duration_sec = 0
    completed = False

    for step in range(MAX_STEPS):
        print(f"\n===== Step {step + 1} =====")

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        input_tokens += response.usage.input_tokens
        output_tokens += response.usage.output_tokens

        # 把模型的回复原样加进历史
        messages.append({"role": "assistant", "content": response.content})

        # 打印模型的思考
        for block in response.content:
            if block.type == "text":
                print(block.text)

        # 没有要调用的 tool，说明给出结论了
        if response.stop_reason != "tool_use":
            summary = "".join(b.text for b in response.content if b.type == "text")
            total_steps = step + 1
            completed = True
            break

        # 执行所有 tool_use
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            print(f"[tool] {block.name} {block.input}")
            tool_calls.append(block.name)
            try:
                result = TOOL_FUNCTIONS[block.name](**block.input)
            except Exception as e:
                result = {"error": f"Tool execution failed: {e}"}
            print(f"[result] {str(result)[:300]}")
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result, default=str),
            })

        messages.append({"role": "user", "content": tool_results})
    
    total_steps = total_steps or MAX_STEPS
    duration_sec = (datetime.now() - current_time).total_seconds()
    if not summary:
        summary = "No results after max steps"

    return {
        "summary": summary,
        "total_steps": total_steps,
        "duration_sec": duration_sec,
        "tool_calls": tool_calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "completed": completed,
    }

if __name__ == "__main__":
    alert = "HighErrorRate: gateway error rate is 100% over the last minute (severity: critical)"
    print("\n===== Final report =====")
    print(run_agent(alert))