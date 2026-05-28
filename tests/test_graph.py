"""
图集成测试

验证完整的状态机从 entry 到 END 的流转路径。
由于 LangGraph 编译后的图需要 checkpoint，测试使用 MemorySaver。
"""

import pytest
from unittest.mock import patch, MagicMock

from graph.builder import build_agent_graph


@pytest.fixture
def compiled_graph():
    """每次测试使用全新的编译图"""
    return build_agent_graph()


class TestHappyPath:
    """正常流程：意图识别 → 检索 → 推理 → 生成"""

    def test_shipping_query_auto_resolved(self, compiled_graph):
        """物流查询自动处理"""
        mock_intent = MagicMock()
        mock_intent.intent = "shipping"
        mock_intent.confidence = 0.92
        mock_intent.sentiment = 0.3
        mock_intent.entities = {"order_id": "123456789012345678"}

        mock_reason = MagicMock()
        mock_reason.analysis = "订单已发货"
        mock_reason.can_auto_resolve = True
        mock_reason.plan = "查询物流"
        mock_reason.escalate_reason = None

        mock_generate = MagicMock()
        mock_generate.response = "已发货，预计明天到"
        mock_generate.policy_cited = False
        mock_generate.confidence = 0.95

        with patch("nodes.llm_nodes.llm_intent") as mi, \
             patch("nodes.llm_nodes.llm_reason") as mr, \
             patch("nodes.llm_nodes.llm_generate") as mg:
            mi.invoke.return_value = mock_intent
            mr.invoke.return_value = mock_reason
            mg.invoke.return_value = mock_generate

            config = {"configurable": {"thread_id": "test_shipping"}}
            result = compiled_graph.invoke({
                "user_query": "我的订单到哪了",
                "messages": [{"role": "user", "content": "我的订单到哪了"}],
            }, config)

        assert result["intent"] == "shipping"
        assert result["blocked"] is False
        assert "已发货" in result["response"]
        assert result["order_info"] is not None

    def test_small_refund_auto_resolved(self, compiled_graph):
        """小额退款自动处理"""
        mock_intent = MagicMock()
        mock_intent.intent = "refund"
        mock_intent.confidence = 0.88
        mock_intent.sentiment = -0.1
        mock_intent.entities = {"order_id": "876543210987654321"}

        mock_reason = MagicMock()
        mock_reason.analysis = "符合退款条件"
        mock_reason.can_auto_resolve = True
        mock_reason.plan = "自动退款"
        mock_reason.escalate_reason = None

        mock_generate = MagicMock()
        mock_generate.response = "已为您办理退款"
        mock_generate.policy_cited = True
        mock_generate.confidence = 0.9

        with patch("nodes.llm_nodes.llm_intent") as mi, \
             patch("nodes.llm_nodes.llm_reason") as mr, \
             patch("nodes.llm_nodes.llm_generate") as mg:
            mi.invoke.return_value = mock_intent
            mr.invoke.return_value = mock_reason
            mg.invoke.return_value = mock_generate

            config = {"configurable": {"thread_id": "test_refund"}}
            result = compiled_graph.invoke({
                "user_query": "我要退款",
                "messages": [{"role": "user", "content": "我要退款"}],
            }, config)

        assert result["intent"] == "refund"
        assert result["policy_result"]["eligible"] is True
        assert result["blocked"] is False
        assert result["policy_cited"] is True


class TestBlockedPath:
    """拦截流程：因规则触发 block"""

    def test_high_amount_blocked(self, compiled_graph):
        """高金额退款被拦截"""
        mock_intent = MagicMock()
        mock_intent.intent = "refund"
        mock_intent.confidence = 0.9
        mock_intent.sentiment = -0.2
        mock_intent.entities = {"order_id": "123456789012345678"}

        mock_reason = MagicMock()
        mock_reason.analysis = "金额超限"
        mock_reason.can_auto_resolve = False
        mock_reason.plan = ""
        mock_reason.escalate_reason = "金额超限 ¥8999"

        with patch("nodes.llm_nodes.llm_intent") as mi, \
             patch("nodes.llm_nodes.llm_reason") as mr, \
             patch("nodes.llm_nodes.llm_generate") as mg:
            mi.invoke.return_value = mock_intent
            mr.invoke.return_value = mock_reason
            mg.invoke.return_value = MagicMock(
                response="转人工", policy_cited=False, confidence=0.5
            )

            config = {"configurable": {"thread_id": "test_block"}}
            result = compiled_graph.invoke({
                "user_query": "我要退 iPhone",
                "messages": [{"role": "user", "content": "我要退 iPhone"}],
            }, config)

        assert result["blocked"] is True
        assert "金额超限" in result["block_reason"]
        assert "人工客服" in result["response"]

    def test_negative_sentiment_blocked(self, compiled_graph):
        """负面情绪被拦截"""
        mock_intent = MagicMock()
        mock_intent.intent = "refund"
        mock_intent.confidence = 0.95
        mock_intent.sentiment = -0.95
        mock_intent.entities = {"order_id": "123456789012345678"}

        with patch("nodes.llm_nodes.llm_intent") as mi, \
             patch("nodes.llm_nodes.llm_reason") as mr, \
             patch("nodes.llm_nodes.llm_generate") as mg:
            mi.invoke.return_value = mock_intent
            mr.invoke.return_value = MagicMock(
                analysis="用户情绪极度负面", can_auto_resolve=False, plan="", escalate_reason="用户情绪极度负面"
            )
            mg.invoke.return_value = MagicMock(
                response="转人工", policy_cited=False, confidence=0.5
            )

            config = {"configurable": {"thread_id": "test_sentiment"}}
            result = compiled_graph.invoke({
                "user_query": "你们这群骗子",
                "messages": [{"role": "user", "content": "你们这群骗子"}],
            }, config)

        assert result["blocked"] is True
        assert "情绪" in result["block_reason"]


class TestMultiTurn:
    """多轮对话记忆测试"""

    def test_second_turn_remembers_order(self, compiled_graph):
        """第二轮追问时记得第一轮提到的订单号"""
        mock_intent_1 = MagicMock()
        mock_intent_1.intent = "shipping"
        mock_intent_1.confidence = 0.92
        mock_intent_1.sentiment = 0.3
        mock_intent_1.entities = {"order_id": "123456789012345678"}

        mock_reason_1 = MagicMock()
        mock_reason_1.analysis = "已发货"
        mock_reason_1.can_auto_resolve = True
        mock_reason_1.plan = "查询物流"
        mock_reason_1.escalate_reason = None

        mock_generate_1 = MagicMock()
        mock_generate_1.response = "已发货"
        mock_generate_1.policy_cited = False
        mock_generate_1.confidence = 0.95

        mock_intent_2 = MagicMock()
        mock_intent_2.intent = "shipping"
        mock_intent_2.confidence = 0.9
        mock_intent_2.sentiment = 0.2
        mock_intent_2.entities = {"order_id": "123456789012345678"}  # 从历史中提取到订单号

        mock_reason_2 = MagicMock()
        mock_reason_2.analysis = "追问物流"
        mock_reason_2.can_auto_resolve = True
        mock_reason_2.plan = "继续查询"
        mock_reason_2.escalate_reason = None

        mock_generate_2 = MagicMock()
        mock_generate_2.response = "预计明天送达"
        mock_generate_2.policy_cited = False
        mock_generate_2.confidence = 0.9

        config = {"configurable": {"thread_id": "test_multiturn"}}

        with patch("nodes.llm_nodes.llm_intent") as mi, \
             patch("nodes.llm_nodes.llm_reason") as mr, \
             patch("nodes.llm_nodes.llm_generate") as mg:
            # 第一轮
            mi.invoke.return_value = mock_intent_1
            mr.invoke.return_value = mock_reason_1
            mg.invoke.return_value = mock_generate_1

            result_1 = compiled_graph.invoke({
                "user_query": "我的订单 123456789012345678 到哪了",
                "messages": [{"role": "user", "content": "我的订单 123456789012345678 到哪了"}],
            }, config)

            # 第二轮（没有订单号）
            mi.invoke.return_value = mock_intent_2
            mr.invoke.return_value = mock_reason_2
            mg.invoke.return_value = mock_generate_2

            result_2 = compiled_graph.invoke({
                "user_query": "那什么时候能到",
                "messages": [{"role": "user", "content": "那什么时候能到"}],
            }, config)

        # 验证第二轮的 prompt 中包含了第一轮的对话历史
        second_intent_prompt = mi.invoke.call_args_list[1][0][0]
        assert "123456789012345678" in second_intent_prompt
        assert "已发货" in second_intent_prompt

        assert result_2["order_info"] is not None  # checkpoint 保留了订单信息
