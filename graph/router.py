"""
路由函数

核心设计原则：LLM 只输出信号（如 intent、confidence），代码做路由决策。
所有路由都是确定性的，不依赖 LLM "自由意志"。
"""

from typing import Literal

from state import AgentState


def route_after_intent(state: AgentState) -> Literal["retrieve", "escalate_gate"]:
    """
    意图理解后的路由：
    - 白名单内的 intent + 高置信度 → 检索
    - 其他 → 升级 Gate（转人工）
    """
    if state["intent"] in ["shipping", "refund", "order_status"] and state["confidence"] >= 0.7:
        return "retrieve"
    return "escalate_gate"


def route_after_retrieve(state: AgentState) -> Literal["policy_check", "reason"]:
    """
    检索后的路由：
    - 退款意图 → 先过政策校验
    - 其他 → 直接推理
    """
    if state["intent"] == "refund":
        return "policy_check"
    return "reason"


def route_after_policy(state: AgentState) -> Literal["reason"]:
    """政策校验后必须走推理节点"""
    return "reason"


def route_after_reason(state: AgentState) -> Literal["contract_check"]:
    """推理后必须走契约校验"""
    return "contract_check"


def route_after_contract(state: AgentState) -> Literal["escalate_gate"]:
    """契约校验后进入升级判断"""
    return "escalate_gate"


def route_after_escalate(state: AgentState) -> Literal["generate"]:
    """升级判断后进入生成（无论是否被 block，都生成提示语）"""
    return "generate"
