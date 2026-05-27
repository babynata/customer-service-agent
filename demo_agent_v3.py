"""
客服 Agent 演示版 v3 —— 完整接口契约设计

核心设计理念：接口契约是 LLM 与确定性系统之间的"协议层"（Protocol Layer）。
所有 LLM 输出必须通过契约校验，才能被下游节点消费。

五大契约要素：
1. Pydantic Schema + with_structured_output：强制输出格式
2. 枚举白名单约束：Intent 只能取自预定义值
3. 契约校验节点：每个 LLM 节点后接代码校验节点
4. 工具参数契约：BaseModel 参数校验 + 防注入
5. Reducer 合并语义：并发节点结果合并
"""

from typing import TypedDict, Annotated, Optional, Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, validator
import json
import gradio as gr
import os
import asyncio

# ============ 1. Pydantic Schema：LLM 输出契约 ============

class IntentSchema(BaseModel):
    """意图识别节点的输出契约"""
    intent: Literal["shipping", "refund", "order_status", "other"] = Field(
        description="用户意图，必须从枚举值中选择"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="置信度，0.0~1.0，低于0.8视为不确定"
    )
    sentiment: float = Field(
        ge=-1.0, le=1.0,
        description="情感分数，-1.0(愤怒)~1.0(满意)"
    )
    entities: dict = Field(
        default_factory=dict,
        description="提取的实体：order_id(18位数字)、phone(11位数字)"
    )

class ReasonSchema(BaseModel):
    """推理决策节点的输出契约"""
    analysis: str = Field(description="情况分析摘要")
    can_auto_resolve: bool = Field(description="能否自动解决")
    plan: str = Field(description="处理方案")
    escalate_reason: Optional[str] = Field(
        default=None,
        description="转人工原因（如需）"
    )

class GenerateSchema(BaseModel):
    """回复生成节点的输出契约"""
    response: str = Field(description="给用户的回复内容")
    policy_cited: bool = Field(
        default=False,
        description="是否引用了政策依据（退款场景必须）"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="回复置信度"
    )

# ============ 2. 工具参数契约 ============

class QueryOrderInput(BaseModel):
    """查询订单工具的输入契约"""
    order_id: str = Field(description="18位数字订单号")

    @validator("order_id")
    def validate_order_id(cls, v):
        import re
        if not re.match(r"^\d{18}$", v):
            raise ValueError("订单号必须是18位纯数字")
        return v

class SearchKnowledgeInput(BaseModel):
    """知识库检索工具的输入契约"""
    query: str = Field(min_length=1, max_length=100)
    top_k: int = Field(default=3, ge=1, le=10)

# ============ 3. State Schema（含契约字段） ============

class AgentState(TypedDict):
    # 输入
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
    contract_violations: Annotated[list[str], lambda x, y: x + y]
    blocked: bool
    block_reason: Optional[str]

    # === 生成层（LLM 输出）===
    response: Optional[str]
    policy_cited: bool

    # === 展示 ===
    thinking_log: Annotated[list[str], lambda x, y: x + y]


# ============ 4. Mock 数据 ============

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

MOCK_FAQ = {
    "退款": {"answer": "7天无理由退款，超过7天需联系人工客服", "confidence": 0.9},
    "发票": {"answer": "可在订单详情页申请电子发票", "confidence": 0.85},
}

# ============ 5. LLM 初始化 ============

ARK_API_KEY = os.environ.get("ARK_API_KEY", "ark-298587c3-db54-4a33-a2fb-eed70dba29b3-b163c")
ARK_ENDPOINT_ID = os.environ.get("ARK_ENDPOINT_ID", "deepseek-v3-2-251201")
ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"

llm = ChatOpenAI(
    model=ARK_ENDPOINT_ID,
    api_key=ARK_API_KEY,
    base_url=ARK_BASE_URL,
    temperature=0.1,
    max_tokens=2048
)

# 带结构化输出的 LLM（强制 JSON Schema）
llm_intent = llm.with_structured_output(IntentSchema)
llm_reason = llm.with_structured_output(ReasonSchema)
llm_generate = llm.with_structured_output(GenerateSchema)


# ============ 6. 专用 LLM 节点（语义层） ============

def intent_understand(state: AgentState) -> AgentState:
    """
    专用 LLM 节点 #1：语义理解
    输出契约：IntentSchema（Pydantic 强制校验）
    """
    prompt = f"""
    你是【意图识别专家】。只分析用户意图，不做任何操作决定。

    用户问题：{state['user_query']}

    要求：
    1. intent 必须从白名单选择：["shipping", "refund", "order_status", "other"]
    2. confidence 必须诚实，不确定时低于 0.8
    3. entities 必须精确提取 18 位订单号和 11 位手机号
    4. sentiment：-1.0(极度愤怒) ~ 1.0(非常满意)
    """

    try:
        result: IntentSchema = llm_intent.invoke(prompt)
        violations = []

        # 契约校验 #1：白名单检查
        if result.intent not in ["shipping", "refund", "order_status", "other"]:
            violations.append(f"intent 不在白名单: {result.intent}")

        # 契约校验 #2：订单号格式
        order_id = result.entities.get("order_id")
        if order_id and not isinstance(order_id, str):
            violations.append("order_id 类型错误")
        if order_id and len(order_id) != 18:
            violations.append(f"order_id 长度错误: {len(order_id)}")

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
        # 契约违约：结构化输出失败
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

    context = f"""
    你是【决策推理专家】。基于已知信息判断如何处理用户请求。

    已知信息：
    - 用户意图：{state['intent']}
    - 订单信息：{json.dumps(order, ensure_ascii=False) if order else '无'}
    - 政策判断：{json.dumps(policy, ensure_ascii=False) if policy else '无'}
    - 用户情感：{state['sentiment']}

    决策规则（严格遵循）：
    1. 意图=shipping，查到订单+物流 → can_auto_resolve=true
    2. 意图=order_status，查到订单 → can_auto_resolve=true
    3. 意图=refund，policy.eligible=true → can_auto_resolve=true
    4. 意图=refund，policy.eligible=false → can_auto_resolve=false（争议）
    5. 订单为空 或 情感<-0.8 → can_auto_resolve=false

    输出契约：必须包含 analysis, can_auto_resolve(bool), plan, escalate_reason
    """

    try:
        result: ReasonSchema = llm_reason.invoke(context)
        violations = []

        # 契约校验
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
        return {
            "response": f"您好，您的问题需要人工客服处理。原因：{state.get('block_reason', '')}",
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

    prompt = f"""
    你是【客服回复专家】。基于已确认的决策结论，生成给用户的回复。

    决策结论（不可违背）：{reasoning}
    订单信息：{json.dumps(order, ensure_ascii=False) if order else '无'}
    政策结果：{json.dumps(policy, ensure_ascii=False) if policy else '无'}

    规则：
    1. 退款场景必须引用政策依据（policy_cited=true）
    2. 只使用提供的数据，不编造
    3. 语气礼貌、简洁

    输出契约：GenerateSchema
    """

    try:
        result: GenerateSchema = llm_generate.invoke(prompt)
        violations = []

        # 契约校验：退款场景必须有 policy_cited
        if state["intent"] == "refund" and not result.policy_cited:
            violations.append("退款回复缺少政策引用标记")

        return {
            "response": result.response,
            "policy_cited": result.policy_cited,
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
            "contract_violations": [f"GenerateSchema 解析失败: {str(e)[:50]}"],
            "thinking_log": [
                "📝 【LLM-回复生成】",
                f"   ❌ 契约违约: GenerateSchema 解析失败 - {str(e)[:50]}"
            ]
        }


# ============ 7. 代码节点（校验层 + 工具层） ============

def retrieve_node(state: AgentState) -> AgentState:
    """
    代码节点：并行检索（Fan-out / Fan-in）
    Reducer 合并语义：多个并发结果合并到 State
    """
    order_id = state.get("entities", {}).get("order_id")
    query = state["user_query"]
    logs = ["⚙️ 【代码-数据检索】", "   并发查询：订单 + FAQ"]

    async def query_all():
        """
        Fan-out：并行查询多个数据源
        """
        tasks = {
            "order": _query_order(order_id),
            "faq": _query_faq(query)
        }
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        return dict(zip(tasks.keys(), results))

    async def _query_order(oid):
        """订单查询工具（带参数契约）"""
        if not oid:
            return {"error": "NO_ORDER_ID", "data": None}

        # 参数契约校验
        try:
            QueryOrderInput(order_id=oid)
        except Exception as e:
            return {"error": f"PARAM_INVALID: {e}", "data": None}

        data = MOCK_ORDERS.get(oid)
        if data:
            # 如果已发货，查物流
            if data.get("tracking_no"):
                data["tracking"] = MOCK_TRACKING.get(data["tracking_no"], [])
            return {"data": data}
        return {"error": "ORDER_NOT_FOUND", "data": None}

    async def _query_faq(q):
        """FAQ 检索工具"""
        for keyword, answer in MOCK_FAQ.items():
            if keyword in q:
                return {"matched": True, "answer": answer}
        return {"matched": False, "answer": None}

    # Fan-in：合并并发结果
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

    # 硬性规则
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
    职责：汇总所有契约违约，决定是否拦截
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
        return {"thinking_log": ["⚙️ 【代码-升级判断】", f"   已拦截: {state.get('block_reason', '')}"]}

    blocked = False
    reason = None
    logs = ["⚙️ 【代码-升级判断】"]

    # 规则 1：置信度
    if state["confidence"] < 0.7:
        blocked = True
        reason = f"置信度 {state['confidence']:.2f} < 0.7"
        logs.append(f"   触发: 置信度过低")

    # 规则 2：情感
    elif state["sentiment"] < -0.8:
        blocked = True
        reason = "用户情绪极度负面"
        logs.append(f"   触发: 情感负面")

    # 规则 3：金额
    elif state.get("policy_result", {}).get("reason") == "金额超限":
        blocked = True
        reason = f"金额超限 ¥{state['order_info']['amount']}"
        logs.append(f"   触发: 金额超限")

    # 规则 4：LLM 建议转人工
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

    # 敏感词过滤
    sensitive_words = ["傻逼", "骗子", "垃圾", "妈的"]
    for word in sensitive_words:
        if word in response:
            logs.append(f"   ❌ 命中敏感词: {word}")
            return {
                "response": "系统检测到异常内容，已转人工处理。",
                "thinking_log": logs
            }

    # 金额一致性校验
    order = state.get("order_info")
    if order and "amount" in order:
        import re
        amounts = re.findall(r"¥?(\d+)", response)
        if amounts and str(order["amount"]) not in amounts:
            logs.append("   ⚠️ 回复中金额与订单不一致")
        else:
            logs.append("   ✓ 金额一致性通过")

    logs.append("   结果: 校验通过")
    return {"thinking_log": logs}


# ============ 8. 路由函数（代码硬路由） ============

def route_after_intent(state: AgentState) -> Literal["retrieve", "escalate_gate"]:
    if state["intent"] in ["shipping", "refund", "order_status"] and state["confidence"] >= 0.7:
        return "retrieve"
    return "escalate_gate"


def route_after_retrieve(state: AgentState) -> Literal["policy_check", "reason"]:
    if state["intent"] == "refund":
        return "policy_check"
    return "reason"


def route_after_policy(state: AgentState) -> Literal["reason"]:
    return "reason"


def route_after_reason(state: AgentState) -> Literal["contract_check"]:
    return "contract_check"


def route_after_contract(state: AgentState) -> Literal["escalate_gate"]:
    return "escalate_gate"


def route_after_escalate(state: AgentState) -> Literal["generate"]:
    return "generate"


# ============ 9. 构建状态机 ============

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
app = workflow.compile(checkpointer=memory)


# ============ 10. Gradio 演示界面 ============

def chat(message: str, history: list, session_id: str = "demo"):
    config = {"configurable": {"thread_id": session_id}}

    result = app.invoke({
        "user_query": message,
        "thinking_log": [],
        "contract_violations": [],
        "blocked": False,
        "policy_cited": False
    }, config)

    # 组装思考过程
    thinking = "\n".join(result.get("thinking_log", []))

    summary = []
    summary.append("=" * 40)
    summary.append(f"🎯 最终决策: {'✅ 自动处理' if not result.get('blocked') else '🔴 转人工'}")
    summary.append(f"📝 最终回复: {result.get('response', '')[:80]}...")
    if result.get("contract_violations"):
        summary.append(f"⚠️ 契约违约: {len(result['contract_violations'])} 处")
    summary.append("=" * 40)

    full_thinking = "\n".join(summary) + "\n\n" + thinking

    return result.get("response", ""), full_thinking


def create_ui():
    with gr.Blocks(title="客服 Agent 演示 v3 — 完整接口契约") as demo:
        gr.Markdown("""
        # 🤖 客服 Agent 演示 v3 —— 接口契约驱动

        **设计原则：接口契约是 LLM 与确定性系统之间的"协议层"**

        ---
        **🧠 LLM 语义层（带 Pydantic 输出契约）：**
        - `IntentSchema` → `ReasonSchema` → `GenerateSchema`

        **⚙️ 代码校验层（契约强制）：**
        - 白名单检查 | 格式校验 | 金额一致性 | 敏感词过滤

        **🔄 Reducer 合并语义：**
        - Fan-out：并行查询订单 + FAQ
        - Fan-in：结果合并到 State

        ---
        **演示用例：**
        - `我的订单 123456789012345678 到哪了？` → 自动物流查询
        - `我想退款，订单号 876543210987654321` → 小额自动退款
        - `我要退 iPhone，订单 123456789012345678` → 金额超限(¥8999>¥5000)，代码拦截
        - `你们这群骗子！` → 情感负面，代码拦截
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
                    label="🧠 Agent 决策过程（契约驱动）",
                    lines=28,
                    max_lines=40,
                    interactive=False,
                    value="发送消息后，此处展示每个节点的契约校验过程..."
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
        clear.click(lambda: ([], "发送消息后，此处展示每个节点的契约校验过程..."), None, [chatbot, thinking])

    return demo


if __name__ == "__main__":
    demo = create_ui()
    demo.launch(
        share=False,
        server_name="0.0.0.0",
        server_port=7860
    )
