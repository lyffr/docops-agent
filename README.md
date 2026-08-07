# DocOps Agent

一个小型的企业知识与工单 AI 项目：支持文档检索、原文引用、无依据拒答、工具调用和人工审批。仓库默认使用离线抽取式生成器，不需要 API Key 即可运行；也可以连接任意 OpenAI-compatible 大模型服务。

> 当前版本可直接用于单机、小规模部署，并保留继续升级检索、模型、存储和可观测性的扩展边界。

## 功能

- 上传 TXT、Markdown、CSV 和文本型 PDF，保留 PDF 页码引用
- BM25 与字符 n-gram 相似度融合的中文离线检索 baseline
- 回答附带原文片段、来源、页码和置信度
- 证据不足时主动拒答
- 识别创建工单意图，使用服务端单次审批记录防止客户端绕过确认
- 使用 SQLite 持久化原始文档、审批、工单和审计事件，重启后自动恢复索引
- 提供文档列表、删除和重新索引接口
- API Key 鉴权以及 reader、operator、admin 三级权限
- JSON 请求日志、请求 ID、存活/就绪探针和安全响应头
- 非 root、只读文件系统、数据卷和健康检查加固的 Docker 部署
- FastAPI、Streamlit、Docker Compose、自动化测试与 GitHub Actions
- JSONL 评测集和可复现评测脚本

## 快速开始

需要 Python 3.10 或更高版本。

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
uvicorn docops_agent.api:app --reload
```

打开 [Swagger API](http://localhost:8000/docs)。另开一个终端启动界面：

```bash
streamlit run docops_agent/streamlit_app.py
```

也可以直接以开发配置使用 Docker：

```bash
docker compose up --build
```

- API：<http://localhost:8000/docs>
- UI：<http://localhost:8501>

实际部署前请阅读[部署指南](docs/deployment.md)，不要把开发配置直接暴露到公网。

## 演示

服务启动时会自动加载一份虚构的员工手册，可以直接提问：

```text
试用期员工有多少天年假？
报销申请最晚什么时候提交？
公司创始人的生日是哪一天？
创建工单：办公电脑无法开机
```

前三个问题分别展示有依据回答、引用和无依据拒答；最后一个请求必须经过确认才会创建工单。

## 连接真实大模型

复制 `.env.example` 为 `.env`，填写兼容接口：

```dotenv
DOCOPS_LLM_PROVIDER=openai-compatible
DOCOPS_LLM_BASE_URL=https://your-endpoint.example/v1
DOCOPS_LLM_API_KEY=your-key
DOCOPS_LLM_MODEL=your-model
DOCOPS_DATABASE_PATH=data/docops.db
```

密钥不会提交到 Git。生成器只会收到检索到的证据，并被要求给每个事实添加 `[1]` 格式的引用。

## 评测

运行单元测试和离线评测：

```bash
python -m unittest discover -s tests -v
python scripts/evaluate.py
```

评测脚本报告关键词正确率、拒答准确率和来源 Recall@K。`data/eval.jsonl` 只是小型演示集，实际使用前建议扩充到 300～500 条，并按照事实问答、跨段推理、表格、无答案和工具任务分层统计。

## API 示例

文档管理接口包括：

- `GET /documents`：列出文档及分节、文本块、页数和更新时间
- `DELETE /documents/{document_id}`：删除文档及其持久化原文和索引
- `POST /documents/{document_id}/reindex`：使用持久化原文重新建立索引

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question":"正式员工一年有几天年假？"}'
```

```bash
curl -X POST http://localhost:8000/agent/run \
  -H "Content-Type: application/json" \
  -d '{"message":"创建工单：电脑无法启动"}'
```

该请求只创建待审批记录。使用返回的审批 ID 调用
`POST /approvals/{approval_id}/approve` 后，系统才会在同一数据库事务中创建工单。生产环境的请求还必须携带 `X-API-Key`。

## 项目结构

```text
docops_agent/
├── agent.py          # 意图路由与人工审批
├── api.py            # FastAPI 接口
├── chunking.py       # 分页文本切块
├── generation.py     # 离线/大模型生成器
├── observability.py  # JSON 日志、请求 ID 与安全响应头
├── parsers.py        # TXT、CSV、PDF 解析
├── persistence.py    # SQLite 文档、审批、工单与审计持久化
├── rag.py            # 检索生成与拒答
├── retrieval.py      # 混合检索 baseline
├── security.py       # API Key 鉴权与角色权限
├── streamlit_app.py  # 演示界面
└── workflow.py       # 服务端审批和审计工作流
data/                 # 演示文档与评测集
deploy/               # 反向代理配置示例
docs/                 # 架构、部署、安全、API 与运维文档
requirements.lock     # 容器使用的固定版本运行时依赖
requirements-dev.lock # CI 使用的固定版本开发依赖
scripts/              # 离线评测
tests/                # 单元测试
```

## Documentation

- [架构说明](docs/architecture.md)
- [部署指南](docs/deployment.md)
- [配置参考](docs/configuration.md)
- [API 指南](docs/api.md)
- [安全模型](docs/security.md)
- [运维手册](docs/operations.md)

## 后续升级路线

1. 用 BGE-M3/E5 等嵌入模型替换字符相似度，报告 Recall@5 变化。
2. 加入 Cross-Encoder Reranker，做检索阶段消融实验。
3. 增加扫描 PDF、表格和图片解析，建立多模态评测子集。
4. 收集错误案例进行 LoRA/SFT，再比较正确率和拒答率。
5. 接入 OpenTelemetry、指标采集、分布式追踪和 Token 成本看板。

## License

[MIT](LICENSE)
