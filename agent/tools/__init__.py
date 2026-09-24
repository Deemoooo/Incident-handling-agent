from .prom import query_prometheus, query_prometheus_range
from .k8s import list_pods, get_pod_logs, get_events

PROMETHEUS_QUERY_SCHEMA = {
    "name": "query_prometheus",
    "description": """
        This is a tool that can be used to query the Prometheus database for metrics.
        The available metrics are: http_requests_total, http_request_duration_seconds_bucket, container_memory_working_set_bytes, kube_pod_container_status_restarts_total.
        The available labels are service, route, status, container and namespace.
        Example queries:
        - Error rate by service: sum by (service) (rate(http_requests_total{route="/api/work", status=~"5.."}[1m])) / sum by (service) (rate(http_requests_total{route="/api/work"}[1m]))
        - p95 latency: histogram_quantile(0.95, sum by (service, le) (rate(http_request_duration_seconds_bucket{route="/api/work"}[1m])))
        - Memory per container: sum by (container) (container_memory_working_set_bytes{namespace="demo", container!=""})

        Notes:
        - Always aggregate with sum by (...). Raw queries return many labels that waste context.
        - Always filter by route="/api/work" for business traffic; otherwise health probes and metrics scrapes are included.
        - status="499" means the client gave up waiting — a sign this service is slow, not erroring.
        - Services form a chain: gateway -> order -> inventory.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "query_string": {
                "type": "string",
                "description": "The PromQL query to execute"
            },
        },
        "required": ["query_string"],
    }
}

PROMETHEUS_RANGE_QUERY = {
    "name": "query_prometheus_range",
    "description": """
        Query Prometheus over a time range to see how a metric changed. 
        Use this to find when a problem started, and to distinguish a gradual ramp (e.g. memory leak) from a sudden step change (e.g. a bad deploy). 
        Same metrics and labels as query_prometheus.
        """,
    "input_schema": {
        "type": "object",
        "properties": {
            "minutes": {
                "type": "number",
                "description": "The number of minutes to query"
            },
            "step": {
                "type": "number",
                "description": "The step of the query"
            },
            "query_string": {
                "type": "string",
                "description": "The PromQL query to execute"
            },
        },
        "required": ["query_string"],
    }
}

LIST_PODS = {
    "name": "list_pods",
    "description": """
        List pods in the demo namespace with their phase, readiness, restart count, and the reason the previous container terminated. 
        A last_terminated_reason of OOMKilled means the container ran out of memory.
        """,
    "input_schema": {
        "type": "object",
        "properties": {
            "namespace": {
                "type": "string",
                "description": "The namespace to list the pods from"
            },
        },
    }
}

GET_POD_LOGS = {
    "name": "get_pod_logs",
    "description": """
        Get recent logs from a pod. 
        Set previous=true to read the logs of the previous crashed container — essential when a pod was OOMKilled, since the current container's logs start fresh after the restart.
        """,
    "input_schema": {
        "type": "object",
        "properties": {
            "pod_name": {
                "type": "string",
                "description": "The name of the pod to get the logs from"
            },
            "previous": {
                "type": "boolean",
                "description": "Whether to get the logs of the previous crashed container"
            },
            "lines": {
                "type": "number",
                "description": "The number of lines to get"
            }
        },
        "required": ["pod_name"],
    }
}

GET_EVENTS = {
    "name": "get_events",
    "description": """
        Get recent Kubernetes cluster events. 
        Useful for understanding what's happening in the cluster, and to find related events,
        such as pod restart, image pull errors or pod stuck in Pending state.
        Pass warnings_only as True to filter Kubernetes routine events
        Note: events are only retained for 1 hour
        """,
    "input_schema": {
        "type": "object",
        "properties": {
            "warnings_only": {
                "type": "boolean",
                "description": "Whether to filter Kubernetes routine events"
            },
            "limit": {
                "type": "number",
                "description": "The number of events to get"
            },
            "namespace": {
                "type": "string",
                "description": "The namespace to get the events from"
            },
        },
    }
}

TOOLS = [
    PROMETHEUS_QUERY_SCHEMA,
    PROMETHEUS_RANGE_QUERY,
    LIST_PODS,
    GET_POD_LOGS,
    GET_EVENTS,
]

TOOL_FUNCTIONS = {
    "query_prometheus": query_prometheus,
    "query_prometheus_range": query_prometheus_range,
    "list_pods": list_pods,
    "get_pod_logs": get_pod_logs,
    "get_events": get_events,
}