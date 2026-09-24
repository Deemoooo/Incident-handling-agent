from datetime import datetime
import requests
import time

PROM_URL = "http://localhost:9090"

def query_prometheus(query_string: str):
    url = f"{PROM_URL}/api/v1/query"
    try:
        response = requests.get(url, params={"query": query_string}, timeout=10)
        data = response.json()
        if data.get("status") == "error":
            return {"error": data["error"]}
        else:
            results = data["data"]["result"]
            MAX_SERIES = 20
            truncated = len(results) > MAX_SERIES
            results = results[:MAX_SERIES]

            output = {
                "result": [
                    {"labels": r["metric"], "value": float(r["value"][1])}
                    for r in results
                ]
            }
            if truncated:
                output["note"] = (
                    f"Too many series returned, showing first {MAX_SERIES}. "
                    "Use sum by (...) to aggregate."
                )
            return output
    except Exception as e:
        return {"error": str(e)}

def query_prometheus_range(query_string: str, minutes: int = 30, step: int = 30):
    url = f"{PROM_URL}/api/v1/query_range"
    end = int(time.time())
    start = end - minutes * 60
    try:
        response = requests.get(url, params={"query": query_string, "start": start, "end": end, "step": step}, timeout=10)
        data = response.json()
        if data.get("status") == "error":
            return {"error": data["error"]}
        else:
            results = data["data"]["result"]
            return {"result": [
                {"labels": service["metric"], "values": [[datetime.fromtimestamp(v[0]).strftime("%H:%M:%S"), float(v[1])] for v in service["values"]]}
                for service in results
            ]}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    print(query_prometheus_range(
            'sum by (service) (rate(http_requests_total{route="/api/work"}[1m]))',
            minutes=30,
        ))