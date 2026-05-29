# 智能客服 Agent —— 从原型到生产

> **核心设计理念**：接口契约是 LLM 与确定性系统之间的"协议层"。LLM 只输出信号，代码做路由决策，人工掌握最终控制权。

---

## 一、概述

基于 LangGraph 的智能客服 Agent，核心设计理念：**接口契约是 LLM 与确定性系统之间的协议层**。

三层架构：
- **LLM 语义层**：意图理解、推理决策、回复生成
- **代码校验层**：数据检索、政策校验、契约强制、升级判断
- **人工接管层**：异常处理、Badcase 收集、运营分析

---

## 二、架构

```
START → intent_understand → retrieve → policy_check → reason
       → contract_check → escalate_gate → generate → final_check
       → badcase_collect → END
```

- 3 个 LLM 节点 + 5 个代码节点 + 1 个后置 Hook
- 每个节点在 `thinking_log` 中留下记录

---

## 三、核心能力

### 3.1 接口契约

| 节点 | Schema | 关键字段 |
|------|--------|---------|
| 意图理解 | `IntentSchema` | `intent` / `confidence` / `sentiment` |
| 推理决策 | `ReasonSchema` | `can_auto_resolve` / `plan` |
| 回复生成 | `GenerateSchema` | `response` / `policy_cited` |

所有 LLM 输出通过 Pydantic Schema 强制格式化。

### 3.2 模型路由

| 用途 | 参数 |
|------|------|
| 意图识别 | temp=0.0, max_tokens=512 |
| 推理决策 | temp=0.1, max_tokens=2048 |
| 回复生成 | temp=0.1, max_tokens=2048 |

`thinking_log` 中标注每个节点使用的 tier 和参数。

### 3.3 政策引擎

```yaml
# config/policies.yaml
rules:
  - name: high_amount_refund
    priority: 100
    conditions:
      - field: order.amount
        operator: gt
        value: 5000
    action:
      eligible: false
      reason: "金额超限"
```

- 热更新：30 秒检查文件变更
- 支持金额、品类、用户等级、时间窗口等条件
- 优先级排序

### 3.4 A/B 实验

| 策略 | 语气 |
|------|------|
| A | 标准客服，礼貌简洁 |
| B | 亲切有温度，主动解释原因 |

`AgentState` 中 `variant` 字段控制，`generate_node` 根据 variant 选择 prompt 模板。

---

## 四、Badcase 自动收集

### 4.1 触发条件

| 触发条件 | 阈值 |
|---------|------|
| `blocked` | 任意拦截 |
| `confidence` | < 0.7 |
| `contract_violations` | 非空 |
| `sentiment` | < -0.5 |

### 4.2 收集方式

`badcase_collect` 节点挂载在状态机末端（`final_check` → END），不修改任何 state。

控制项：
- `BADCASE_ENABLED` — 开关（默认 true）
- `BADCASE_SAMPLE_RATE` — 采样率（默认 1.0）
- 存储：本地 JSONL，按天滚动

### 4.3 运营接口

```bash
GET    /badcases              # 查询列表（支持 trigger/status 过滤）
GET    /badcases/stats        # 统计信息
POST   /badcases/{id}/status  # 更新状态（open / reviewed / fixed / ignored）
```

### 4.4 闭环流程

```
自动收集 → 运营 review → 调整配置 → 验证效果 → 循环
```

---

## 五、工程化

### 5.1 测试

```bash
ARK_API_KEY="sk-test-fake-key-for-pytest" pytest tests/ -v
```

48 个测试，覆盖代码节点、LLM 节点、图路径、规则引擎。

### 5.2 监控

暴露端点：`GET /metrics`（Prometheus 格式）

| 指标 | 说明 |
|------|------|
| `agent_requests_total` | 总请求数（按 intent、blocked） |
| `agent_latency_seconds` | 处理延迟直方图 |
| `agent_llm_calls_total` | LLM 调用次数（按 tier） |
| `agent_errors_total` | 错误数 |
| `agent_faq_hit_rate` | FAQ 命中率 |

### 5.3 限流熔断

| 机制 | 配置 |
|------|------|
| IP 限流 | 10 QPS |
| 会话限流 | 30 轮/小时 |
| 熔断器 | 错误率 >20% 或连续 10 次失败，冷却 30 秒 |
| 降级 | Redis 不可用时自动放行 |

### 5.4 容器化

```bash
ARK_API_KEY="your-key" docker compose up --build
```

---

## 六、快速开始

```bash
pip install -r requirements.txt
export ARK_API_KEY="your-api-key"

python main.py                     # Gradio 模式
uvicorn api.main:app --reload      # FastAPI 模式
```

API：

```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test", "message": "我的订单到哪了", "variant": "A"}'
curl http://localhost:8000/metrics
curl http://localhost:8000/badcases
```

---

## 七、项目结构

```
demo-agent/
├── api/
│   ├── main.py
│   ├── routes/
│   │   ├── chat.py
│   │   ├── health.py
│   │   └── badcases.py
│   └── schemas.py
├── config/
│   ├── policies.yaml
│   ├── policy_engine.py
│   └── badcase.yaml
├── graph/
│   ├── builder.py
│   └── router.py
├── middleware/
│   ├── rate_limit.py
│   └── circuit_breaker.py
├── nodes/
│   ├── llm_nodes.py
│   └── code_nodes.py
├── observability/
│   ├── metrics.py
│   ├── logging.py
│   └── badcase.py
├── state/
│   ├── agent_state.py
│   └── redis_saver.py
├── tests/
├── ui/
│   └── gradio_app.py
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## 八、技术栈

LangGraph, LangChain OpenAI, Pydantic, FastAPI, Gradio, Prometheus, Grafana, Redis

---

## 九、完成度

| 方向 | 内容 | 状态 |
|------|------|------|
| 演示增强 | 多轮记忆、人工接管、决策日志、A/B 切换、导出会话 | ✅ |
| 工程深度 | 48 测试、Mock 工厂、模型路由、FAQ 向量检索 | ✅ |
| 生产化 | 政策引擎、FastAPI、Docker、监控、限流、Badcase | ✅ |
