"""
LLM 语义层节点

职责：只负责语义理解、推理、生成，不决定路由。
所有输出必须通过 Pydantic Schema 强制格式化。
"""

import json

from config import llm_intent, llm_reason, llm_generate
from schemas import IntentSchema, ReasonSchema, GenerateSchema
from state import AgentState


def _safe_json_parse(content: str, default: dict) -> dict:
    """鲁棒的 JSON 解析器，处理 markdown 代码块等格式"""
    if not content or not content.strip():
        return default

    text = content.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        start_idx, end_idx = 0, len(lines)
        for i, line in enumerate(lines):
            if line.strip().startswith("```"):
                if start_idx == 0:
                    start_idx = i + 1
                else:
                    end_idx = i
                    break
        text = "\n".join(lines[start_idx:end_idx]).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            fixed = text.replace("'", '"')
            import re
            fixed = re.sub(r',(\s*[}\]])', r'\1', fixed)
            return json.loads(fixed)
        except:
            pass

    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        pass

    return default


def intent_understand(state: AgentState) -> AgentState:
    """
    专用 LLM 节点 #1：语义理解
    输出契约：IntentSchema
    """
    history = state.get("messages", [])
    history_text = ""
    if history:
        # 取最近 3 轮对话作为上下文
        recent = history[-6:] if len(history) > 6 else history
        for msg in recent:
            role = "用户" if msg.get("role") == "user" else "客服"
            history_text += f"{role}：{msg.get('content', '')}\n"

    prompt = f"""
    你是【意图识别专家】。只分析用户意图，不做任何操作决定。

    历史对话（最近{len(history)//2 if history else 0}轮）：
    {history_text or "（无历史对话）"}

    当前用户问题：{state['user_query']}

    要求：
    1. intent 必须从白名单选择：["shipping", "refund", "order_status", "other"]
    2. confidence 必须诚实，不确定时低于 0.8
    3. entities 必须精确提取 18 位订单号和 11 位手机号（可引用历史对话中的信息）
    4. sentiment：-1.0(极度愤怒) ~ 1.0(非常满意)
    """

    try:
        result: IntentSchema = llm_intent.invoke(prompt)
        violations = []

        # 白名单检查
        valid_intents = ["shipping", "refund", "order_status", "other"]
        if result.intent not in valid_intents:
            violations.append(f"intent 不在白名单: {result.intent}")

        # 订单号格式
        order_id = result.entities.get("order_id")
        if order_id and (not isinstance(order_id, str) or len(order_id) != 18):
            violations.append(f"order_id 格式错误: {order_id}")

        return {
            "intent": result.intent,
            "confidence": result.confidence,
            "sentiment": result.sentiment,
            "entities": result.entities,
            "contract_violations": violations,
            "thinking_log": [
                "🧠 【LLM-意图理解】",
                f"   输出契约: IntentSchema",
                f"   intent={result.intent} | confidence={result.confidence:.2f} | sentiment={result.sentiment:.2f}",
                f"   entities={json.dumps(result.entities, ensure_ascii=False)}",
            ]
        }
    except Exception as e:
        return {
            "intent": "other",
            "confidence": 0.0,
            "sentiment": 0.0,
            "entities": {},
            "contract_violations": [f"结构化输出失败: {str(e)[:50]}"],
            "thinking_log": [
                "🧠 【LLM-意图理解】",
                f"   ❌ 契约违约: 结构化输出失败 - {str(e)[:50]}"
            ]
        }


def reason_node(state: AgentState) -> AgentState:
    """
    专用 LLM 节点 #2：推理决策
    输出契约：ReasonSchema
    """
    if state.get("blocked"):
        return {"thinking_log": []}

    order = state.get("order_info")
    policy = state.get("policy_result")

    history = state.get("messages", [])
    history_text = ""
    if history:
        recent = history[-6:] if len(history) > 6 else history
        for msg in recent:
            role = "用户" if msg.get("role") == "user" else "客服"
            history_text += f"{role}：{msg.get('content', '')}\n"

    context = f"""
    你是【决策推理专家】。基于已知信息判断如何处理用户请求。

    历史对话（最近{len(history)//2 if history else 0}轮）：
    {history_text or "（无历史对话）"}

    已知信息：
    - 用户意图：{state['intent']}
    - 订单信息：{json.dumps(order, ensure_ascii=False) if order else '无'}
    - 政策判断：{json.dumps(policy, ensure_ascii=False) if policy else '无'}
    - 用户情感：{state['sentiment']}

    决策规则（严格遵循）：
    1. 意图=shipping，查到订单+物流 → can_auto_resolve=true
    2. 意图=order_status，查到订单 → can_auto_resolve=true
    3. 意图=refund，policy.eligible=true → can_auto_resolve=true
    4. 意图=refund，policy.eligible=false → can_auto_resolve=false
    5. 订单为空 或 情感<-0.8 → can_auto_resolve=false

    输出契约：必须包含 analysis, can_auto_resolve(bool), plan, escalate_reason
    """

    try:
        result: ReasonSchema = llm_reason.invoke(context)
        violations = []

        if result.can_auto_resolve and not result.plan:
            violations.append("can_auto_resolve=true 但 plan 为空")
        if not result.can_auto_resolve and not result.escalate_reason:
            violations.append("can_auto_resolve=false 但 escalate_reason 为空")

        return {
            "reasoning": result.analysis,
            "can_auto_resolve": result.can_auto_resolve,
            "plan": result.plan,
            "contract_violations": violations,
            "thinking_log": [
                "🧠 【LLM-推理决策】",
                f"   输出契约: ReasonSchema",
                f"   can_auto_resolve={result.can_auto_resolve}",
                f"   analysis={result.analysis[:50]}...",
                f"   plan={result.plan[:40]}..." if result.plan else "   plan=无",
            ]
        }
    except Exception as e:
        return {
            "reasoning": "推理失败",
            "can_auto_resolve": False,
            "plan": "",
            "contract_violations": [f"ReasonSchema 解析失败: {str(e)[:50]}"],
            "thinking_log": [
                "🧠 【LLM-推理决策】",
                f"   ❌ 契约违约: ReasonSchema 解析失败 - {str(e)[:50]}"
            ]
        }


def generate_node(state: AgentState) -> AgentState:
    """
    专用 LLM 节点 #3：回复生成
    输出契约：GenerateSchema
    """
    if state.get("blocked"):
        resp = f"您好，您的问题需要人工客服处理。原因：{state.get('block_reason', '')}"
        return {
            "response": resp,
            "messages": [{"role": "assistant", "content": resp}],
            "policy_cited": False,
            "thinking_log": [
                "📝 【LLM-回复生成】",
                "   输出契约: GenerateSchema",
                "   生成转人工提示语"
            ]
        }

    order = state.get("order_info")
    policy = state.get("policy_result")
    reasoning = state.get("reasoning", "")

    history = state.get("messages", [])
    history_text = ""
    if history:
        recent = history[-6:] if len(history) > 6 else history
        for msg in recent:
            role = "用户" if msg.get("role") == "user" else "客服"
            history_text += f"{role}：{msg.get('content', '')}\n"

    prompt = f"""
    你是【客服回复专家】。基于已确认的决策结论，生成给用户的回复。

    历史对话（最近{len(history)//2 if history else 0}轮）：
    {history_text or "（无历史对话）"}

    决策结论（不可违背）：{reasoning}
    订单信息：{json.dumps(order, ensure_ascii=False) if order else '无'}
    政策结果：{json.dumps(policy, ensure_ascii=False) if policy else '无'}

    规则：
    1. 退款场景必须引用政策依据（policy_cited=true）
    2. 只使用提供的数据，不编造
    3. 语气礼貌、简洁，与历史对话风格一致
    4. 如果是追问（用户没有提供新信息），基于历史对话中的已知信息回答

    输出契约：GenerateSchema
    """

    try:
        result: GenerateSchema = llm_generate.invoke(prompt)
        violations = []

        if state["intent"] == "refund" and not result.policy_cited:
            violations.append("退款回复缺少政策引用标记")

        return {
            "response": result.response,
            "policy_cited": result.policy_cited,
            "messages": [{"role": "assistant", "content": result.response}],
            "contract_violations": violations,
            "thinking_log": [
                "📝 【LLM-回复生成】",
                f"   输出契约: GenerateSchema",
                f"   policy_cited={result.policy_cited}",
                f"   confidence={result.confidence}",
                f"   response={result.response[:50]}...",
            ]
        }
    except Exception as e:
        return {
            "response": "系统繁忙，请稍后重试。",
            "policy_cited": False,
            "messages": [{"role": "assistant", "content": "系统繁忙，请稍后重试。"}],
            "contract_violations": [f"GenerateSchema 解析失败: {str(e)[:50]}"],
            "thinking_log": [
                "📝 【LLM-回复生成】",
                f"   ❌ 契约违约: GenerateSchema 解析失败 - {str(e)[:50]}"
            ]
        }
