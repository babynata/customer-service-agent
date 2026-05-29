"""
Prometheus 指标采集

定义核心指标和装饰器，自动采集 Agent 运行数据。
"""

from functools import wraps
from time import time
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST


# 核心指标
AGENT_REQUESTS = Counter(
    "agent_requests_total",
    "Total Agent requests",
    ["intent", "blocked"],
)

AGENT_LATENCY = Histogram(
    "agent_latency_seconds",
    "Agent request latency",
    ["node"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

LLM_CALLS = Counter(
    "agent_llm_calls_total",
    "Total LLM calls",
    ["tier"],
)

ERRORS = Counter(
    "agent_errors_total",
    "Total errors",
    ["node", "error_type"],
)

FAQ_HIT_RATE = Gauge(
    "agent_faq_hit_rate",
    "FAQ hit rate",
)


def timed(node_name: str):
    """装饰器：自动记录节点执行延迟"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time()
            try:
                return func(*args, **kwargs)
            finally:
                AGENT_LATENCY.labels(node=node_name).observe(time() - start)
        return wrapper
    return decorator


def record_request(intent: str, blocked: bool):
    """记录一次请求"""
    AGENT_REQUESTS.labels(intent=intent or "unknown", blocked=str(blocked).lower()).inc()


def record_llm_call(tier: str):
    """记录一次 LLM 调用"""
    LLM_CALLS.labels(tier=tier).inc()


def record_error(node: str, error_type: str):
    """记录一次错误"""
    ERRORS.labels(node=node, error_type=error_type).inc()


def set_faq_hit_rate(rate: float):
    """设置 FAQ 命中率"""
    FAQ_HIT_RATE.set(rate)


def get_metrics():
    """获取 Prometheus 格式指标"""
    return generate_latest()
