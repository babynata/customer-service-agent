"""
客服 Agent 演示版 v2
严格保留设计初衷：状态机 + 多个专用 LLM 节点 + 确定性校验层

节点职责：
- LLM 节点（3个）：只负责语义理解、推理、生成
- 代码节点（3个）：只负责查数据、硬性规则、安全校验
- 状态机：显式控制流，LLM 不决定路由，代码决定路由
"""

from typing import TypedDict, Annotated, Optional, Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI
import json
import gradio as gr
import os

# ============ JSON 解析容错（DeepSeek 输出兼容） ============

def safe_json_parse(content: str, default: dict) -> dict:
    """
    鲁棒的 JSON 解析器。
    处理 DeepSeek 可能输出的 markdown 代码块、多余空格等问题。
    """
    if not content or not content.strip():
        return default

    text = content.strip()

    # 去除 markdown 代码块标记
    if text.startswith("```"):
        lines = text.split("\n")
        # 找到第一个和最后一个 ```，取中间内容
        start_idx = 0
        end_idx = len(lines)
        for i, line in enumerate(lines):
            if line.strip().startswith("```"):
                if start_idx == 0:
                    start_idx = i + 1
                else:
                    end_idx = i
                    break
        text = "\n".join(lines[start_idx:end_idx]).strip()

    # 尝试解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 尝试修复常见问题：单引号替换、尾部逗号
        try:
            fixed = text.replace("'", '"')
            # 移除尾部逗号
            import re
            fixed = re.sub(r',(\s*[}\]])', r'\1', fixed)
            return json.loads(fixed)
        except:
            pass

    # 尝试提取 JSON 子串（找第一个 { 和最后一个 }）
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        pass

    return default

# ============ 1. State Schema ============

class AgentState(TypedDict):
    user_query: str
    # === 认知层（LLM 负责）===
    intent: Optional[Literal["shipping", "refund", "order_status", "other"]]
    confidence: float
    sentiment: float  # -1.0 ~ 1.0
    entities: dict
    # === 检索层（代码负责）===
    order_info: Optional[dict]
    # === 决策层（LLM 负责推理，代码负责判断）===
    reasoning: Optional[str]  # LLM 的推理过程（给人看）
    can_auto_resolve: Optional[bool]  # LLM 建议能否自动解决
    # === 校验层（代码负责）===
    policy_result: Optional[dict]
    blocked: bool  # 是否被硬性规则拦截
    block_reason: Optional[str]
    # === 生成层（LLM 负责）===
    response: Optional[str]
    # === 展示层 ===
    thinking_log: Annotated[list, lambda x, y: x + y]


# ============ 2. Mock 数据 ============

MOCK_ORDERS = {
    "123456789012345678": {
        "order_id": "123456789012345678",
        "product": "iPhone 15 Pro",
        "amount": 8999,
        "status": "已发货",
        "tracking_no": "SF1029384756",
        "carrier": "顺丰速运",
        "created_at": "2025-05-20"
    },
    "876543210987654321": {
        "order_id": "876543210987654321",
        "product": "AirPods Pro",
        "amount": 199,
        "status": "待发货",
        "tracking_no": None,
        "created_at": "2025-05-26"
    }
}

MOCK_TRACKING = {
    "SF1029384756": [
        {"time": "2025-05-25 14:30", "status": "已签收", "location": "上海市浦东新区"},
        {"time": "2025-05-25 08:00", "status": "派送中", "location": "上海市"},
    ]
}

# ============ 3. LLM 初始化（火山方舟 DeepSeek） ============

# 火山方舟配置（优先从环境变量读取）
ARK_API_KEY = os.environ.get("ARK_API_KEY", "ark-298587c3-db54-4a33-a2fb-eed70dba29b3-b163c")
ARK_ENDPOINT_ID = os.environ.get("ARK_ENDPOINT_ID", "deepseek-v3-2-251201")
ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"

DEMO_MODE = ARK_API_KEY.startswith("YOUR_") or not ARK_API_KEY

if DEMO_MODE:
    print("⚠️  DEMO MODE：未配置火山方舟 API Key，使用 Mock LLM 运行")
    print("    如需接入真实 API，请设置环境变量：")
    print("    export ARK_API_KEY=your_key")
    print("    export ARK_ENDPOINT_ID=ep-xxxxx")

    class MockLLM:
        """Mock LLM：用规则模拟 DeepSeek 输出，用于验证链路"""
        def invoke(self, prompt: str):
            class MockResult:
                def __init__(self, content):
                    self.content = content

            p = prompt.lower()

            # 意图识别 Mock
            if "意图识别" in prompt or "intent" in p:
                if any(w in p for w in ["到哪", "物流", "快递", "发货", "签收"]):
                    return MockResult('{"intent": "shipping", "confidence": 0.95, "sentiment": 0.0, "entities": {"order_id": "123456789012345678", "phone": null}}')
                elif any(w in p for w in ["退款", "退货", "退钱"]):
                    order_id = "123456789012345678" if "123456789012345678" in prompt else "876543210987654321"
                    return MockResult(f'{{"intent": "refund", "confidence": 0.92, "sentiment": -0.2, "entities": {{"order_id": "{order_id}", "phone": null}}}}')
                elif any(w in p for w in ["订单状态", "发货了吗", "还没发"]):
                    return MockResult('{"intent": "order_status", "confidence": 0.88, "sentiment": -0.1, "entities": {"order_id": "876543210987654321", "phone": null}}')
                elif any(w in p for w in ["骗子", "垃圾", "投诉", "315"]):
                    return MockResult('{"intent": "refund", "confidence": 0.85, "sentiment": -0.85, "entities": {"order_id": null, "phone": null}}')
                else:
                    return MockResult('{"intent": "other", "confidence": 0.6, "sentiment": 0.0, "entities": {"order_id": null, "phone": null}}')

            # 推理决策 Mock
            elif "决策推理" in prompt or "can_auto_resolve" in p:
                if "金额" in prompt and "8999" in prompt:
                    return MockResult('{"analysis": "订单金额8999元超过自动处理阈值5000元，属于大额退款，需人工审核", "can_auto_resolve": false, "plan": "转人工客服处理", "escalate_reason": "金额超限"}')
                elif "情感" in prompt and ("-0.8" in prompt or "负面" in prompt):
                    return MockResult('{"analysis": "用户情绪极度负面，继续自动处理可能激化矛盾", "can_auto_resolve": false, "plan": "立即转人工安抚", "escalate_reason": "情绪负面"}')
                else:
                    return MockResult('{"analysis": "情况清晰，订单信息和政策依据完整，可以自动处理", "can_auto_resolve": true, "plan": "自动生成回复", "escalate_reason": null}')

            # 回复生成 Mock（ Fallback：返回简单文本）
            return MockResult("已收到您的请求，正在处理中...")

    llm = MockLLM()

else:
    print(f"✅ 使用火山方舟 API：{ARK_ENDPOINT_ID}")
    llm = ChatOpenAI(
        model=ARK_ENDPOINT_ID,
        api_key=ARK_API_KEY,
        base_url=ARK_BASE_URL,
        temperature=0.1,
        max_tokens=2048
    )

# ============ 4. 专用 LLM 节点（语义层） ============

def intent_understand(state: AgentState) -> AgentState:
    """
    专用 LLM 节点 #1：语义理解
    职责：只负责理解用户说什么，不决定怎么做
    """
    prompt = f"""
    你是【意图识别专家】。只分析用户意图，不做任何操作决定。

    任务：
    1. 判断意图：shipping(物流)/refund(退款)/order_status(订单状态)/other
    2. 提取实体：18位订单号、手机号
    3. 评估情感：-1.0(愤怒) ~ 1.0(满意)
    4. 评估置信度：0.0 ~ 1.0（不确定时低于0.8）

    输出 JSON：
    {{{{
      "intent": "shipping|refund|order_status|other",
      "confidence": 0.0-1.0,
      "sentiment": -1.0-1.0,
      "entities": {{"order_id": "..."或null, "phone": "..."或null}}
    }}}}

    用户问题：{state['user_query']}
    """

    result = llm.invoke(prompt)
    parsed = safe_json_parse(
        result.content,
        {"intent": "other", "confidence": 0.0, "sentiment": 0.0, "entities": {}}
    )

    return {
        "intent": parsed.get("intent", "other"),
        "confidence": parsed.get("confidence", 0.0),
        "sentiment": parsed.get("sentiment", 0.0),
        "entities": parsed.get("entities", {}),
        "thinking_log": [
            "🧠 【LLM-意图理解】",
            f"   意图: {parsed.get('intent')} | 置信度: {parsed.get('confidence')} | 情感: {parsed.get('sentiment')}"
        ]
    }


def reason_node(state: AgentState) -> AgentState:
    """
    专用 LLM 节点 #2：推理决策
    职责：综合所有信息，思考"能不能解决、怎么解决"
    约束：只输出推理和建议，不直接生成给用户的回复
    """
    if state.get("blocked"):
        return {"thinking_log": []}

    order = state.get("order_info")
    policy = state.get("policy_result")

    context = f"""
    你是【决策推理专家】。基于已知信息判断如何处理用户请求。

    已知信息：
    - 用户意图：{state['intent']}
    - 订单信息：{json.dumps(order, ensure_ascii=False) if order else '无'}
    - 政策判断：{json.dumps(policy, ensure_ascii=False) if policy else '无'}
    - 用户情感：{state['sentiment']}

    决策规则（严格遵循）：
    1. 如果意图是 shipping（物流查询），且已查到订单信息（含物流轨迹）→ can_auto_resolve = true
    2. 如果意图是 order_status（订单状态），且已查到订单信息 → can_auto_resolve = true
    3. 如果意图是 refund（退款），且 policy_result 明确显示 eligible = true → can_auto_resolve = true
    4. 如果意图是 refund，且 policy_result 显示 eligible = false → can_auto_resolve = false（需人工判定争议）
    5. 如果订单信息为空，或物流/政策信息缺失 → can_auto_resolve = false
    6. 如果用户情感 < -0.8（极度愤怒）→ can_auto_resolve = false

    注意：你是"参谋"，不是"执行者"。你只出主意，不直接回复用户。

    输出 JSON：
    {{{{
      "analysis": "情况分析...",
      "can_auto_resolve": true/false,
      "plan": "处理方案...",
      "escalate_reason": "转人工原因（如需）"
    }}}}
    """

    result = llm.invoke(context)
    parsed = safe_json_parse(
        result.content,
        {"analysis": "解析失败", "can_auto_resolve": False, "plan": "", "escalate_reason": "推理异常"}
    )

    return {
        "reasoning": parsed.get("analysis"),
        "can_auto_resolve": parsed.get("can_auto_resolve", False),
        "thinking_log": [
            "🧠 【LLM-推理决策】",
            f"   分析: {parsed.get('analysis', '')[:60]}...",
            f"   建议: {'自动处理' if parsed.get('can_auto_resolve') else '转人工'}"
        ]
    }


def generate_node(state: AgentState) -> AgentState:
    """
    专用 LLM 节点 #3：回复生成
    职责：基于推理结果，生成给用户的自然语言回复
    约束：不能篡改推理结论，不能编造数据
    """
    if state.get("blocked"):
        return {
            "response": f"您好，您的问题需要人工客服处理。原因：{state.get('block_reason', '')}",
            "thinking_log": ["📝 【LLM-回复生成】生成转人工提示"]
        }

    order = state.get("order_info")
    policy = state.get("policy_result")
    reasoning = state.get("reasoning", "")

    prompt = f"""
    你是【客服回复专家】。基于已确认的决策结论，生成给用户的回复。

    决策结论（不可违背）：
    {reasoning}

    订单信息（不可编造）：
    {json.dumps(order, ensure_ascii=False) if order else '未查询到'}

    政策结果（不可违背）：
    {json.dumps(policy, ensure_ascii=False) if policy else '无'}

    规则：
    1. 语气礼貌、简洁
    2. 只使用提供的数据，不编造
    3. 如果是退款，必须包含政策依据
    4. 如果是物流，必须包含最新物流状态

    请生成回复：
    """

    result = llm.invoke(prompt)

    return {
        "response": result.content.strip(),
        "thinking_log": [
            "📝 【LLM-回复生成】",
            f"   输出: {result.content.strip()[:60]}..."
        ]
    }


# ============ 5. 确定性校验层（代码节点） ============

def retrieve_node(state: AgentState) -> AgentState:
    """
    代码节点 #1：数据检索
    职责：查订单、查物流。纯代码，无 LLM。
    """
    order_id = state.get("entities", {}).get("order_id")
    logs = ["⚙️ 【代码-数据检索】"]

    if order_id and order_id in MOCK_ORDERS:
        info = MOCK_ORDERS[order_id]
        logs.append(f"   查到订单: {info['product']} ¥{info['amount']}")

        if info.get("tracking_no"):
            tracking = MOCK_TRACKING.get(info["tracking_no"], [])
            info["tracking"] = tracking
            logs.append(f"   查到物流: {tracking[0]['status'] if tracking else '无轨迹'}")
        else:
            logs.append("   该订单暂无物流信息")
    else:
        info = None
        logs.append("   未找到订单")

    return {"order_info": info, "thinking_log": logs}


def policy_check(state: AgentState) -> AgentState:
    """
    代码节点 #2：政策判断（确定性规则引擎）
    职责：用代码硬规则判断是否符合退款条件，不依赖 LLM 推理
    """
    if state["intent"] != "refund":
        return {"thinking_log": []}

    order = state.get("order_info")
    logs = ["⚙️ 【代码-政策校验】"]

    if not order:
        logs.append("   结果: 未找到订单，无法判断")
        return {"policy_result": {"eligible": False, "reason": "未找到订单"}, "thinking_log": logs}

    amount = order["amount"]
    logs.append(f"   订单金额: ¥{amount}")

    # 硬性规则：金额 > 5000 需人工
    if amount > 5000:
        logs.append("   结果: 金额超限，标记为需人工审核")
        return {
            "policy_result": {"eligible": False, "reason": "金额超限", "threshold": 5000},
            "thinking_log": logs
        }

    # 演示简化：小额都通过
    logs.append("   结果: 符合自动退款条件")
    return {"policy_result": {"eligible": True, "reason": "符合退款条件"}, "thinking_log": logs}


def escalate_gate(state: AgentState) -> AgentState:
    """
    代码节点 #3：硬性规则 Gate
    职责：100% 确定的拦截规则。LLM 不参与此决策。
    """
    logs = ["⚙️ 【代码-升级判断】"]
    blocked = False
    reason = None

    # 规则 1：置信度过低
    if state["confidence"] < 0.7:
        blocked = True
        reason = f"意图置信度 {state['confidence']:.2f} < 0.7，系统无法确定用户意图"
        logs.append(f"   触发: 置信度过低 ({state['confidence']:.2f})")

    # 规则 2：情感极度负面
    elif state["sentiment"] < -0.8:
        blocked = True
        reason = "用户情绪极度负面，需人工安抚"
        logs.append(f"   触发: 情感负面 ({state['sentiment']:.2f})")

    # 规则 3：政策拦截（金额超限）
    elif state.get("policy_result", {}).get("reason") == "金额超限":
        blocked = True
        reason = f"订单金额 ¥{state['order_info']['amount']} 超过自动处理上限 ¥5000"
        logs.append(f"   触发: 金额超限 (¥{state['order_info']['amount']})")

    # 规则 4：LLM 建议转人工
    elif state.get("can_auto_resolve") is False and state.get("reasoning"):
        blocked = True
        reason = f"推理节点建议转人工: {state.get('reasoning', '')[:50]}"
        logs.append("   触发: 推理节点建议人工处理")

    else:
        logs.append("   结果: 通过，继续自动处理")

    return {
        "blocked": blocked,
        "block_reason": reason,
        "thinking_log": logs
    }


def final_check(state: AgentState) -> AgentState:
    """
    代码节点 #4：最终安全校验
    职责：回复发出前的最后一道防线
    """
    response = state.get("response", "")
    logs = ["⚙️ 【代码-最终校验】"]

    # 敏感词过滤（演示简化）
    sensitive_words = ["傻逼", "骗子", "垃圾", "妈的"]
    for word in sensitive_words:
        if word in response:
            logs.append(f"   拦截: 命中敏感词 '{word}'")
            return {
                "response": "系统检测到异常内容，已转人工客服处理。",
                "thinking_log": logs
            }

    # 一致性校验：回复中提到的金额必须与订单一致
    order = state.get("order_info")
    if order and "amount" in order:
        import re
        amounts_in_response = re.findall(r"¥?(\d+)", response)
        if amounts_in_response and str(order["amount"]) not in amounts_in_response:
            # 如果回复里有数字金额但和订单对不上，拦截
            # 演示简化：只警告不拦截
            logs.append(f"   警告: 回复中金额可能与订单不一致")

    logs.append("   结果: 校验通过")
    return {"thinking_log": logs}


# ============ 6. 路由函数（代码硬路由） ============

def route_after_intent(state: AgentState) -> Literal["retrieve", "escalate_gate"]:
    """
    代码路由：LLM 只输出意图和置信度，代码决定下一步去哪。
    """
    if state["intent"] in ["shipping", "refund", "order_status"] and state["confidence"] >= 0.7:
        return "retrieve"
    return "escalate_gate"


def route_after_retrieve(state: AgentState) -> Literal["policy_check", "reason"]:
    if state["intent"] == "refund":
        return "policy_check"
    return "reason"


def route_after_policy(state: AgentState) -> Literal["reason"]:
    return "reason"


def route_after_reason(state: AgentState) -> Literal["escalate_gate"]:
    return "escalate_gate"


def route_after_escalate(state: AgentState) -> Literal["generate"]:
    """
    即使被 block，也走 generate 生成转人工提示，然后结束。
    """
    return "generate"


# ============ 7. 构建状态机 ============

workflow = StateGraph(AgentState)

# 注册节点
workflow.add_node("intent_understand", intent_understand)
workflow.add_node("retrieve", retrieve_node)
workflow.add_node("policy_check", policy_check)
workflow.add_node("reason", reason_node)
workflow.add_node("escalate_gate", escalate_gate)
workflow.add_node("generate", generate_node)
workflow.add_node("final_check", final_check)

# 边
workflow.set_entry_point("intent_understand")
workflow.add_conditional_edges("intent_understand", route_after_intent)
workflow.add_conditional_edges("retrieve", route_after_retrieve)
workflow.add_conditional_edges("policy_check", route_after_policy)
workflow.add_conditional_edges("reason", route_after_reason)
workflow.add_conditional_edges("escalate_gate", route_after_escalate)
workflow.add_edge("generate", "final_check")
workflow.add_edge("final_check", END)

memory = MemorySaver()
app = workflow.compile(checkpointer=memory)

# ============ 8. Gradio 演示界面 ============

def chat(message: str, history: list, session_id: str = "demo"):
    config = {"configurable": {"thread_id": session_id}}

    result = app.invoke({
        "user_query": message,
        "thinking_log": []
    }, config)

    # 组装思考过程，清晰标注 LLM vs 代码
    thinking = "\n".join(result.get("thinking_log", []))

    # 在顶部加总结
    summary = []
    summary.append("=" * 40)
    summary.append(f"🎯 最终决策: {'✅ 自动处理' if not result.get('blocked') else '🔴 转人工'}")
    summary.append(f"📝 最终回复: {result.get('response', '')[:80]}...")
    summary.append("=" * 40)

    full_thinking = "\n".join(summary) + "\n\n" + thinking

    return result.get("response", ""), full_thinking


def create_ui():
    with gr.Blocks(title="客服 Agent 演示 v2") as demo:
        gr.Markdown("""
        # 🤖 客服 Agent 演示 v2

        **设计原则：状态机 + 多个专用 LLM 节点 + 确定性校验层**

        ---
        **🧠 LLM 节点（语义层）：** 意图理解 | 推理决策 | 回复生成
        **⚙️ 代码节点（校验层）：** 数据检索 | 政策规则 | 升级判断 | 安全校验

        ---
        **演示用例：**
        - `我的订单 123456789012345678 到哪了？` → 物流查询（自动）
        - `我想退款，订单号 876543210987654321` → 小额退款（自动）
        - `我要退 iPhone，订单 123456789012345678` → 大额退款（¥8999>¥5000，代码拦截→人工）
        - `你们这群骗子！` → 情绪负面（代码拦截→人工）
        """)

        with gr.Row():
            with gr.Column(scale=2):
                chatbot = gr.Chatbot(label="对话", height=450)
                msg = gr.Textbox(label="输入", placeholder="请输入问题...")
                with gr.Row():
                    send = gr.Button("发送", variant="primary")
                    clear = gr.Button("清空")

            with gr.Column(scale=1):
                thinking = gr.Textbox(
                    label="🧠 Agent 决策过程（LLM vs 代码）",
                    lines=25,
                    max_lines=35,
                    interactive=False,
                    value="发送消息后，此处展示每个节点的决策过程..."
                )

        session = gr.State(value="demo_001")

        def respond(message, history, sid):
            if not message.strip():
                return "", history, ""
            resp, think = chat(message, history, sid)
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": resp})
            return "", history, think

        send.click(respond, [msg, chatbot, session], [msg, chatbot, thinking])
        msg.submit(respond, [msg, chatbot, session], [msg, chatbot, thinking])
        clear.click(lambda: ([], "发送消息后，此处展示每个节点的决策过程..."), None, [chatbot, thinking])

    return demo


if __name__ == "__main__":
    demo = create_ui()
    demo.launch(
        share=False,
        server_name="0.0.0.0",
        server_port=7860,
        theme=gr.themes.Soft()
    )
