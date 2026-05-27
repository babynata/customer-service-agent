"""
Gradio 演示界面

左侧：用户对话窗口
右侧：Agent 决策过程展示（契约驱动）
"""

import gradio as gr

from graph import agent_app


def chat(message: str, history: list, session_id: str = "demo"):
    """单次对话处理"""
    config = {"configurable": {"thread_id": session_id}}

    result = agent_app.invoke({
        "user_query": message,
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
        clear.click(
            lambda: ([], "发送消息后，此处展示每个节点的契约校验过程..."),
            None, [chatbot, thinking]
        )

    return demo


if __name__ == "__main__":
    demo = create_ui()
    demo.launch(share=False, server_name="0.0.0.0", server_port=7860)
