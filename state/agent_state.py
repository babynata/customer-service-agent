"""
Agent State 定义

LangGraph 的状态机核心。所有节点通过读写 State 传递信息。
"""

from typing import TypedDict, Annotated, Optional, Literal


def _merge_lists(x: list, y: list) -> list:
    """Reducer：合并两个列表"""
    return x + y


class AgentState(TypedDict):
    """客服 Agent 的状态定义"""

    # === 输入 ===
    user_query: str

    # === 认知层（LLM 输出）===
    intent: Optional[Literal["shipping", "refund", "order_status", "other"]]
    confidence: float
    sentiment: float
    entities: dict

    # === 检索层（代码执行）===
    order_info: Optional[dict]
    faq_result: Optional[dict]

    # === 决策层（LLM 输出）===
    reasoning: Optional[str]
    can_auto_resolve: Optional[bool]
    plan: Optional[str]

    # === 校验层（契约状态）===
    contract_violations: Annotated[list[str], _merge_lists]
    blocked: bool
    block_reason: Optional[str]

    # === 生成层（LLM 输出）===
    response: Optional[str]
    policy_cited: bool

    # === 展示 ===
    thinking_log: Annotated[list[str], _merge_lists]
