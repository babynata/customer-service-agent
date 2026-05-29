"""
Gradio 演示界面

左侧：用户对话窗口
右侧：Agent 决策过程展示（契约驱动）+ 人工客服工作台
"""

import gradio as gr

from graph import agent_app


def _msg_to_dict(msg) -> dict:
    """兼容 LangChain Message 对象和普通 dict"""
    if hasattr(msg, "type") and hasattr(msg, "content"):
        return {"role": "user" if msg.type == "human" else "assistant", "content": msg.content}
    return msg if isinstance(msg, dict) else {"role": "user", "content": str(msg)}

def chat(message: str, history: list, session_id: str = "demo", variant: str = "A"):
    """单次对话处理，保留多轮记忆"""
    config = {"configurable": {"thread_id": session_id}}

    # 追加用户消息到对话历史，LangGraph 的 add_messages Reducer 会自动合并
    # 不传入 thinking_log / contract_violations，让 checkpoint 保留历史值
    result = agent_app.invoke({
        "user_query": message,
        "messages": [{"role": "user", "content": message}],
        "blocked": False,
        "policy_cited": False,
        "variant": variant,
    }, config)

    # 组装当前轮的决策日志
    current_thinking = "\n".join(result.get("thinking_log", []))

    turn_count = sum(
        1 for m in result.get("messages", []) if _msg_to_dict(m).get("role") == "user"
    )

    summary = []
    summary.append(f"📌 第 {turn_count} 轮")
    summary.append(f"🎯 最终决策: {'✅ 自动处理' if not result.get('blocked') else '🔴 转人工'}")
    summary.append(f"📝 最终回复: {result.get('response', '')[:80]}...")
    if result.get("contract_violations"):
        summary.append(f"⚠️ 契约违约: {len(result['contract_violations'])} 处")
    summary.append("-" * 40)

    round_thinking = "\n".join(summary) + "\n" + current_thinking

    # 组装人工工作台数据
    blocked = result.get("blocked", False)
    order = result.get("order_info") or {}
    intent = result.get("intent", "other")
    sentiment = result.get("sentiment", 0.0)
    confidence = result.get("confidence", 0.0)
    entities = result.get("entities", {})
    block_reason = result.get("block_reason", "")

    messages = result.get("messages", [])
    dialog_summary = []
    for msg in messages:
        m = _msg_to_dict(msg)
        role_label = "用户" if m.get("role") == "user" else "客服"
        content = m.get("content", "")[:60]
        dialog_summary.append(f"{role_label}：{content}...")

    key_info = f"""
意图：{intent} | 置信度：{confidence:.2f} | 情感：{sentiment:.2f}
订单号：{entities.get('order_id', '无')} | 手机号：{entities.get('phone', '无')}
商品：{order.get('product', '无')} | 金额：¥{order.get('amount', 0)}
拦截原因：{block_reason or '无'}
    """.strip()

    return (
        result.get("response", ""),
        round_thinking,
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
                strategy_select = gr.Dropdown(
                    label="回复策略",
                    choices=["A", "B"],
                    value="A",
                    interactive=True,
                )
                gr.Markdown("""
                **策略说明：**
                - **A**：标准客服，礼貌简洁
                - **B**：亲切有温度，主动解释原因
                """)

            with gr.Column(scale=1):
                with gr.Tabs(elem_id="right_tabs") as right_tabs:
                    with gr.TabItem("🧠 Agent 决策过程"):
                        with gr.Row():
                            round_select = gr.Dropdown(
                                label="选择轮次",
                                choices=[],
                                value=None,
                                interactive=True,
                            )
                        thinking_meta = gr.Markdown("当前轮次暂无模型路由信息")
                        thinking = gr.Textbox(
                            label="Agent 决策过程（契约驱动）",
                            lines=26,
                            max_lines=45,
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
                        export_btn = gr.Button("📥 导出会话 JSON", variant="secondary")
                        export_file = gr.File(label="导出文件", visible=False)
                        manual_reply = gr.Textbox(
                            label="人工回复", placeholder="输入人工客服回复..."
                        )
                        manual_send = gr.Button("发送回复", variant="secondary")

        session = gr.State(value="demo_001")
        blocked_state = gr.State(value=False)
        thinking_by_round_state = gr.State(value={})

        def _render_thinking(thinking_dict: dict, selected_round: int) -> str:
            return thinking_dict.get(selected_round, "")

        def _extract_meta(thinking_text: str) -> str:
            """从 thinking_log 中提取模型路由和策略版本信息"""
            lines = thinking_text.split("\n")
            meta_parts = []
            for line in lines:
                if "模型:" in line or "策略版本:" in line:
                    # 去掉前面的空格，加粗显示
                    clean = line.strip()
                    if "模型:" in clean:
                        meta_parts.append(f"- **{clean}**")
                    else:
                        meta_parts.append(f"- {clean}")
            return "\n".join(meta_parts) if meta_parts else "当前轮次暂无模型路由信息"

        def respond(message, history, sid, thinking_dict, variant):
            if not message.strip():
                return (
                    "", history, gr.Dropdown(), "", False, "", "", "",
                    gr.Tabs(selected=0), "", thinking_dict, "",
                )
            resp, think, blocked, dialog_summary, key_info, turn_count = chat(
                message, history, sid, variant
            )
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": f"🤖 {resp}"})

            # 按轮次存储决策日志
            thinking_dict[turn_count] = think
            round_choices = list(thinking_dict.keys())
            latest_round = turn_count

            tab_index = 1 if blocked else 0
            alert_md = "### ⚠️ 已触发人工接管" if blocked else ""
            turn_info_str = f"会话 ID: {sid} | 已对话 {turn_count} 轮"
            meta_md = _extract_meta(think)
            return (
                "",
                history,
                gr.Dropdown(choices=round_choices, value=latest_round),
                meta_md,
                think,
                blocked,
                dialog_summary,
                key_info,
                turn_info_str,
                gr.Tabs(selected=tab_index),
                alert_md,
                thinking_dict,
            )

        def send_manual_reply(reply_text, history):
            if not reply_text.strip():
                return history, ""
            history.append({"role": "assistant", "content": f"👤 {reply_text}"})
            return history, ""

        def _render_thinking_full(thinking_dict: dict, selected_round: int):
            text = thinking_dict.get(selected_round, "")
            return text, _extract_meta(text)

        send.click(
            respond,
            [msg, chatbot, session, thinking_by_round_state, strategy_select],
            [
                msg, chatbot, round_select, thinking_meta, thinking, blocked_state,
                dialog_summary_box, key_info_box, turn_info, right_tabs, manual_alert,
                thinking_by_round_state,
            ],
        )
        msg.submit(
            respond,
            [msg, chatbot, session, thinking_by_round_state, strategy_select],
            [
                msg, chatbot, round_select, thinking_meta, thinking, blocked_state,
                dialog_summary_box, key_info_box, turn_info, right_tabs, manual_alert,
                thinking_by_round_state,
            ],
        )
        import uuid

        def _clear_all():
            return (
                [],
                gr.Dropdown(choices=[], value=None),
                "当前轮次暂无模型路由信息",
                "发送消息后，此处展示每个节点的契约校验过程...",
                False,
                "",
                "",
                "",
                gr.Tabs(selected=0),
                "",
                {},
                f"demo_{uuid.uuid4().hex[:8]}",
            )

        clear.click(
            _clear_all,
            None,
            [
                chatbot, round_select, thinking_meta, thinking, blocked_state,
                dialog_summary_box, key_info_box, turn_info, right_tabs, manual_alert,
                thinking_by_round_state, session,
            ],
        )
        round_select.change(
            _render_thinking_full,
            [thinking_by_round_state, round_select],
            [thinking, thinking_meta],
        )
        manual_send.click(
            send_manual_reply,
            [manual_reply, chatbot],
            [chatbot, manual_reply]
        )

        def export_session(sid, thinking_dict, history):
            import json, tempfile, os
            data = {
                "session_id": sid,
                "messages": history,
                "thinking_by_round": {str(k): v for k, v in thinking_dict.items()},
            }
            fd, path = tempfile.mkstemp(suffix=".json", prefix=f"session_{sid}_")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return gr.File(value=path, visible=True)

        export_btn.click(
            export_session,
            [session, thinking_by_round_state, chatbot],
            export_file,
        )

    return demo


if __name__ == "__main__":
    demo = create_ui()
    demo.launch(share=False, server_name="0.0.0.0", server_port=7860)
