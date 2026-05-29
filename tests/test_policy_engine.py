"""
政策规则引擎测试

验证规则加载、匹配、热更新逻辑。
"""

import pytest
from config.policy_engine import PolicyEngine, Condition, Action, PolicyRule


class TestPolicyEngine:
    """规则引擎核心测试"""

    def test_default_rules_loaded(self):
        """默认规则正确加载"""
        engine = PolicyEngine()
        assert len(engine.rules) >= 2
        assert engine.rules[0].name == "high_amount_refund"
        assert engine.rules[0].priority > engine.rules[1].priority

    def test_high_amount_refund_blocked(self):
        """大额退款被拦截"""
        engine = PolicyEngine()
        context = {
            "intent": "refund",
            "order": {"amount": 8999, "product": "iPhone"},
            "amount": 8999,
        }
        action = engine.evaluate(context)

        assert action is not None
        assert action.eligible is False
        assert action.reason == "金额超限"
        assert action.escalate is True

    def test_small_amount_refund_allowed(self):
        """小额退款自动通过"""
        engine = PolicyEngine()
        context = {
            "intent": "refund",
            "order": {"amount": 1999, "product": "AirPods"},
            "amount": 1999,
        }
        action = engine.evaluate(context)

        assert action is not None
        assert action.eligible is True
        assert action.reason == "符合退款条件"
        assert action.escalate is False

    def test_non_refund_no_match(self):
        """非退款意图无匹配规则"""
        engine = PolicyEngine()
        context = {
            "intent": "shipping",
            "order": {"amount": 100},
            "amount": 100,
        }
        action = engine.evaluate(context)

        assert action is None

    def test_field_path_nested(self):
        """嵌套字段路径解析"""
        engine = PolicyEngine()
        assert engine._get_field({"order": {"amount": 100}}, "order.amount") == 100
        assert engine._get_field({"intent": "refund"}, "intent") == "refund"
        assert engine._get_field({}, "missing") is None
        assert engine._get_field({"a": {}}, "a.b") is None

    def test_compare_operators(self):
        """比较操作符"""
        engine = PolicyEngine()
        assert engine._compare(100, "gt", 50) is True
        assert engine._compare(100, "gt", 200) is False
        assert engine._compare(100, "gte", 100) is True
        assert engine._compare(100, "lt", 200) is True
        assert engine._compare(100, "lte", 100) is True
        assert engine._compare("refund", "eq", "refund") is True
        assert engine._compare("refund", "ne", "shipping") is True
        assert engine._compare("a", "in", ["a", "b"]) is True
        assert engine._compare("abc", "contains", "b") is True
        assert engine._compare(None, "gt", 100) is False

    def test_rule_priority_order(self):
        """高优先级规则优先匹配"""
        engine = PolicyEngine()
        # high_amount_refund (priority=100) 应该在 standard_refund (priority=50) 之前
        assert engine.rules[0].priority > engine.rules[1].priority

    def test_exact_threshold_boundary(self):
        """阈值边界值：5000 不拦截，5001 拦截"""
        engine = PolicyEngine()

        context_5000 = {
            "intent": "refund",
            "order": {"amount": 5000},
            "amount": 5000,
        }
        action_5000 = engine.evaluate(context_5000)
        assert action_5000.eligible is True

        context_5001 = {
            "intent": "refund",
            "order": {"amount": 5001},
            "amount": 5001,
        }
        action_5001 = engine.evaluate(context_5001)
        assert action_5001.eligible is False
