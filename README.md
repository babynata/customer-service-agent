# demo-agent

基于 LangGraph 的智能客服 Agent 演示项目，以**接口契约**作为 LLM 与确定性系统之间的协议层，实现「LLM 输出信号 → 代码硬路由决策 → 人工掌握最终控制权」的三层架构。

## Overview

传统客服系统面临两难：纯规则系统僵化、纯 LLM 系统不可控。本项目演示了一种中间路线——通过 Pydantic Schema 将 LLM 输出强制格式化为结构化信号，再由纯 Python 路由函数做决策，最终让人工保留异常接管权。

核心目标：
- **可控制**：所有关键决策（是否自动处理、是否升级）由代码规则完成，LLM 仅提供语义理解
- **可观测**：每个节点在 `thinking_log` 中留下完整决策记录
- **可迭代**：Badcase 自动收集 + 运营 review + 策略调整的闭环

适合场景：需要 LLM 语义能力、但业务规则必须严格兜底的企业客服、售后、咨询类应用。

## Demo

### Gradio 本地演示

```bash
export ARK_API_KEY="your-api-key"
python main.py
```

浏览器打开 `http://localhost:7860`：

- 左侧：用户对话窗口
- 右侧：Agent 决策过程（每轮 thinking_log + 模型路由信息）
- 底部：人工客服工作台（会话摘要、关键信息、手动回复、A/B 策略切换）

### API 调用示例

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "demo-001",
    "message": "我的订单到哪了",
    "variant": "A"
  }'
```

示例响应：

```json
{
  "response": "您好，订单 DO-20240601-001 当前状态：已发货，预计 6 月 3 日送达。",
  "thinking_log": [
    {"node": "intent_understand", "intent": "query_order", "confidence": 0.92},
    {"node": "retrieve", "order_found": true},
    {"node": "generate", "variant": "A", "model_tier": "main"}
  ]
}
```

## Features

- **接口契约驱动** —— 所有 LLM 输出通过 Pydantic Schema 强制格式化（`IntentSchema`、`ReasonSchema`、`GenerateSchema`），禁止自由文本解析
- **代码硬路由** —— LLM 只输出 `intent` / `confidence` 等信号，路由决策由 `graph/router.py` 中的纯 Python 函数完成
- **模型路由分层** —— `llm_fast`（temp=0.0, max_tokens=512）做意图识别，`llm_main`（temp=0.1, max_tokens=2048）做推理生成，避免「创造力过剩」或「过于保守」
- **YAML 政策引擎** —— 业务规则外置在 `config/policies.yaml`，支持热更新（30 秒检查间隔），无需改代码即可调整退款、升级等策略
- **A/B 实验框架** —— `AgentState` 中 `variant` 字段控制回复策略，支持标准客服（A）与亲切有温度（B）两种风格的无缝切换
- **Badcase 自动收集** —— 命中拦截、置信度低、契约违规、负面情感时自动落盘 JSONL，提供运营查询与状态管理 API
- **限流熔断** —— IP 限流 10 QPS、会话限流 30 轮/小时、错误率>20% 或连续 10 次失败触发熔断，冷却 30 秒
- **Prometheus 监控** —— 暴露 `/metrics` 端点，覆盖请求数、延迟直方图、LLM 调用次数、错误数、FAQ 命中率
- **FAQ 向量检索** —— 基于 Embedding 语义搜索 + 余弦相似度，附带关键词兜底，支持常见咨询类问题自动回答
- **FAQ 短路路径** —— FAQ 高置信度命中时跳过 LLM 推理和生成，直接返回标准答案，延迟降至 ~50ms；退款意图仍先过政策校验再判断短路
- **FAQ 混合打分** —— 三级加分：向量余弦相似度 + 关键词 bonus（标准问题 +0.15 / 同义词 +0.08）+ 分类上下文 bonus（+0.05），支持条目级阈值配置

## Quick Start

### Requirements

- Python >= 3.11
- pip
- 火山方舟 API Key（用于 LLM 调用）

### Installation

```bash
git clone <repository-url>
cd demo-agent
pip install -r requirements.txt
```

### Run

**方式一：Gradio 演示模式**

```bash
export ARK_API_KEY="your-api-key"
python main.py
```

**方式二：FastAPI 服务模式**

```bash
export ARK_API_KEY="your-api-key"
uvicorn api.main:app --reload
```

**方式三：Docker**

```bash
export ARK_API_KEY="your-api-key"
docker compose up --build
```

### Expected Result

Gradio 模式启动后：

```text
Running on local URL:  http://0.0.0.0:7860
```

FastAPI 模式启动后：

```text
INFO:     Uvicorn running on http://127.0.0.1:8000
```

验证服务健康：

```bash
curl http://localhost:8000/health
```

## Usage

### Basic Example

**查询订单：**

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "user-001", "message": "帮我查一下订单状态", "variant": "A"}'
```

**查看指标：**

```bash
curl http://localhost:8000/metrics
```

**查看 Badcase 列表：**

```bash
curl "http://localhost:8000/badcases?trigger=blocked"
```

### Configuration

| Name | Required | Default | Description |
|---|---:|---|---|
| `ARK_API_KEY` | Yes | - | 火山方舟 API Key |
| `ARK_ENDPOINT_ID` | No | `deepseek-v3-2-251201` | 模型端点 ID |
| `BADCASE_ENABLED` | No | `true` | Badcase 自动收集开关 |
| `BADCASE_SAMPLE_RATE` | No | `1.0` | Badcase 采样率（0.0~1.0） |

配置集中在 `app_config.py`，环境变量优先，无外部配置中心依赖。

## How It Works

### 三层架构

```
┌─────────────────────────────────────────────────────────┐
│  LLM 语义层   │  intent_understand / reason / generate  │
├─────────────────────────────────────────────────────────┤
│  代码校验层   │  retrieve → policy_check → contract_check │
│             │  → escalate_gate → final_check            │
├─────────────────────────────────────────────────────────┤
│  人工接管层   │  Badcase 收集 → 运营 Review → 策略调整    │
└─────────────────────────────────────────────────────────┘
```

### 数据流

```text
用户输入
  → 意图识别 (intent_node, llm_fast, IntentSchema)
  → 路由决策 (router.py, 代码硬路由)
    ├─→ 自动处理路径：retrieve → policy_check → reason → generate → final_check
    ├─→ FAQ 短路路径：retrieve → faq_direct → final_check（高置信度 FAQ 命中）
    ├─→ 退款+FAQ 短路：retrieve → policy_check → faq_direct → final_check（政策通过 + FAQ 命中）
    └─→ 升级路径：escalate_gate → escalate
  → 输出回复 + thinking_log
  → Badcase 收集 (后置 Hook，不修改 state)
```

### 图节点说明

| 节点 | 类型 | 职责 |
|------|------|------|
| `intent_understand` | LLM | 识别用户意图、置信度、情感 |
| `retrieve` | 代码 | 并行查询订单 + FAQ 向量检索 |
| `faq_direct` | 代码 | FAQ 高置信度命中时直接返回标准答案，跳过 LLM |
| `policy_check` | 代码 | YAML 策略规则校验 |
| `reason` | LLM | 推理分析、制定处理计划 |
| `contract_check` | 代码 | 汇总契约违规项 |
| `escalate_gate` | 代码 | 升级判断（置信度、情感、政策） |
| `generate` | LLM | 生成回复，支持 A/B variant |
| `final_check` | 代码 | 敏感词过滤、金额一致性校验 |
| `badcase_collect` | 代码 | 后置 Hook，自动收集异常 case |

### 置信度阈值

- `confidence >= 0.7`：自动处理
- `confidence < 0.7`：进入升级网关
- FAQ 短路阈值：`faq_result.answer.confidence >= 0.8`

## Project Structure

```
demo-agent/
├── api/                    # FastAPI 服务
│   ├── main.py
│   └── routes/
│       ├── chat.py
│       ├── health.py
│       └── badcases.py
├── config/                 # 策略配置
│   ├── policies.yaml
│   └── policy_engine.py
├── graph/                  # LangGraph 状态机
│   ├── builder.py
│   └── router.py
├── middleware/             # 限流熔断
│   ├── rate_limit.py
│   └── circuit_breaker.py
├── nodes/                  # 图节点
│   ├── llm_nodes.py
│   └── code_nodes.py
├── observability/          # 监控与日志
│   ├── metrics.py
│   ├── logging.py
│   └── badcase.py
├── schemas/                # Pydantic 接口契约
│   ├── llm_output.py
│   ├── tool_input.py
│   └── faq_schema.py       # FAQDocument 结构化契约
├── state/                  # 状态定义与持久化
│   ├── agent_state.py
│   └── redis_saver.py
├── tools/                  # 查询工具与 Mock 数据
│   ├── query.py
│   ├── mock_data.py
│   ├── mock_factory.py
│   └── embedding.py
├── ui/                     # Gradio 演示界面
│   └── gradio_app.py
├── tests/                  # 测试套件
├── app_config.py           # 全局配置 + 模型路由
├── main.py                 # Gradio 入口
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## Testing

```bash
ARK_API_KEY="sk-test-fake-key-for-pytest" pytest tests/ -v
```

共 62 个测试，覆盖范围：

| 文件 | 数量 | 说明 |
|------|------|------|
| `test_code_nodes.py` | 24 | 检索、政策检查、契约校验、升级、最终校验、FAQ 短路、同义词匹配 |
| `test_llm_nodes.py` | 14 | Mock LLM 调用验证 Schema 处理逻辑 |
| `test_graph.py` | 9 | 完整图路径（happy path / blocked path / 多轮记忆 / FAQ 短路） |
| `test_faq_schema.py` | 6 | FAQDocument Schema 校验 |
| `test_policy_engine.py` | 8 | YAML 策略规则解析与执行 |

真实 API Key **永不进入**测试流程。

## Roadmap

- [x] FAQ RAG 闭环（检索 → 生成 → 短路路径）
- [x] FAQ 数据模型升级（同义词、分类、条目级阈值）
- [ ] 接入内部订单 API，替换 `tools/mock_data.py`
- [ ] 接入物流 API，替换 `tools/query.py`
- [ ] 接入 Milvus 向量数据库，支持万级 FAQ
- [ ] FAQ 同义词自动挖掘（LLM 生成 + 人工审核）
- [ ] 接入规则引擎（Drools 或内部系统），替换 `nodes/code_nodes.py:policy_check`
- [ ] Redis 持久化 + 分布式锁，替换内存状态
- [ ] 配置中心（Nacos / Apollo / Consul），替换 `app_config.py` 硬编码
- [ ] 多模型切换（`get_model_for_task()` 扩展）
- [ ] 人工接管实时干预（非事后 Badcase）

## Limitations

- **Mock 数据**：当前使用内存 Mock 数据演示链路，生产环境需替换为真实 API
- **LLM 提供商**：当前仅对接火山方舟（Volcengine Ark），切换其他提供商需修改 `app_config.py`
- **FAQ 检索**：当前为内存向量检索（numpy + 混合打分），同义词和分类数据为手动填充，生产环境建议迁移至 Milvus + 自动同义词挖掘
- **语言场景**：当前主要优化中文客服场景，多语言支持需额外 prompt 工程

## Troubleshooting

### 环境变量缺失导致 LLM 调用失败

**现象**：启动后对话无响应，日志提示 API Key 相关错误。  
**解决**：

```bash
export ARK_API_KEY="your-api-key"
```

确认已 export 后再运行 `python main.py`。

### Schema 与代码不同步

**现象**：运行时报 `ValidationError` 或字段访问错误。  
**解决**：修改 `schemas/llm_output.py` 后，必须同步检查：

1. `nodes/llm_nodes.py` 中的 `with_structured_output()` 引用
2. `nodes/code_nodes.py` 中的字段访问
3. `tests/` 中的 mock 数据

### 模型路由参数混淆

**现象**：意图识别结果不稳定，或生成回复过于简短/冗长。  
**解决**：

- 意图识别必须用 `llm_fast`（temperature=0.0, max_tokens=512）
- 推理生成必须用 `llm_main`（temperature=0.1, max_tokens=2048）

切勿互换。

### FAQ 向量检索无结果

**现象**：咨询类问题返回「未找到相关信息」。  
**解决**：检查 `faq-vector-db/` 目录是否存在且包含向量数据；如使用 Docker，确认数据卷挂载正确。

## Contributing

欢迎贡献。

基本流程：

1. Fork this repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Commit your changes (`git commit -am 'feat: add some feature'`)
4. Open a pull request

提交信息请遵循 [Conventional Commits](https://www.conventionalcommits.org/)。

## License

This project is licensed under the MIT License.
