"""
代码校验层节点

职责：所有确定性逻辑——数据查询、硬性规则、契约校验、安全过滤。
LLM 不参与此层决策。
"""

import asyncio
import re

from state import AgentState
from tools import query_order, query_faq


def retrieve_node(state: AgentState) -> AgentState:
    """
    代码节点：并行检索（Fan-out / Fan-in）
    Reducer 合并语义：多个并发结果合并到 State
    """
    order_id = state.get("entities", {}).get("order_id")
    query = state["user_query"]
    logs = ["⚙️ 【代码-数据检索】", "   并发查询：订单 + FAQ"]

    async def query_all():
        tasks = {
            "order": query_order(order_id),
            "faq": query_faq(query)
        }
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        return dict(zip(tasks.keys(), results))

    try:
        results = asyncio.run(query_all())
    except Exception as e:
        results = {"order": {"error": str(e)}, "faq": {"error": str(e)}}

    order_result = results.get("order", {})
    faq_result = results.get("faq", {})

    logs.append(f"   订单结果: {'✓ 命中' if order_result.get('data') else '✗ 未命中'}")
    logs.append(f"   FAQ结果: {'✓ 命中' if faq_result.get('matched') else '✗ 未命中'}")

    return {
        "order_info": order_result.get("data"),
        "faq_result": faq_result,
        "thinking_log": logs
    }


def policy_check(state: AgentState) -> AgentState:
    """
    代码节点：政策判断（确定性规则引擎）
    """
    if state["intent"] != "refund":
        return {"thinking_log": []}

    order = state.get("order_info")
    logs = ["⚙️ 【代码-政策校验】"]

    if not order:
        logs.append("   结果: 未找到订单")
        return {"policy_result": {"eligible": False, "reason": "未找到订单"}, "thinking_log": logs}

    amount = order["amount"]
    logs.append(f"   订单金额: ¥{amount}")

    # 硬性规则：金额 > 5000 需人工
    if amount > 5000:
        logs.append("   结果: 金额超限(>5000)，需人工审核")
        return {
            "policy_result": {"eligible": False, "reason": "金额超限", "threshold": 5000},
            "thinking_log": logs
        }

    logs.append("   结果: 符合自动退款条件")
    return {"policy_result": {"eligible": True, "reason": "符合退款条件"}, "thinking_log": logs}


def contract_check(state: AgentState) -> AgentState:
    """
    代码节点：契约校验 Gate
    汇总所有契约违约，决定是否拦截
    """
    violations = state.get("contract_violations", [])
    logs = ["⚙️ 【代码-契约校验】"]

    if violations:
        logs.append(f"   发现 {len(violations)} 处契约违约:")
        for v in violations:
            logs.append(f"     ❌ {v}")
        logs.append("   决策: 拦截，转人工")
        return {
            "blocked": True,
            "block_reason": f"契约违约: {'; '.join(violations)}",
            "thinking_log": logs
        }

    logs.append("   所有契约校验通过")
    return {"blocked": False, "thinking_log": logs}


def escalate_gate(state: AgentState) -> AgentState:
    """
    代码节点：升级判断（硬性规则 Gate）
    """
    if state.get("blocked"):
        return {
            "thinking_log": [
                "⚙️ 【代码-升级判断】",
                f"   已拦截: {state.get('block_reason', '')}"
            ]
        }

    blocked = False
    reason = None
    logs = ["⚙️ 【代码-升级判断】"]

    if state["confidence"] < 0.7:
        blocked = True
        reason = f"置信度 {state['confidence']:.2f} < 0.7"
        logs.append("   触发: 置信度过低")
    elif state["sentiment"] < -0.8:
        blocked = True
        reason = "用户情绪极度负面"
        logs.append("   触发: 情感负面")
    elif state.get("policy_result", {}).get("reason") == "金额超限":
        blocked = True
        reason = f"金额超限 ¥{state['order_info']['amount']}"
        logs.append("   触发: 金额超限")
    elif state.get("can_auto_resolve") is False:
        blocked = True
        reason = "推理节点建议人工处理"
        logs.append("   触发: 推理建议人工")
    else:
        logs.append("   结果: 通过")

    return {
        "blocked": blocked,
        "block_reason": reason,
        "thinking_log": logs
    }


def final_check(state: AgentState) -> AgentState:
    """
    代码节点：最终安全校验
    """
    response = state.get("response", "")
    logs = ["⚙️ 【代码-最终校验】"]

    sensitive_words = ["傻逼", "骗子", "垃圾", "妈的"]
    for word in sensitive_words:
        if word in response:
            logs.append(f"   ❌ 命中敏感词: {word}")
            return {
                "response": "系统检测到异常内容，已转人工处理。",
                "thinking_log": logs
            }

    order = state.get("order_info")
    if order and "amount" in order:
        amounts = re.findall(r"¥?(\d+)", response)
        if amounts and str(order["amount"]) not in amounts:
            logs.append("   ⚠️ 回复中金额与订单不一致")
        else:
            logs.append("   ✓ 金额一致性通过")

    logs.append("   结果: 校验通过")
    return {"thinking_log": logs}
