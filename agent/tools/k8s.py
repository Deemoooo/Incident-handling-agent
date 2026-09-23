from datetime import datetime, timezone
from kubernetes import client, config

try:
    config.load_incluster_config()   
except config.ConfigException:
    config.load_kube_config()        

v1 = client.CoreV1Api()     
apps = client.AppsV1Api()   
NAMESPACE = "demo"

def list_pods(namespace: str = NAMESPACE):
    pods = v1.list_namespaced_pod(namespace)
    result = []
    for pod in pods.items:
        statuses = pod.status.container_statuses or []
        cs = statuses[0] if statuses else None

        last_reason = None
        exit_code = None
        last_exited_at = None
        if cs and cs.last_state and cs.last_state.terminated:
            last_reason = cs.last_state.terminated.reason
            exit_code = cs.last_state.terminated.exit_code
            last_exited_at = cs.last_state.terminated.finished_at.isoformat() if cs.last_state.terminated.finished_at else None

        result.append({
            "name": pod.metadata.name,
            "phase": pod.status.phase,
            "ready": cs.ready if cs else False,
            "restart_count": cs.restart_count if cs else 0,
            "last_terminated_reason": last_reason,
            "last_terminated_exit_code": exit_code,
            "last_terminated_exited_at": last_exited_at,
            "start_time": pod.status.start_time.isoformat() if pod.status.start_time else None,
        })
    return {"result": result}

def get_pod_logs(pod_name: str, lines: int = 100, previous: bool = False, namespace: str = NAMESPACE):
    lines = min(lines, 500)
    try:
        logs = v1.read_namespaced_pod_log(pod_name, namespace, tail_lines=lines, previous=previous)
        return {"result": logs}
    except client.rest.ApiException as e:
        if e.status == 404:
            return {"error": "Pod not found, use list_pods to get available pods"}
        elif e.status == 400 and previous:
            return {"error": "Pod doesn't have a previous terminated container"}
        else:
            return {"error": f"Failed to get logs: {e.status} {e.reason}"}

def get_events(limit: int = 30, warnings_only: bool = False, namespace: str = NAMESPACE):
    try:
        events = v1.list_namespaced_event(namespace)
        items = events.items
        def _event_time(e):
            timestamp = e.last_timestamp or e.event_time or e.metadata.creation_timestamp
            return timestamp if timestamp else datetime.min.replace(tzinfo=timezone.utc)
        if warnings_only:
            items = [e for e in items if e.type == "Warning"]
        items.sort(key=lambda e: _event_time(e), reverse=True)
        return {"result": [{"type": e.type, "reason": e.reason, "count": e.count, "involved_object": f"{e.involved_object.kind}/{e.involved_object.name}", "message": e.message, "timestamp": _event_time(e).isoformat()} for e in items[:limit]]}
    except client.rest.ApiException as e:
        return {"error": f"Failed to get events: {e.status} {e.reason}"}

if __name__ == "__main__":
    print(get_events())