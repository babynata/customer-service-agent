"""
Gradio 演示界面

左侧：用户对话窗口
右侧：Agent 决策过程展示（契约驱动）+ 人工客服工作台
"""

import gradio as gr

from graph import agent_app

NODE_ORDER = [
    ("intent_understand", "🧠 意图理解", "LLM"),
    ("retrieve", "⚙️ 数据检索", "代码"),
    ("policy_check", "⚙️ 政策校验", "代码"),
    ("reason", "🧠 推理决策", "LLM"),
    ("contract_check", "⚙️ 契约校验", "代码"),
    ("escalate_gate", "⚙️ 升级判断", "代码"),
    ("generate", "📝 回复生成", "LLM"),
    ("final_check", "⚙️ 最终校验", "代码"),
]

NODE_TAG_MAP = {
    "意图理解": "intent_understand",
    "数据检索": "retrieve",
    "政策校验": "policy_check",
    "推理决策": "reason",
    "契约校验": "contract_check",
    "升级判断": "escalate_gate",
    "回复生成": "generate",
    "最终校验": "final_check",
}

FLOW_CSS = """
<style>
.flow-container {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 10px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}
.flow-node {
    display: flex;
    align-items: center;
    padding: 8px 12px;
    border-radius: 8px;
    border: 1px solid #e5e7eb;
    background: #f9fafb;
    transition: all 0.3s ease;
    position: relative;
}
.flow-node.done {
    background: #dcfce7;
    border-color: #86efac;
}
.flow-node.blocked {
    background: #fee2e2;
    border-color: #fca5a5;
    animation: pulse-red 2s infinite;
}
.flow-node.skipped {
    background: #f3f4f6;
    border-color: #d1d5db;
    opacity: 0.5;
}
.flow-node.active {
    background: #dbeafe;
    border-color: #93c5fd;
    animation: pulse-blue 2s infinite;
}
.flow-icon {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    margin-right: 10px;
    flex-shrink: 0;
}
.flow-node.done .flow-icon { background: #22c55e; color: white; }
.flow-node.blocked .flow-icon { background: #ef4444; color: white; }
.flow-node.skipped .flow-icon { background: #9ca3af; color: white; }
.flow-node.active .flow-icon { background: #3b82f6; color: white; }
.flow-title { font-weight: 600; font-size: 13px; }
.flow-type { font-size: 11px; color: #6b7280; margin-left: auto; }
.flow-arrow {
    text-align: center;
    color: #9ca3af;
    font-size: 12px;
    line-height: 1;
}
@keyframes pulse-blue {
    0% { box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.4); }
    70% { box-shadow: 0 0 0 6px rgba(59, 130, 246, 0); }
    100% { box-shadow: 0 0 0 0 rgba(59, 130, 246, 0); }
}
@keyframes pulse-red {
    0% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4); }
    70% { box-shadow: 0 0 0 6px rgba(239, 68, 68, 0); }
    100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }
}
</style>
"""


def infer_flow_state(thinking_log: list[str]) -> dict[str, str]:
    """根据 thinking_log 推断每个节点的状态"""
    executed = set()
    blocked_node = None

    for line in thinking_log:
        for tag, node_id in NODE_TAG_MAP.items():
            if tag in line:
                executed.add(node_id)
                # 判断该节点是否触发拦截
                if node_id in ("contract_check", "escalate_gate", "policy_check"):
                    if any(k in line for k in ("拦截", "已拦截", "触发:", "金额超限")):
                        if blocked_node is None:
                            blocked_node = node_id

    flow = {}
    blocked_reached = False
    for node_id, name, typ in NODE_ORDER:
        if blocked_reached:
            flow[node_id] = "skipped"
            continue
        if node_id == blocked_node:
            flow[node_id] = "blocked"
            blocked_reached = True
            continue
        if node_id in executed:
            flow[node_id] = "done"
        else:
            # 在 blocked 之前但未执行 → skipped
            flow[node_id] = "skipped"

    return flow


def build_flow_html(flow_state: dict[str, str]) -> str:
    """根据 flow_state 生成 HTML 流程图"""
    nodes_html = []
    for i, (node_id, name, typ) in enumerate(NODE_ORDER):
        status = flow_state.get(node_id, "skipped")
        cls = status
        icon = "✓" if status == "done" else "✗" if status == "blocked" else "−"
        if status == "active":
            icon = "●"
        nodes_html.append(
            f'<div class="flow-node {cls}">'
            f'<div class="flow-icon">{icon}</div>'
            f'<div class="flow-title">{name}</div>'
            f'<div class="flow-type">{typ}</div>'
            f'</div>'
        )
        if i < len(NODE_ORDER) - 1:
            nodes_html.append('<div class="flow-arrow">↓</div>')

    return FLOW_CSS + '<div class="flow-container">\n' + "\n".join(nodes_html) + "\n</div>"


def chat(message: str, history: list, session_id: str = "demo"):
    """单次对话处理，保留多轮记忆"""
    config = {"configurable": {"thread_id": session_id}}

    # 追加用户消息到对话历史，LangGraph 的 add_messages Reducer 会自动合并
    result = agent_app.invoke({
        "user_query": message,
        "messages": [{"role": "user", "content": message}],
        "thinking_log": [],
        "contract_violations": [],
        "blocked": False,
        "policy_cited": False
    }, config)

    thinking = "\n".join(result.get("thinking_log", []))

    summary = []
    summary.append("=" * 40)
    summary.append(f"🎯 最终决策: {'✅ 自动处理' if not result.get('blocked') else '🔴 转人工'}")
    summary.append(f"📝 最终回复: {result.get('response', '')[:80]}...")
    if result.get("contract_violations"):
        summary.append(f"⚠️ 契约违约: {len(result['contract_violations'])} 处")
    summary.append("=" * 40)

    full_thinking = "\n".join(summary) + "\n\n" + thinking

    # 节点流转可视化
    flow_state = infer_flow_state(result.get("thinking_log", []))
    flow_html = build_flow_html(flow_state)

    # 组装人工工作台数据
    blocked = result.get("blocked", False)
    order = result.get("order_info") or {}
    intent = result.get("intent", "other")
    sentiment = result.get("sentiment", 0.0)
    confidence = result.get("confidence", 0.0)
    entities = result.get("entities", {})
    block_reason = result.get("block_reason", "")
    turn_count = result.get("turn_count", 0)

    # 对话摘要（用户+助手消息精简列表）
    messages = result.get("messages", [])
    dialog_summary = []
    for msg in messages:
        role_label = "用户" if msg.get("role") == "user" else "客服"
        content = msg.get("content", "")[:60]
        dialog_summary.append(f"{role_label}：{content}...")

    key_info = f"""
意图：{intent} | 置信度：{confidence:.2f} | 情感：{sentiment:.2f}
订单号：{entities.get('order_id', '无')} | 手机号：{entities.get('phone', '无')}
商品：{order.get('product', '无')} | 金额：¥{order.get('amount', 0)}
拦截原因：{block_reason or '无'}
    """.strip()

    return (
        result.get("response", ""),
        full_thinking,
        flow_html,
        blocked,
        "\n".join(dialog_summary),
        key_info,
        turn_count,
    )


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
                with gr.Tabs(elem_id="right_tabs") as right_tabs:
                    with gr.TabItem("🧠 Agent 决策过程"):
                        flow_html_box = gr.HTML(label="节点流转")
                        thinking = gr.Textbox(
                            label="Agent 决策过程（契约驱动）",
                            lines=18,
                            max_lines=30,
                            interactive=False,
                            value="发送消息后，此处展示每个节点的契约校验过程..."
                        )

                    with gr.TabItem("👤 人工客服工作台"):
                        manual_alert = gr.Markdown("")
                        turn_info = gr.Textbox(
                            label="会话信息", interactive=False, value=""
                        )
                        key_info_box = gr.Textbox(
                            label="关键信息", interactive=False, lines=4, value=""
                        )
                        dialog_summary_box = gr.Textbox(
                            label="对话摘要", interactive=False, lines=8, value=""
                        )
                        manual_reply = gr.Textbox(
                            label="人工回复", placeholder="输入人工客服回复..."
                        )
                        manual_send = gr.Button("发送回复", variant="secondary")

        session = gr.State(value="demo_001")
        blocked_state = gr.State(value=False)

        def respond(message, history, sid):
            if not message.strip():
                return "", history, "", "", False, "", "", 0, gr.Tabs(selected=0), ""
            resp, think, flow_html, blocked, dialog_summary, key_info, turn_count = chat(
                message, history, sid
            )
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": resp})
            tab_index = 1 if blocked else 0
            alert_md = "### ⚠️ 已触发人工接管" if blocked else ""
            return (
                "",
                history,
                flow_html,
                think,
                blocked,
                dialog_summary,
                key_info,
                turn_count,
                gr.Tabs(selected=tab_index),
                alert_md,
            )

        def send_manual_reply(reply_text, history):
            if not reply_text.strip():
                return history, ""
            history.append({"role": "assistant", "content": reply_text})
            return history, ""

        send.click(
            respond,
            [msg, chatbot, session],
            [
                msg, chatbot, flow_html_box, thinking, blocked_state,
                dialog_summary_box, key_info_box, turn_info, right_tabs, manual_alert,
            ],
        )
        msg.submit(
            respond,
            [msg, chatbot, session],
            [
                msg, chatbot, flow_html_box, thinking, blocked_state,
                dialog_summary_box, key_info_box, turn_info, right_tabs, manual_alert,
            ],
        )
        clear.click(
            lambda: (
                [],
                "",
                "发送消息后，此处展示每个节点的契约校验过程...",
                False,
                "",
                "",
                0,
                gr.Tabs(selected=0),
                "",
            ),
            None,
            [
                chatbot, flow_html_box, thinking, blocked_state,
                dialog_summary_box, key_info_box, turn_info, right_tabs, manual_alert,
            ],
        )
        manual_send.click(
            send_manual_reply,
            [manual_reply, chatbot],
            [chatbot, manual_reply]
        )

    return demo


if __name__ == "__main__":
    demo = create_ui()
    demo.launch(share=False, server_name="0.0.0.0", server_port=7860)
