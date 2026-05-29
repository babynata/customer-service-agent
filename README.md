# 智能客服 Agent —— 从原型到生产

> **核心设计理念**：接口契约是 LLM 与确定性系统之间的"协议层"。LLM 只输出信号，代码做路由决策，人工掌握最终控制权。

---

## 一、产品定位

### 1.1 为什么做这个项目

传统客服系统面临两个极端：
- **纯规则系统**：死板，无法处理复杂语义
- **纯 LLM 系统**：幻觉、不可控、无法追责

本系统尝试第三条路：**LLM 语义层 + 代码校验层 + 人工接管层** 的三层架构，让 AI 处理它能处理的，把不确定的交给人工，且整个过程可追溯、可审计。

### 1.2 目标用户

| 角色 | 需求 |
|------|------|
| **终端用户** | 快速解决问题，不被机器人绕圈子 |
| **运营人员** | 看到系统为什么做了这个决策，发现 badcase |
| **开发者** | 通过配置而非代码调整业务规则 |
| **管理层** | 有数据看板，知道系统在干什么 |

---

## 二、架构设计

### 2.1 三层架构

```
┌─────────────────────────────────────────────────────────┐
│  第一层：LLM 语义层（信号输出）                           │
│  intent_understand → reason_node → generate_node        │
│  职责：理解、推理、生成，但不决定路由                      │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│  第二层：代码校验层（硬路由）                             │
│  retrieve → policy_check → contract_check → escalate_gate │
│  职责：数据查询、规则校验、契约强制、升级判断              │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│  第三层：人工接管层（最终控制）                           │
│  人工客服工作台 + Badcase 收集 + 运营分析                 │
│  职责：处理异常、复盘问题、优化规则                        │
└─────────────────────────────────────────────────────────┘
```

### 2.2 状态机流转

```
START → intent_understand → retrieve → policy_check → reason
       → contract_check → escalate_gate → generate → final_check
       → badcase_collect → END
```

- **8 个节点**：3 个 LLM 节点 + 5 个代码节点 + 1 个后置 Hook
- **全链路可追溯**：每个节点在 `thinking_log` 中留下记录
- **双向控制**：LLM 输出信号，代码决定是否放行，人工可随时介入

---

## 三、核心能力

### 3.1 接口契约驱动

所有 LLM 输出必须通过 Pydantic Schema 强制格式化，不是建议，是强制。

| 节点 | Schema | 关键字段 | 契约规则 |
|------|--------|---------|---------|
| 意图理解 | `IntentSchema` | `intent` / `confidence` / `sentiment` | intent 必须在白名单；confidence 必须诚实 |
| 推理决策 | `ReasonSchema` | `can_auto_resolve` / `plan` | can_auto_resolve=true 必须有 plan |
| 回复生成 | `GenerateSchema` | `response` / `policy_cited` | 退款场景必须引用政策依据 |

### 3.2 模型路由分层

同一模型（deepseek-v3），不同参数，体现"分层架构"设计理念：

| 用途 | 参数 | 原因 |
|------|------|------|
| **意图识别** | temp=0.0, max_tokens=512 | 简单分类，不需要创造力，要低确定性 |
| **推理决策** | temp=0.1, max_tokens=2048 | 复杂决策，需要一定灵活性 |
| **回复生成** | temp=0.1, max_tokens=2048 | 复杂生成，保持语气一致性 |

`thinking_log` 中标注每个节点使用的 tier 和参数，为后续多模型切换留接口。

### 3.3 政策引擎可配置化

业务规则不再硬编码在代码中，而是通过 YAML 配置：

```yaml
# config/policies.yaml
rules:
  - name: high_amount_refund
    priority: 100
    conditions:
      - field: intent
        operator: eq
        value: refund
      - field: order.amount
        operator: gt
        value: 5000
    action:
      eligible: false
      reason: "金额超限"
```

- **热更新**：30 秒检查一次文件变更，无需重启
- **多维度**：支持金额、品类、用户等级、时间窗口等条件
- **优先级**：高优先级规则优先匹配

### 3.4 A/B 实验框架

同一问题，不同策略，观众可主动切换对比：

| 策略 | 语气 | 适用场景 |
|------|------|---------|
| **A** | 标准客服，礼貌简洁 | 效率优先 |
| **B** | 亲切有温度，主动解释原因 | 体验优先 |

实现方式：
- `AgentState` 中 `variant` 字段控制
- `generate_node` 根据 variant 选择不同 prompt 模板
- UI 右侧 Dropdown 切换，thinking_log 标注策略版本

---

## 四、Badcase 运营闭环（AI PM 核心能力）

### 4.1 为什么需要 Badcase 收集

LLM 系统上线后最大的风险是**不知道自己在犯错**。用户不满意时不会告诉你，只会默默流失。Badcase 收集是 AI 产品的"体检报告"。

### 4.2 触发条件（自动识别）

系统无需用户反馈，自动识别以下情况：

| 触发条件 | 说明 | 示例 |
|---------|------|------|
| `blocked` | 被代码拦截 | 金额超限、情感负面 |
| `confidence < 0.7` | LLM 自己不确信 | "我大概理解你是想问..." |
| `contract_violations` | 契约违约 | intent 不在白名单、order_id 格式错误 |
| `sentiment < -0.5` | 用户情绪负面 | "你们这群骗子！" |

### 4.3 收集方式（零侵入）

```
用户请求 → ... → final_check → [badcase_collect] → END
```

- **后置 Hook**：`badcase_collect` 节点挂在图的最后，不修改任何 state
- **配置开关**：`BADCASE_ENABLED` 环境变量控制
- **采样率**：`BADCASE_SAMPLE_RATE` 控制收集比例（1.0=全量，0.1=10%）
- **存储**：本地 JSONL 文件，按天滚动，便于日志采集工具读取

### 4.4 运营接口

```bash
# 查询最近 badcase
GET /badcases?limit=50

# 按触发类型过滤
GET /badcases?trigger=blocked

# 查看统计
GET /badcases/stats

# 运营标记（标记为已处理）
POST /badcases/{id}/status?status=reviewed&notes=已补充FAQ
```

### 4.5 运营闭环流程

```
系统自动收集 badcase
  ↓
运营每日 review → 分类：补充 FAQ / 调整阈值 / 优化 prompt / 忽略
  ↓
调整配置（policies.yaml / prompt 模板）
  ↓
验证效果 → 观察 badcase 数量是否下降
  ↓
循环迭代
```

### 4.6 数据驱动决策

通过 `/badcases/stats` 可以看到：
- 哪类触发最多？（blocked vs low_confidence）
- 哪个时段问题最多？
- 处理后是否减少？

这些数据指导产品迭代方向，而不是凭感觉改代码。

---

## 五、工程化能力

### 5.1 测试覆盖

```bash
ARK_API_KEY="sk-test-fake-key-for-pytest" pytest tests/ -v
```

- 48 个测试，覆盖代码节点、LLM 节点、图路径、规则引擎
- Mock LLM 调用，不依赖真实 API
- 集成测试验证完整链路

### 5.2 监控告警

| 指标 | 说明 |
|------|------|
| `agent_requests_total` | 总请求数（按 intent、blocked 标签） |
| `agent_latency_seconds` | 处理延迟直方图 |
| `agent_llm_calls_total` | LLM 调用次数（按 tier 标签） |
| `agent_errors_total` | 错误数 |
| `agent_faq_hit_rate` | FAQ 命中率 |

暴露端点：`GET /metrics`（Prometheus 格式）

### 5.3 限流熔断

| 机制 | 配置 |
|------|------|
| IP 限流 | 10 QPS（滑动窗口） |
| 会话限流 | 30 轮/小时 |
| 熔断器 | 错误率 >20% 或连续 10 次失败触发，冷却 30 秒 |
| 降级 | Redis 不可用时自动放行，避免误杀 |

### 5.4 容器化

```bash
# 一键启动完整环境
ARK_API_KEY="your-key" docker compose up --build

# 包含：app + redis + prometheus + grafana
```

---

## 六、快速开始

### 本地开发

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
export ARK_API_KEY="your-api-key"

# 3. 启动
python main.py          # Gradio 模式（演示）
# 或
uvicorn api.main:app --reload   # FastAPI 模式（生产）
```

### API 调用

```bash
# 健康检查
curl http://localhost:8000/health

# 对话
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test", "message": "我的订单到哪了", "variant": "A"}'

# 查看指标
curl http://localhost:8000/metrics

# 查询 badcase
curl http://localhost:8000/badcases
```

---

## 七、项目结构

```
demo-agent/
├── api/                    # FastAPI 服务
│   ├── main.py             # 入口（挂载 Gradio 子应用）
│   ├── routes/
│   │   ├── chat.py         # 对话接口
│   │   ├── health.py       # 健康检查
│   │   └── badcases.py     # Badcase 运营接口
│   └── schemas.py          # API 请求/响应 Schema
├── config/
│   ├── policies.yaml       # 业务规则配置
│   ├── policy_engine.py    # 规则引擎
│   └── badcase.yaml        # Badcase 收集配置
├── graph/
│   ├── builder.py          # 状态机构建（含 badcase_collect Hook）
│   └── router.py           # 路由函数
├── middleware/
│   ├── rate_limit.py       # 限流
│   └── circuit_breaker.py  # 熔断
├── nodes/
│   ├── llm_nodes.py        # LLM 语义层
│   └── code_nodes.py       # 代码校验层
├── observability/
│   ├── metrics.py          # Prometheus 指标
│   ├── logging.py          # 结构化日志
│   └── badcase.py          # Badcase 收集器
├── state/
│   ├── agent_state.py      # State 定义
│   └── redis_saver.py      # Redis 持久化
├── tests/                  # 测试套件（48 个测试）
├── ui/
│   └── gradio_app.py       # 演示界面
├── Dockerfile              # 多阶段构建
├── docker-compose.yml      # 全栈编排
└── README.md               # 本文件
```

---

## 八、技术栈

- **LangGraph**：状态机 + 图执行引擎
- **LangChain OpenAI**：火山方舟 API 兼容调用
- **Pydantic**：接口契约强制校验
- **FastAPI**：API 服务化
- **Gradio**：演示界面
- **Prometheus + Grafana**：监控告警
- **Redis**：对话持久化 + 限流计数

---

## 九、三个方向完成度

| 方向 | 内容 | 状态 |
|------|------|------|
| **方向二：演示增强** | 多轮记忆、人工接管、按轮次展示决策日志、A/B 策略切换、导出会话 | ✅ 完成 |
| **方向三：工程深度** | 48 个测试、Mock 工厂、模型路由分层、FAQ 向量检索 | ✅ 完成 |
| **方向一：生产化** | 政策引擎可配置化、FastAPI 服务化、Docker 容器化、监控告警、限流熔断、Badcase 运营闭环 | ✅ 完成 |

---

*Designed for AI PM who cares about observability, configurability, and closed-loop optimization.*
