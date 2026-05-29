"""
政策规则引擎

支持 YAML 配置驱动、热更新、多维度条件匹配。
"""

import os
import time
import yaml
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field


DEFAULT_POLICY_PATH = Path(__file__).parent / "policies.yaml"


@dataclass
class Condition:
    """规则条件"""
    field: str          # 如 "intent", "order.amount"
    operator: str       # eq, ne, gt, gte, lt, lte, in, contains
    value: Any          # 比较值


@dataclass
class Action:
    """规则动作"""
    eligible: bool
    reason: str
    escalate: bool = False


@dataclass
class PolicyRule:
    """政策规则"""
    name: str
    description: str = ""
    priority: int = 0
    conditions: list[Condition] = field(default_factory=list)
    action: Optional[Action] = None


class PolicyEngine:
    """
    政策规则引擎

    支持热更新：每 30 秒检查配置文件是否变更，自动重载。
    """

    def __init__(self, policy_path: Optional[Path] = None):
        self.policy_path = policy_path or DEFAULT_POLICY_PATH
        self.rules: list[PolicyRule] = []
        self._last_load_time: float = 0
        self._last_mtime: float = 0
        self._reload_interval = 30  # 秒
        self._load()

    def _load(self) -> None:
        """从 YAML 加载规则"""
        if not self.policy_path.exists():
            self.rules = self._default_rules()
            return

        try:
            with open(self.policy_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception:
            self.rules = self._default_rules()
            return

        if not data or "rules" not in data:
            self.rules = self._default_rules()
            return

        self.rules = []
        for r in data["rules"]:
            conditions = [
                Condition(
                    field=c["field"],
                    operator=c["operator"],
                    value=c["value"],
                )
                for c in r.get("conditions", [])
            ]
            action_data = r.get("action", {})
            action = Action(
                eligible=action_data.get("eligible", True),
                reason=action_data.get("reason", ""),
                escalate=action_data.get("escalate", False),
            )
            self.rules.append(PolicyRule(
                name=r["name"],
                description=r.get("description", ""),
                priority=r.get("priority", 0),
                conditions=conditions,
                action=action,
            ))

        # 按优先级降序排列
        self.rules.sort(key=lambda x: x.priority, reverse=True)
        self._last_load_time = time.time()
        self._last_mtime = self.policy_path.stat().st_mtime

    def _maybe_reload(self) -> None:
        """热更新检查"""
        now = time.time()
        if now - self._last_load_time < self._reload_interval:
            return
        self._last_load_time = now

        try:
            mtime = self.policy_path.stat().st_mtime
            if mtime != self._last_mtime:
                self._load()
        except Exception:
            pass

    def _default_rules(self) -> list[PolicyRule]:
        """默认规则（硬编码兜底）"""
        return [
            PolicyRule(
                name="high_amount_refund",
                description="大额退款需人工审核",
                priority=100,
                conditions=[
                    Condition(field="intent", operator="eq", value="refund"),
                    Condition(field="order.amount", operator="gt", value=5000),
                ],
                action=Action(eligible=False, reason="金额超限", escalate=True),
            ),
            PolicyRule(
                name="standard_refund",
                description="标准退款自动处理",
                priority=50,
                conditions=[
                    Condition(field="intent", operator="eq", value="refund"),
                ],
                action=Action(eligible=True, reason="符合退款条件", escalate=False),
            ),
        ]

    def evaluate(self, context: dict) -> Optional[Action]:
        """
        评估规则，返回匹配的最高优先级规则的动作

        Args:
            context: 评估上下文，如 {"intent": "refund", "order": {"amount": 8999}}

        Returns:
            匹配规则的 Action，或 None（无匹配）
        """
        self._maybe_reload()

        for rule in self.rules:
            if self._match_rule(rule, context):
                return rule.action
        return None

    def _match_rule(self, rule: PolicyRule, context: dict) -> bool:
        """判断规则是否全部条件匹配"""
        for cond in rule.conditions:
            actual = self._get_field(context, cond.field)
            if not self._compare(actual, cond.operator, cond.value):
                return False
        return True

    @staticmethod
    def _get_field(context: dict, field_path: str) -> Any:
        """从上下文中获取字段值，支持点号路径"""
        parts = field_path.split(".")
        value = context
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return None
            if value is None:
                return None
        return value

    @staticmethod
    def _compare(actual: Any, operator: str, expected: Any) -> bool:
        """条件比较"""
        if operator == "eq":
            return actual == expected
        if operator == "ne":
            return actual != expected
        if operator == "gt":
            return actual is not None and expected is not None and actual > expected
        if operator == "gte":
            return actual is not None and expected is not None and actual >= expected
        if operator == "lt":
            return actual is not None and expected is not None and actual < expected
        if operator == "lte":
            return actual is not None and expected is not None and actual <= expected
        if operator == "in":
            return actual in expected if expected is not None else False
        if operator == "contains":
            return expected in actual if actual is not None else False
        return False


# 全局单例
policy_engine = PolicyEngine()
