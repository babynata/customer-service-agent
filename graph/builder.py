"""
状态机构建器

将节点和边组装成完整的 LangGraph 状态机。
"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from state import AgentState
from nodes import (
    intent_understand, reason_node, generate_node,
    retrieve_node, policy_check, contract_check,
    escalate_gate, final_check,
)
from graph.router import (
    route_after_intent, route_after_retrieve, route_after_policy,
    route_after_reason, route_after_contract, route_after_escalate,
)


def build_agent_graph():
    """
    构建并编译客服 Agent 状态机。

    图结构：
    intent_understand → retrieve → policy_check → reason → contract_check → escalate_gate → generate → final_check → END
    """
    workflow = StateGraph(AgentState)

    # LLM 语义层
    workflow.add_node("intent_understand", intent_understand)
    workflow.add_node("reason", reason_node)
    workflow.add_node("generate", generate_node)

    # 代码校验层
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("policy_check", policy_check)
    workflow.add_node("contract_check", contract_check)
    workflow.add_node("escalate_gate", escalate_gate)
    workflow.add_node("final_check", final_check)

    # 边
    workflow.set_entry_point("intent_understand")
    workflow.add_conditional_edges("intent_understand", route_after_intent)
    workflow.add_conditional_edges("retrieve", route_after_retrieve)
    workflow.add_conditional_edges("policy_check", route_after_policy)
    workflow.add_conditional_edges("reason", route_after_reason)
    workflow.add_conditional_edges("contract_check", route_after_contract)
    workflow.add_conditional_edges("escalate_gate", route_after_escalate)
    workflow.add_edge("generate", "final_check")
    workflow.add_edge("final_check", END)

    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)


# 全局单例
agent_app = build_agent_graph()
