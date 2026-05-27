"""
客服 Agent 演示版
一个下午能跑起来的 LangGraph 客服 Agent，用于现场演示。
- 前端：Gradio（浏览器打开即可演示）
- 后端：LangGraph（完整的意图识别→检索→生成→人工兜底链路）
- 工具：Mock 数据（无需真实 API）
- 展示：实时显示 Agent 思考过程（State 变化）
"""

from typing import TypedDict, Annotated, Optional, Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage
import json
import gradio as gr
import time

# ============ 1. State Schema（演示版，极简） ============

class AgentState(TypedDict):
    user_query: str
    intent: Optional[Literal["shipping", "refund", "order_status", "other"]]
    confidence: float
    order_id: Optional[str]
    order_info: Optional[dict]
    policy_result: Optional[dict]
    response: Optional[str]
    requires_human: bool
    reason: Optional[str]
    # 用于展示 Agent "思考过程"
    thinking_log: Annotated[list, lambda x, y: x + y]

# ============ 2. Mock 数据（演示用，无需真实 API） ============

MOCK_ORDERS = {
    "123456789012345678": {
        "order_id": "123456789012345678",
        "product": "iPhone 15 Pro",
        "amount": 8999,
        "status": "已发货",
        "tracking_no": "SF1029384756",
        "created_at": "2025-05-20",
        "carrier": "顺丰速运"
    },
    "876543210987654321": {
        "order_id": "876543210987654321",
        "product": "蓝牙耳机 AirPods",
        "amount": 199,
        "status": "待发货",
        "tracking_no": None,
        "created_at": "2025-05-26",
        "carrier": None
    }
}

MOCK_TRACKING = {
    "SF1029384756": [
        {"time": "2025-05-25 14:30", "status": "已签收", "location": "上海市浦东新区"},
        {"time": "2025-05-25 08:00", "status": "派送中", "location": "上海市"},
        {"time": "2025-05-24 20:00", "status": "运输中", "location": "杭州市"},
    ]
}

# ============ 3. LLM 初始化 ============

llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.1,
    api_key="your-api-key",  # 演示时替换为真实 key
    base_url="https://api.openai.com/v1"
)

# ============ 4. 节点实现 ============

def intent_node(state: AgentState) -> AgentState:
    """意图识别节点：理解用户想做什么"""
    prompt = f"""
    分析用户问题，判断意图。可选：shipping(物流查询), refund(退款), order_status(订单状态), other(其他)。
    同时提取18位订单号。
    输出JSON格式：{{"intent": "...", "confidence": 0.0-1.0, "order_id": "..." 或 null}}

    用户问题：{state['user_query']}
    """

    response = llm.invoke(prompt)
    try:
        result = json.loads(response.content)
    except:
        result = {"intent": "other", "confidence": 0.0, "order_id": None}

    return {
        "intent": result.get("intent", "other"),
        "confidence": result.get("confidence", 0.0),
        "order_id": result.get("order_id"),
        "thinking_log": [f"🧠 意图识别：{result.get('intent')} (置信度: {result.get('confidence')})"]
    }


def retrieve_node(state: AgentState) -> AgentState:
    """检索节点：查订单和物流"""
    order_id = state.get("order_id")
    logs = []

    if order_id and order_id in MOCK_ORDERS:
        order_info = MOCK_ORDERS[order_id]
        logs.append(f"📦 查到订单：{order_info['product']}，金额 ¥{order_info['amount']}")

        # 如果已发货，查物流
        if order_info.get("tracking_no"):
            tracking = MOCK_TRACKING.get(order_info["tracking_no"], [])
            order_info["tracking"] = tracking
            logs.append(f"🚚 查到物流：最新状态 {tracking[0]['status'] if tracking else '无'}")
    else:
        order_info = None
        logs.append("⚠️ 未找到订单信息")

    return {
        "order_info": order_info,
        "thinking_log": logs
    }


def policy_node(state: AgentState) -> AgentState:
    """退款政策判断（确定性规则，不用 LLM）"""
    if state["intent"] != "refund":
        return {"thinking_log": []}

    order = state.get("order_info")
    if not order:
        return {
            "policy_result": {"eligible": False, "reason": "未找到订单信息"},
            "thinking_log": ["❌ 退款政策：未找到订单，无法判断"]
        }

    amount = order["amount"]

    # 演示规则：金额 > 5000 必须人工审核
    if amount > 5000:
        return {
            "policy_result": {"eligible": False, "reason": "金额超限，需人工审核"},
            "requires_human": True,
            "reason": f"订单金额 ¥{amount} > ¥5000，触发人工审核规则",
            "thinking_log": [f"⚠️ 退款政策：金额 ¥{amount} 超过自动处理上限"]
        }

    # 简单规则：都允许（演示简化）
    return {
        "policy_result": {"eligible": True, "reason": "符合退款条件"},
        "thinking_log": ["✅ 退款政策：符合自动退款条件"]
    }


def escalate_node(state: AgentState) -> AgentState:
    """升级判断：硬性规则"""
    if state.get("requires_human"):
        return {"thinking_log": [f"🚨 触发人工审核：{state.get('reason', '')}"]}

    # 兜底：置信度太低的也转人工
    if state["confidence"] < 0.7:
        return {
            "requires_human": True,
            "reason": f"意图置信度 {state['confidence']} 过低",
            "thinking_log": [f"🚨 触发人工审核：意图不明确（置信度 {state['confidence']}）"]
        }

    return {"thinking_log": ["✅ 通过自动审核，进入回复生成"]}


def generate_node(state: AgentState) -> AgentState:
    """回复生成节点"""
    intent = state["intent"]
    order = state.get("order_info")

    if state.get("requires_human"):
        return {
            "response": "您好，您的问题比较复杂，正在为您转接人工客服，请稍等...",
            "thinking_log": ["📝 生成转人工提示语"]
        }

    # 物流查询
    if intent == "shipping" and order:
        tracking = order.get("tracking", [])
        if tracking:
            latest = tracking[0]
            response = (
                f"您的订单 **{order['product']}**（订单号：{order['order_id']}）"
                f"最新物流状态：**{latest['status']}**，"
                f"地点：{latest['location']}。\n\n"
                f"承运：{order['carrier']}，运单号：{order['tracking_no']}"
            )
        else:
            response = f"您的订单 **{order['product']}** 尚未发货，请耐心等待。"

    # 订单状态
    elif intent == "order_status" and order:
        response = (
            f"您的订单 **{order['product']}**（订单号：{order['order_id']}）\n"
            f"当前状态：**{order['status']}**\n"
            f"下单时间：{order['created_at']}"
        )

    # 退款
    elif intent == "refund" and order:
        policy = state.get("policy_result", {})
        if policy.get("eligible"):
            response = (
                f"您的订单 **{order['product']}** 符合退款条件。\n"
                f"退款金额：¥{order['amount']}\n"
                f"预计到账时间：3-5 个工作日\n"
                f"退款路径：原支付渠道退回"
            )
        else:
            response = (
                f"很抱歉，您的订单 **{order['product']}** 目前不符合自动退款条件。\n"
                f"原因：{policy.get('reason', '未知')}\n"
                f"建议：联系人工客服进一步处理。"
            )

    else:
        response = "您好，请问有什么可以帮您？您可以提供订单号，我帮您查询。"

    return {
        "response": response,
        "thinking_log": [f"📝 生成回复：{response[:50]}..."]
    }


# ============ 5. 路由函数 ============

def route_after_intent(state: AgentState) -> Literal["retrieve", "escalate"]:
    if state["intent"] in ["shipping", "refund", "order_status"]:
        return "retrieve"
    return "escalate"


def route_after_retrieve(state: AgentState) -> Literal["policy", "escalate"]:
    if state["intent"] == "refund":
        return "policy"
    return "escalate"


def route_after_policy(state: AgentState) -> Literal["escalate"]:
    return "escalate"


# ============ 6. 构建图 ============

workflow = StateGraph(AgentState)

workflow.add_node("intent", intent_node)
workflow.add_node("retrieve", retrieve_node)
workflow.add_node("policy", policy_node)
workflow.add_node("escalate", escalate_node)
workflow.add_node("generate", generate_node)

workflow.set_entry_point("intent")
workflow.add_conditional_edges("intent", route_after_intent)
workflow.add_conditional_edges("retrieve", route_after_retrieve)
workflow.add_conditional_edges("policy", route_after_policy)
workflow.add_edge("escalate", "generate")
workflow.add_edge("generate", END)

# 编译（带内存持久化，演示时能看到历史对话）
memory = MemorySaver()
app = workflow.compile(checkpointer=memory)

# ============ 7. Gradio 前端 ============

def chat_with_agent(message: str, history: list, session_id: str = "demo_session"):
    """
    Gradio 聊天回调。
    返回：(回复内容, 思考过程文本)
    """
    config = {"configurable": {"thread_id": session_id}}

    # 运行 Agent
    result = app.invoke({
        "user_query": message,
        "thinking_log": []
    }, config)

    # 组装思考过程展示
    thinking = "\n".join(result.get("thinking_log", []))

    # 如果转人工，在思考过程里高亮
    if result.get("requires_human"):
        thinking += "\n\n🔴 **最终决策：转人工客服处理**"

    return result.get("response", "抱歉，我暂时无法理解您的问题。"), thinking


def create_demo_ui():
    with gr.Blocks(title="客服 Agent 演示", theme=gr.themes.Soft()) as demo:
        gr.Markdown("""
        # 🤖 智能客服 Agent 演示

        基于 **LangGraph** 的客服 Agent，支持：物流查询、订单状态、退款咨询。

        **演示用例：**
        - `我的订单 123456789012345678 到哪了？` → 物流查询
        - `我想退款，订单号 876543210987654321` → 退款（小额自动通过）
        - `我要退 iPhone，订单 123456789012345678` → 退款（大额触发人工）
        - `你好` → 意图不明确，转人工
        """)

        with gr.Row():
            with gr.Column(scale=2):
                chatbot = gr.Chatbot(
                    label="对话",
                    height=400,
                    bubble_full_width=False
                )
                msg_input = gr.Textbox(
                    label="输入消息",
                    placeholder="请输入您的问题...",
                    lines=1
                )
                with gr.Row():
                    submit_btn = gr.Button("发送", variant="primary")
                    clear_btn = gr.Button("清空对话")

            with gr.Column(scale=1):
                thinking_output = gr.Textbox(
                    label="🧠 Agent 思考过程（实时 State 变化）",
                    lines=20,
                    max_lines=30,
                    interactive=False,
                    value="发送消息后，这里会显示 Agent 的决策过程..."
                )

        # 会话 ID（用于 LangGraph Checkpoint）
        session_state = gr.State(value="demo_session_001")

        def respond(message, chat_history, session_id):
            if not message.strip():
                return "", chat_history, "请输入内容..."

            response, thinking = chat_with_agent(message, chat_history, session_id)

            chat_history.append([message, response])
            return "", chat_history, thinking

        submit_btn.click(
            respond,
            inputs=[msg_input, chatbot, session_state],
            outputs=[msg_input, chatbot, thinking_output]
        )

        msg_input.submit(
            respond,
            inputs=[msg_input, chatbot, session_state],
            outputs=[msg_input, chatbot, thinking_output]
        )

        clear_btn.click(lambda: (None, []), None, [thinking_output, chatbot], queue=False)

    return demo


if __name__ == "__main__":
    demo = create_demo_ui()
    demo.launch(share=False, server_name="0.0.0.0", server_port=7860)
