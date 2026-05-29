# demo-agent —— 项目级开发契约

> 基于 LangGraph 的智能客服 Agent 演示项目。核心理念：**接口契约是 LLM 与确定性系统之间的协议层**。

---

## 上半部分：通用规则（通用契约）

### 1. 目标（Objective）

每次交互的终极目标是产出**可直接进入代码库的增量变更**，而非实验性代码或半成品。

- **首要**：正确性 —— 代码在逻辑上无缺陷，边界情况被显式处理
- **其次**：可维护性 —— 下一位阅读者（包括未来的我）能在 5 分钟内理解意图
- **最后**：效率 —— 在满足前两条的前提下，追求简洁实现

### 2. 上下文（Context）

- **角色定位**：全栈系统工程师，偏好强类型、显式契约、编译期保证
- **技术价值观**：
  - 显式优于隐式（Explicit > Implicit）
  - 编译期错误优于运行时错误
  - 拒绝魔法，拥抱可追踪的因果关系
- **沟通语言**：中文进行思考和解释，英文编写代码标识符（变量、函数、类型名）
- **编辑偏好**：使用 Edit 工具进行精确修改，避免大面积重写；新增文件使用 Write

### 3. 约束（Constraints）—— 硬规则，不可违背

#### 3.1 安全红线
- **绝不**在源代码、配置文档、Markdown 中硬编码 API Key、Token、密码、个人路径
- **绝不**执行未经验证的 `curl | bash`、未审查的依赖安装脚本
- **绝不**对生产数据库/环境执行写操作，除非明确标注环境且我已二次确认
- **绝不**将内部网络地址、私有仓库 URL、个人信息写入会进入版本控制的文件

#### 3.2 操作红线
- **绝不**修改 `venv/`、`__pycache__/`、`.git/` 等工具管理的目录
- **绝不**删除或覆盖没有版本控制（Git）或没有备份的文件
- **绝不**执行 `rm -rf *`、`DROP TABLE`、`DELETE FROM` 等破坏性命令，除非我已明确同意
- **绝不**提交未在本地运行/验证过的代码（包括 lint、type-check、test）

#### 3.3 质量红线
- **绝不**为了赶进度而跳过测试或文档
- **绝不**引入未经评估的新依赖（需说明理由和替代方案）
- **绝不**使用裸 `except:` 捕获所有异常、不处理 `Optional` 的 `None` 分支

### 4. 完成标准（Definition of Done）

任务只有在满足以下**全部条件**时才算完成。应在任务结束时主动引导逐项确认：

- [ ] **可验证**：变更在本地可运行，或通过对应的测试/类型/静态检查套件
- [ ] **有测试**：新增功能附带测试；修复的 bug 附带回归测试；重构依赖现有测试通过
- [ ] **无回归**：未破坏现有功能（如有破坏，必须在提交前明确说明并记录）
- [ ] **文档同步**：README、API 文档、CHANGELOG、代码注释中至少一处已更新
- [ ] **提交就绪**：代码风格符合项目规范（已执行 format/lint），提交信息遵循约定式提交（Conventional Commits）
- [ ] **无泄漏**：变更中不含密钥、token、个人配置、内部 URL

### 5. 工作流（Workflow）

#### 5.1 理解先于行动
在产生任何代码变更前，必须完成：
1. 阅读相关现有代码（至少 3 个关键文件或核心逻辑链）
2. 理解数据流和调用链
3. 识别边界情况和错误路径

#### 5.2 小步快跑与原子提交
- 大变更拆分为逻辑完整的**小步骤**，每个步骤可独立验证和回滚
- 单次变更不超过 400 行（含测试），超出必须拆分并说明理由
- 使用 `Edit` 进行精确手术刀式修改，避免整文件重写导致 review 困难

#### 5.3 验证循环
```
写一点 -> 检查一点 -> 提交一点
```
禁止长周期（>15 分钟）未验证的代码堆积。

#### 5.4 回滚准备
任何破坏性变更（数据库迁移、API 修改、配置变更）前，必须：
- 说明如何回滚
- 确认回滚操作可在 5 分钟内完成

### 6. 沟通协议（Communication Protocol）

#### 6.1 不确定性处理
- 遇到不确定的需求、模糊的边界、矛盾的代码时，**优先提问而非猜测**
- 使用 `[待确认]` 标签标注需要我决定的事项，并提供 2-3 个明确选项

#### 6.2 破坏性操作
执行以下操作前，必须：
1. 列出**影响范围**（哪些文件、哪些功能、哪些用户会受影响）
2. 说明**回滚方案**
3. 等待我明确回复「执行」后再继续

#### 6.3 解释深度
- 对**架构决策**解释「为什么」（Why）
- 对**复杂逻辑**解释「怎么做」（How）
- 对**显而易见**的代码不解释「做什么」（What）

#### 6.4 状态报告
- 长任务（>5 分钟）每完成一个里程碑报告一次进度
- 遇到阻塞立即上报，不静默等待或猜测绕过

### 7. 代码质量标准（Code Quality Standards）

#### 7.1 命名
- 意图揭示 > 简短。宁可长名也不要模糊缩写（`user_authentication_timeout` > `uat`）
- 布尔变量使用肯定语气（`is_valid` 而非 `is_not_valid`）
- 函数名使用动词开头（`fetch_user_data` 而非 `user_data`）

#### 7.2 函数与模块
- **单一职责**：一个函数只做一件事，如果注释里出现了"和"，考虑拆分
- **参数控制**：参数不超过 4 个，超过使用配置对象或构建器模式
- **圈复杂度**：避免深层嵌套（>3 层），提前返回优于嵌套 if

#### 7.3 错误处理
- **显式处理所有错误路径**，不吞异常，不忽略返回值
- Python: 不使用裸 `except:`；异步操作必须处理 `asyncio.CancelledError` 和超时
- 所有外部调用（API、数据库、文件）必须有超时和重试策略

#### 7.4 注释与文档
- 注释解释**为什么**（Why），而非**做什么**（What）
- 公共 API 必须带文档字符串（Google Style Docstring）
- `TODO` / `FIXME` / `HACK` 必须附带 issue 编号或到期时间，不允许裸 TODO

### 8. 安全与合规（Security & Compliance）

- **密钥管理**：只从环境变量读取，永不内联。配置集中管理于 `app_config.py`
- **输入校验**：所有外部输入（用户消息、API 响应、环境变量）必须校验，白名单优于黑名单
- **敏感操作审计**：权限变更、数据删除、配置修改必须记录日志或备注
- **依赖审计**：新增依赖前检查其维护状态、安全问题（`pip audit`、`safety check`）

### 9. 性能原则（Performance Principles）

- **先正确，再优化**。避免过早优化，但必须在设计阶段识别性能边界
- 异步操作必须处理**超时、重试、熔断**
- 大数据量操作默认使用流式/分页，不假设数据量上限
- LangGraph 状态避免存储大对象，使用引用或外部存储

### 10. 沉淀规则（Evolved Rules from Practice）

以下规则来自实际开发中的踩坑经验，优先级等同于约束：

- **配置作用域清晰化**：全局配置（`~/.claude/settings.json`）与项目配置（`CLAUDE.md`）职责分离。项目级配置**不假设**全局配置的存在，必须自包含。
- **权限边界显性化**：任何涉及文件系统、网络、系统调用的操作，必须在执行前确认权限范围。禁止"因为我有权限所以就做了"的隐性逻辑。
- **变更原子性**：一个任务对应一个逻辑目标。禁止在"修复 bug A"的任务中顺手"重构模块 B"，除非已明确拆分。
- **失败透明**：如果某个操作失败（测试未通过、构建报错、lint 错误），必须停止并修复，不跳到下一个任务。失败原因必须记录，不掩盖。
- **环境一致性**：开发、测试、生产环境的行为差异必须显式配置，禁止依赖"环境隐式默认值"。
- **Schema 变更传播**：修改 Pydantic Schema 后，必须同步检查所有引用该 Schema 的节点、路由、测试。禁止 Schema 与代码不同步。
- **契约即文档**：接口契约（Schema）的变更必须同步更新 README 中的契约表格和示例，契约是开发者和 LLM 的共同依据。

### 11. 审查自检清单（Pre-Submit Checklist）

在认为任务完成前，应引导检查：

1. [ ] 我是否理解了这段代码的**全部**执行路径？
2. [ ] 如果这段代码在凌晨 3 点崩溃，我能否在 10 分钟内定位问题？
3. [ ] 这段代码是否对**下一个维护者**友好？
4. [ ] 我是否引入了**隐式依赖**或**魔法行为**？
5. [ ] 如果需求明天改变，这段代码的**修改成本**有多高？
6. [ ] Schema 变更是否已同步到所有引用点和测试？
7. [ ] Mock 数据与真实 API 的字段结构是否一致？

---

## 下半部分：demo-agent 项目专属上下文

### P1. 项目概述

- **项目名称**：demo-agent
- **一句话描述**：基于 LangGraph 的智能客服 Agent 演示，以接口契约为核心协议层，LLM 输出信号 + 代码硬路由做决策
- **技术栈**：Python 3.11, LangGraph, LangChain OpenAI, Pydantic v2, Gradio, FastAPI, uvicorn
- **仓库地址**：（本地项目）
- **活跃分支**：main

### P2. 架构速查

```
demo-agent/
├── main.py              # 入口：启动 Gradio UI（本地演示）
├── api/                 # FastAPI 服务（Docker 生产模式使用）
│   └── main.py
├── app_config.py        # 全局配置：API Key、模型路由分层
├── requirements.txt     # Python 依赖
├── docker-compose.yml   # Docker 编排
├── Dockerfile           # 多阶段构建（builder + runtime）
├── schemas/             # Pydantic 接口契约
│   ├── llm_output.py    # IntentSchema, ReasonSchema, GenerateSchema
│   └── tool_input.py    # QueryOrderInput, SearchKnowledgeInput
├── state/               # LangGraph State 定义
│   ├── agent_state.py
│   └── redis_saver.py   # Redis 持久化（可选）
├── tools/               # 工具查询层
│   ├── mock_data.py     # 原始硬编码 Mock 数据（2 个订单）
│   ├── mock_factory.py  # 批量生成 Mock 数据（20+ 订单）
│   ├── query.py         # 查询实现（订单、物流、FAQ）
│   └── embedding.py     # 向量嵌入工具
├── nodes/               # 图节点
│   ├── llm_nodes.py     # LLM 语义层：意图理解、推理、生成
│   └── code_nodes.py    # 代码校验层：检索、政策、契约校验、升级
├── graph/               # 状态机构建
│   ├── router.py        # 路由函数（代码硬路由）
│   └── builder.py       # 图构建器
├── config/              # 策略配置
│   ├── policies.yaml    # 业务策略规则
│   └── policy_engine.py # 策略引擎
├── middleware/          # 中间件
│   ├── circuit_breaker.py  # 熔断器
│   └── rate_limit.py    # 限流器
├── observability/       # 可观测性
├── faq-vector-db/       # FAQ 向量数据库数据
├── ui/                  # Gradio 演示界面
│   └── gradio_app.py
└── tests/               # 测试套件
    ├── test_code_nodes.py    # 18 个测试
    ├── test_llm_nodes.py     # 14 个测试（mock LLM）
    ├── test_graph.py         # 5 个集成测试
    └── test_policy_engine.py # 策略引擎测试
```

**数据流方向**：
```
用户输入
  → 意图识别 (intent_node, llm_fast, IntentSchema)
  → 路由决策 (router.py, 代码硬路由)
    ├─→ 自动处理路径：retrieve → policy_check → reason → generate → final_check
    └─→ 升级路径：escalate_gate → escalate
  → 输出回复 + thinking_log
```

### P3. 构建与开发命令

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量（必须）
export ARK_API_KEY="your-api-key"
export ARK_ENDPOINT_ID="deepseek-v3-2-251201"  # 可选，有默认值

# 本地开发（Gradio UI）
python main.py
# 浏览器打开 http://localhost:7860

# 运行测试
ARK_API_KEY="sk-test-fake-key-for-pytest" pytest tests/ -v

# 类型检查（如已安装 mypy）
mypy nodes/ graph/ tools/ schemas/ state/ --ignore-missing-imports

# 代码格式化
black . && isort .

# Docker 构建与运行
docker build -t demo-agent .
docker-compose up
```

### P4. 测试策略

- **测试框架**：pytest
- **测试命令**：`ARK_API_KEY="sk-test-fake-key-for-pytest" pytest tests/ -v`
- **测试覆盖要求**：新增节点/工具必须附带单元测试；图路径变更必须更新集成测试
- **Mock 策略**：
  - LLM 调用使用 `monkeypatch` + 预定义 Schema 实例 mock
  - 订单/物流查询使用 `mock_factory.py` 生成的数据
  - 真实 API Key 永不进入测试流程

**测试文件职责**：
| 文件 | 测试数 | 覆盖范围 |
|------|--------|----------|
| `test_code_nodes.py` | 18 | 检索、政策检查、契约校验、升级、最终校验 |
| `test_llm_nodes.py` | 14 | mock LLM 调用验证 Schema 处理逻辑 |
| `test_graph.py` | 5 | 完整图路径（happy path / blocked path / 多轮记忆） |
| `test_policy_engine.py` | - | YAML 策略规则解析与执行 |

### P5. 部署与发布

- **部署目标**：本地演示（Gradio 7860 端口）/ Docker 容器（FastAPI 8000 端口）
- **容器化**：多阶段 Dockerfile（builder + runtime），非 root 用户运行
- **健康检查**：Docker 内 `http://localhost:8000/health`
- **环境变量清单**：
  - `ARK_API_KEY` —— **必填**，火山方舟 API Key
  - `ARK_ENDPOINT_ID` —— 可选，默认 `deepseek-v3-2-251201`

### P6. 常见陷阱

- **⚠️ 环境变量缺失**：`ARK_API_KEY` 未设置时 LLM 调用会静默失败或报错。本地开发前必须确认已 export。
- **⚠️ Schema 与代码不同步**：修改 `schemas/llm_output.py` 后，必须同步更新：
  1. `nodes/llm_nodes.py` 中的 `with_structured_output()` 引用
  2. `nodes/code_nodes.py` 中的字段访问
  3. `tests/` 中的 mock 数据
  4. README 中的契约表格
- **⚠️ Mock 数据与真实 API 字段不一致**：`tools/mock_data.py` 和 `tools/mock_factory.py` 的字段结构必须保持与真实订单/物流 API 一致，否则生产切换时会踩坑。
- **⚠️ 模型路由参数混淆**：`llm_fast`（temperature=0.0, max_tokens=512）用于意图识别，`llm_main`（temperature=0.1, max_tokens=2048）用于推理生成。切勿互换，否则意图识别会"创造力过剩"，生成会"过于保守"。
- **⚠️ LangGraph 状态字段名变更**：`AgentState` 中的字段名变更后，图中所有引用该字段的节点和路由必须同步修改，没有编译器帮你检查。
- **⚠️ README 与实际文件名不一致**：README 中提到 `config.py`，实际文件名为 `app_config.py`。修改时以实际文件为准，并同步更新 README。

### P7. 项目特定约定

#### 7.1 接口契约驱动（核心设计原则）
- **所有 LLM 输出必须通过 Pydantic Schema 强制格式化**，禁止自由文本解析
- Schema 定义在 `schemas/` 目录，分为 `llm_output.py`（LLM 输出）和 `tool_input.py`（工具参数）
- 契约是"不可协商的协议"，Schema 变更 = 代码变更

#### 7.2 代码硬路由（LLM 只输出信号，代码做决策）
- LLM 节点只输出 `intent`、`confidence` 等信号
- 路由决策由 `graph/router.py` 中的纯 Python 函数完成
- 置信度阈值：`confidence >= 0.7` 自动处理，否则进入升级网关

#### 7.3 模型路由分层
| 用途 | 变量名 | temperature | max_tokens | 备注 |
|------|--------|-------------|------------|------|
| 意图识别 | `llm_fast` | 0.0 | 512 | 低创造力，高确定性分类 |
| 推理决策 | `llm_main` | 0.1 | 2048 | 标准参数 |
| 回复生成 | `llm_main` | 0.1 | 2048 | 标准参数 |

- `thinking_log` 中必须标注每个节点使用的 tier 和参数
- 预留 `get_model_for_task()` 接口，后续可无缝切换多模型

#### 7.4 A/B 实验框架
- `AgentState` 中 `variant` 字段控制回复策略
- `generate_node` 根据 variant 选择不同 prompt 模板
- UI 支持手动切换策略版本

#### 7.5 策略配置
- 业务规则使用 YAML（`config/policies.yaml`），不硬编码在 Python 中
- 策略引擎（`config/policy_engine.py`）负责解析和执行
- 规则变更无需改代码，重启即可生效

#### 7.6 日志与可观测性
- 每个节点必须向 `thinking_log` 写入执行记录（节点名、耗时、输入摘要、输出摘要）
- 生产环境使用 `structlog` + `prometheus-client`
- 禁止在生产日志中打印用户敏感信息（订单号、手机号等）

### P8. 外部依赖与集成

- **LLM 提供商**：火山方舟（Volcengine Ark），base_url: `https://ark.cn-beijing.volces.com/api/v3`
- **模型**：deepseek-v3-2-251201（通过 OpenAI 兼容接口调用）
- **框架**：LangGraph（状态机 + 图执行）、LangChain OpenAI（API 封装）
- **契约校验**：Pydantic v2
- **演示 UI**：Gradio
- **API 服务**：FastAPI + uvicorn（Docker 模式）
- **持久化（可选）**：Redis（`state/redis_saver.py`）
- **向量检索（可选）**：`faq-vector-db/` + `tools/embedding.py`
- **监控**：prometheus-client, structlog

### P9. 生产化替换点

当前使用内存 Mock 数据演示链路，生产环境替换：

| Mock 模块 | 替换方案 |
|-----------|----------|
| `tools/mock_data.py` | 接入内部订单 API |
| `tools/query.py` | 接入物流 API、RAG 向量数据库 |
| `nodes/code_nodes.py:policy_check` | 接入规则引擎（Drools 或内部系统） |
| `state/agent_state.py`（内存） | Redis 持久化 + 分布式锁 |
| `app_config.py`（硬编码） | 配置中心（Nacos / Apollo / Consul） |

---

*本文件生效范围：demo-agent 项目。当 Claude Code 在此目录启动时，内容自动注入会话上下文。*
