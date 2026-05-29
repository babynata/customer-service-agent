"""
Badcase 收集模块

自动收集和归档系统异常、低质量回复、用户不满意的情况。
"""

import json
import uuid
import random
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict


# Badcase 存储目录
BADCASE_DIR = Path(__file__).parent.parent / "data" / "badcases"
BADCASE_DIR.mkdir(parents=True, exist_ok=True)

# 采样率：环境变量控制，默认 1.0（全量）
BADCASE_SAMPLE_RATE = float(os.environ.get("BADCASE_SAMPLE_RATE", "1.0"))


@dataclass
class Badcase:
    """Badcase 记录"""
    id: str
    timestamp: str
    session_id: str
    user_query: str
    response: str
    intent: Optional[str]
    confidence: float
    sentiment: float
    blocked: bool
    block_reason: Optional[str]
    contract_violations: list[str]
    thinking_log: list[str]
    trigger: str              # 触发原因：blocked/low_confidence/contract_violation/negative_sentiment
    status: str = "open"      # open / reviewed / fixed / ignored
    notes: str = ""           # 运营备注


class BadcaseCollector:
    """Badcase 收集器"""

    def __init__(self, storage_dir: Path = BADCASE_DIR):
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def collect(self, state: dict) -> Optional[Badcase]:
        """
        从 AgentState 中判断是否需要收集 badcase

        触发条件（满足任一）：
        1. blocked = True（被拦截）
        2. confidence < 0.7（低置信度）
        3. contract_violations 非空（契约违约）
        4. sentiment < -0.5（负面情绪）
        """
        # 采样率过滤
        if random.random() > BADCASE_SAMPLE_RATE:
            return None

        triggers = []

        if state.get("blocked"):
            triggers.append("blocked")

        if state.get("confidence", 1.0) < 0.7:
            triggers.append("low_confidence")

        if state.get("contract_violations"):
            triggers.append("contract_violation")

        if state.get("sentiment", 0.0) < -0.5:
            triggers.append("negative_sentiment")

        if not triggers:
            return None

        badcase = Badcase(
            id=str(uuid.uuid4())[:12],
            timestamp=datetime.now(timezone.utc).isoformat(),
            session_id=state.get("session_id", "unknown"),
            user_query=state.get("user_query", ""),
            response=state.get("response", ""),
            intent=state.get("intent"),
            confidence=state.get("confidence", 0.0),
            sentiment=state.get("sentiment", 0.0),
            blocked=state.get("blocked", False),
            block_reason=state.get("block_reason"),
            contract_violations=state.get("contract_violations", []),
            thinking_log=state.get("thinking_log", []),
            trigger=",".join(triggers),
        )

        self._save(badcase)
        return badcase

    def _save(self, badcase: Badcase) -> None:
        """保存到本地 JSONL 文件"""
        date_str = badcase.timestamp[:10]  # YYYY-MM-DD
        file_path = self.storage_dir / f"badcases_{date_str}.jsonl"

        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(badcase), ensure_ascii=False) + "\n")

    def list_badcases(
        self,
        date: Optional[str] = None,
        trigger: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[Badcase]:
        """查询 badcase 列表"""
        results = []

        if date:
            files = [self.storage_dir / f"badcases_{date}.jsonl"]
        else:
            files = sorted(self.storage_dir.glob("badcases_*.jsonl"), reverse=True)

        for file_path in files:
            if not file_path.exists():
                continue
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    if trigger and trigger not in data.get("trigger", ""):
                        continue
                    if status and data.get("status") != status:
                        continue
                    results.append(Badcase(**data))
                    if len(results) >= limit:
                        break
            if len(results) >= limit:
                break

        return results

    def update_status(self, badcase_id: str, status: str, notes: str = "") -> bool:
        """更新 badcase 状态（运营标记）"""
        # 找到对应的文件和记录
        for file_path in self.storage_dir.glob("badcases_*.jsonl"):
            lines = []
            found = False
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    data = json.loads(line.strip())
                    if data.get("id") == badcase_id:
                        data["status"] = status
                        data["notes"] = notes
                        found = True
                    lines.append(json.dumps(data, ensure_ascii=False))

            if found:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
                return True

        return False

    def get_stats(self) -> dict:
        """获取 badcase 统计"""
        total = 0
        by_trigger = {}
        by_status = {}

        for file_path in self.storage_dir.glob("badcases_*.jsonl"):
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    data = json.loads(line.strip())
                    total += 1
                    for t in data.get("trigger", "").split(","):
                        by_trigger[t] = by_trigger.get(t, 0) + 1
                    status = data.get("status", "open")
                    by_status[status] = by_status.get(status, 0) + 1

        return {
            "total": total,
            "by_trigger": by_trigger,
            "by_status": by_status,
        }


# 全局单例
collector = BadcaseCollector()
