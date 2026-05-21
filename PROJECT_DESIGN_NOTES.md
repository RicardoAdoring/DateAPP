# 项目设计与开发说明

本文档用于记录恋爱约会规划项目的整体设计、核心架构、技术层选择和开发改动。文档口径按照“从零设计一个地图选点驱动的约会一日游 Agent 项目”来组织，方便后续开发、排查、验收和交接。

## 1. 项目整体架构

### 1.1 项目定位

这是一个面向恋爱约会场景的一日游路线规划应用。用户可以输入地点或地址，也可以直接在地图上点击选点；系统会解析出地点、地址和坐标，再围绕这个中心点生成一天的约会路线，包括活动、餐饮、休息、夜间轻活动、预算和相邻路线。

系统目标不是只生成一段文字建议，而是把“地图选点、周边 POI 发现、外部搜索增强、RAG 知识补充、Agent 规划、路线估算、流式展示、保存与导出”做成一条完整产品链路。

核心链路如下：

```text
地点输入或地图选点
  -> 标准化中心点地址与坐标
  -> 高德 MCP 收集周边 POI
  -> SearchApi.io 补充评分、评论、图片、攻略线索
  -> RAG 提供本地攻略知识补充
  -> LLM 基于结构化候选生成严格 JSON 方案
  -> 高德 MCP 重新估算相邻路线
  -> 前端流式展示思考、安排节点、路线段和最终 itinerary
```

### 1.2 前端架构

前端使用 Vue 3 + Ant Design Vue，整体界面设计为约会规划工作台。

- `App.vue` 管理全局视图状态，包括规划页、流式执行页、结果页和历史页。
- `Home.vue` 是主入口，承载地图选点、地点搜索、日期、时间段、预算、人数、偏好、饮食限制、交通方式和半径等输入。
- `LocationPickerMap.vue` 负责高德 JS 地图加载、关键词搜索、候选列表、地图点击选点、反向地理编码和 marker 展示。
- `StreamingPlanner.vue` 负责流式生成和流式调整，按阶段展示 Agent 思考、安排节点、路线段和最终结果。
- `Result.vue` 展示一日时间线、地图点位、餐饮、玩乐、预算、交通、天气参考、来源信息和智能调整入口。
- `AmapTripMap.vue` 在结果页按时间顺序绘制编号 marker，并连接一日路线。
- `History.vue` 负责展示保存过的 itinerary 记录。
- `frontend/src/services/api.ts` 统一封装 REST 接口和 POST + NDJSON 流式读取。
- `frontend/src/types/index.ts` 维护地点、约会请求、流式事件和 itinerary 相关类型。

### 1.3 后端架构

后端使用 FastAPI，按 API 层、Service 层、Provider 层、Agent 层、RAG 层和配置层组织。

- API 层：`backend/app/api/routes/*`
  - `/location/search`：地点搜索。
  - `/location/reverse-geocode`：经纬度反查地址。
  - `/date-plan/generate`：同步生成约会一日游。
  - `/date-plan/generate/stream`：流式生成约会一日游。
  - `/trip/edit/stream`：流式调整既有 itinerary。
  - `/trip/*`：行程列表、生成、保存、详情、删除和统计能力。
  - `/weather/*`：天气查询。
  - `/export/*`：Markdown 和 PDF 导出。
- Service 层：`backend/app/services/*`
  - `date_plan_service.py` 负责约会一日游编排。
  - `location_service.py` 负责地点搜索和反向地理编码。
  - `trip_service.py` 负责 itinerary 生成、保存和调整。
- Provider 层：`backend/app/services/providers/*`
  - `amap_mcp_provider.py` 封装高德 MCP 能力。
  - `searchapi_provider.py` 封装 SearchApi.io 能力。
- Agent 层：`backend/app/agents/*`
  - `trip_planner_agent.py` 负责 LLM 规划和结构化输出。
  - `tools/rag_tool.py` 负责 RAG 查询改写、检索和召回内容整理。
- 配置层：`backend/app/config.py`
  - 统一读取 DeepSeek、DashScope、Redis、高德 MCP、SearchApi、数据库和缓存 TTL 等环境变量。

### 1.4 Agent 编排层

约会规划编排由 `date_plan_service.py` 承接，核心原则是让 LLM 基于真实候选地点做规划，减少自由编造地点的风险。

主要步骤：

- 标准化用户选择的 `anchor location`，确保具备名称、地址、经纬度和城市信息。
- 围绕中心点按类别收集候选 POI：餐厅、咖啡/甜品、景点、公园/步道、展馆/影院、商圈、夜间轻活动。
- 使用 SearchApi.io 补充评分、评论数量、图片、链接、营业时间和攻略线索。
- 将候选 POI、用户预算、时间段、偏好、人数、交通方式等结构化输入交给 LLM。
- 要求 LLM 输出严格 JSON，建议 4-6 个停靠点，覆盖核心活动、午餐或晚餐、休息点、夜间轻活动。
- 如果 LLM 输出不可解析或不可用，使用规则 fallback 生成基础路线。
- 最终用高德 MCP 重新计算相邻点位的交通距离和耗时，并写入 `transport`。
- 输出统一转换为 `Itinerary`，用于结果展示、保存、历史和导出。

### 1.5 RAG 层

RAG 层用于把本地攻略知识注入规划过程，帮助 Agent 在约会安排、城市玩法、路线节奏和风格化建议上获得更稳定的上下文。当前实现集中在 `backend/app/rag` 与 `backend/app/agents/tools/rag_tool.py`。

- 知识来源：`backend/data/*.md` 本地攻略文档。
- 文档切分：`vector_db.py` 按 Markdown 二级、三级标题切分 chunk，保留标题、正文和 metadata。
- 向量模型：通过 LangChain `OpenAIEmbeddings` 的 OpenAI-compatible 接口调用 Embedding 服务；当前部署使用 DashScope Embedding，具体模型由环境变量控制。
- 向量库：使用 ChromaDB 持久化 collection，检索空间为 cosine。
- 检索策略：优先走 Chroma 向量检索；当向量库或 embedding 不可用时，回退到关键词检索。
- Query Rewrite：`rag_tool.py` 优先使用 LLM 改写查询，失败时使用规则改写。
- Rerank：`retriever.py` 优先调用 DashScope `qwen3-rerank` 做 Cross-encoder 重排序，失败时回退到规则打分。
- 缓存：Redis 缓存 RAG 检索、Rerank 结果和相关中间结果，减少重复调用和外部依赖压力。
- Token 统计：Rerank 和 Planner 的 token usage 会被记录，并随部分接口结果返回，方便观察成本。

### 1.6 外部 Provider 层

外部依赖集中在后端 Provider 层，前端不直接持有服务端密钥。

- LLM Provider：主链路使用 DeepSeek 的 OpenAI-compatible 接口，当前规划模型配置为 `deepseek-v4-flash`；当 DeepSeek 连接失败、调用异常、返回空内容或结构化 JSON 解析失败时，自动尝试 Ollama 本地模型 fallback。
- Embedding Provider：使用 DashScope Embedding，环境变量控制 provider、base URL、model 和 key。
- Rerank Provider：使用 DashScope `qwen3-rerank`，失败时自动回退规则排序。
- 高德地图 Provider：默认走 MCP，后端通过 Python `mcp` SDK 以 stdio 方式调用 `@amap/amap-maps-mcp-server@0.0.8`，覆盖地理编码、反向地理编码、文本搜索、周边搜索、POI 详情和路线估算。
- Search Provider：使用 SearchApi.io，优先 `engine=google_maps` 补充 POI 可信度信息，必要时 `engine=google` 查询活动、攻略和来源线索。
- 降级策略：SearchApi 失败时降级为高德 MCP-only；高德 MCP 不可用时返回清晰错误，让前端展示地图工具不可用。

### 1.7 缓存与持久化

- SQLite：保存 itinerary、历史记录和详情数据。
- Redis：作为短期缓存层，缓存天气、地图查询、SearchApi 查询、路线估算、RAG 检索和 Rerank 结果。
- ChromaDB：作为 RAG 向量库持久化存储本地攻略 chunk。
- 本地 Markdown：作为可维护的攻略知识源，便于扩充城市、路线和风格化约会建议。

### 1.8 Docker 部署结构

Docker Compose 采用三服务结构：

- `redis`：缓存服务。
- `backend`：FastAPI 后端，镜像内安装 Python 依赖、Node 20，并全局安装 `@amap/amap-maps-mcp-server@0.0.8`，运行时默认调用 `mcp-amap`。
- `frontend`：Vue 前端构建和运行服务。

关键环境变量按职责拆分：

```text
PLANNER_LLM_MODEL=deepseek-v4-flash
OLLAMA_FALLBACK_ENABLED=true
OLLAMA_FALLBACK_MODEL=qwen2.5:7b
OLLAMA_FALLBACK_BASE_URL=http://host.docker.internal:11434/v1
EMBEDDING_PROVIDER=dashscope
RERANK_PROVIDER=dashscope
AMAP_PROVIDER=mcp
MCP_AMAP_COMMAND=mcp-amap
SEARCHAPI_BASE_URL=https://www.searchapi.io/api/v1/search
SEARCHAPI_TIMEOUT_SECONDS=20
REDIS_ENABLED=true
REDIS_URL=redis://redis:6379/0
```

实际 API key 只写入本地 `.env` 或 Docker 环境，不写入仓库文档。

## 2. 开发改动记录

### 2.1 约会一日游主流程

- 设计地图选点驱动的约会一日游 Agent 主流程。
- 实现围绕单个中心点生成一天约会路线的业务链路。
- 默认规划人数为 2 人，默认时间段为 10:00-22:00，默认半径为 3000 米，默认交通方式偏向步行和公共交通混合。
- 生成内容覆盖玩乐、餐饮、休息、夜间轻活动、预算和相邻路线。
- 输出统一使用 `Itinerary` 结构，支持结果展示、保存、历史和导出。

### 2.2 地图选点与地点解析

- 新增 `GET /location/search`，按关键词和可选城市返回地点候选。
- 新增 `GET /location/reverse-geocode`，按经纬度返回行政区、地址、地点名和坐标。
- 新增 `LocationPickerMap.vue`，支持地点搜索、候选选择、地图点击、反向地理编码、marker 展示和当前地址展示。
- 首页展示已选地点的名称、地址、坐标和简要状态，用户可以在生成前确认中心点。

### 2.3 约会规划接口与数据模型

- 新增 `POST /date-plan/generate`，输入中心点、日期、时间段、预算、人数、偏好、饮食限制、交通方式和半径，返回兼容 `Itinerary` 的结果。
- 新增 `SelectedLocation`、`LocationCandidate`、`DatePlanRequest`、`PoiCandidate`、`PlanSource` 等类型。
- 扩充 `SpotItem` / `MealItem`，补充开始时间、结束时间、地址、经纬度、POI ID、图片和来源相关字段。
- 前端同步补充约会规划请求、地点候选、流式事件和执行任务类型。

### 2.4 Provider 隔离

- 新增高德 MCP Provider，封装地理编码、反向地理编码、文本搜索、周边搜索、POI 详情和路线估算。
- 新增 SearchApi.io Provider，使用 Google Maps / Google Search 结果补充评分、评论、图片、链接、摘要和攻略线索。
- DeepSeek LLM、Ollama fallback、DashScope Embedding、DashScope Rerank、高德 MCP、SearchApi 均集中由后端环境变量配置。
- SearchApi 不可用时自动降级，高德 MCP 不可用时向接口层抛出明确错误。
- 前端只配置浏览器端必须使用的高德 Web JS key 和安全密钥，不接触服务端 LLM、DashScope、SearchApi 密钥。

### 2.5 约会规划编排服务

- 新增 `date_plan_service.py`，承接约会一日游专属业务逻辑。
- 按餐厅、咖啡/甜品、景点、公园、展馆/影院、商圈、夜间轻活动等类别收集候选 POI。
- SearchApi 成功时合并可信度信息，失败时记录降级说明并使用高德候选完成规划。
- LLM 规划阶段只允许从候选 POI 中选择地点，并要求输出严格 JSON。
- 新增规则 fallback，在 LLM 输出不可用时仍可生成基础路线。
- 生成完成后重新估算相邻点位的距离和耗时，保证 `transport` 字段更接近真实路线。
- 预算重新按餐饮、活动、交通和弹性费用汇总，减少固定模板感。

### 2.6 流式生成与流式调整

- 新增 `POST /date-plan/generate/stream`，生成过程中流式输出阶段、思考、安排节点、路线段和最终 itinerary。
- 新增 `POST /trip/edit/stream`，智能调整阶段也复用同一套流式体验。
- 后端采用 `StreamingResponse` 返回 POST + NDJSON，一行一个 JSON event。
- 前端 `api.ts` 新增 `streamJsonLines()`，使用 `fetch`、`ReadableStream` 和 `TextDecoder` 逐行解析事件。
- 新增 `StreamingPlanner.vue`，首页点击生成后立即跳转到流式执行页，展示每一步规划过程。
- 流式事件类型包括：

```text
stage      当前执行阶段
thought    Agent 的阶段性判断
plan_item  逐步产出的活动或餐饮节点
route      相邻停靠点交通路线
complete   最终 itinerary
error      明确失败原因
```

### 2.7 结果页与地图展示

- `Result.vue` 强化一日时间线，统一展示活动、餐饮、预算、路线交通、天气参考和来源信息。
- `AmapTripMap.vue` 支持按时间顺序绘制编号 marker，并用虚线连接约会路线。
- 结果页的“智能调整”入口改为跳转流式执行页，调整完成后可返回结果页保存或导出。
- 历史页展示已保存 itinerary，视觉风格统一到工作台样式。

### 2.8 UI/UX 优化

- 使用统一设计 token 重做全局视觉，包括 `surface`、`ink`、`accent`、`teal`、`line`、`radius`、`shadow` 等变量。
- 顶部导航改为更紧凑的工具型导航，规划、结果、历史三个入口状态更清晰。
- 首页、地图选点、结果页、历史页统一为工作台风格，减少大面积装饰性渐变和过大圆角。
- 候选地点列表、已选地点、搜索按钮、空状态、加载状态和 disabled 状态重新整理。
- 移动端断点完成检查，主要页面无横向溢出，核心内容可以单列展示。

### 2.9 Docker 与运行环境

- 后端 Docker 镜像安装 Node 20，并全局安装 `@amap/amap-maps-mcp-server@0.0.8`。
- 容器运行时默认调用 `mcp-amap`，避免启动时临时拉取 npm 包。
- Docker Compose 配置 `redis`、`backend`、`frontend` 三服务。
- 后端容器通过环境变量接收 LLM、DashScope、高德、SearchApi、Redis 和数据库配置。
- 前端容器只接收 `VITE_API_BASE_URL`、`VITE_AMAP_JS_KEY`、`VITE_AMAP_SECURITY_JS_CODE` 等浏览器端必需配置。
- Redis 已纳入 Docker 部署，用于缓存地图、SearchApi、路线估算、RAG 和 Rerank 等中间结果。

### 2.10 兼容性与健壮性修复

- 修复高德 MCP 返回 `address`、`city`、`type` 等字段可能为数组时导致 Pydantic 校验失败的问题。
- 新增 `_string_or_none()` 规范化函数，将数组、字典和其他非字符串值转换为可用字符串。
- 修复流式路线文案中“距离待估 km”的显示问题，改成更自然的“距离待估”。
- 调整智能编辑流心跳频率，减少重复刷屏造成的思考列表噪音。
- SearchApi 失败、Rerank 失败、LLM JSON 解析失败等场景均提供降级路径或明确错误。

### 2.11 测试与验收

- 新增 `/date-plan/generate/stream` 测试，覆盖 NDJSON 阶段事件和最终 itinerary。
- 新增 `/trip/edit/stream` 测试，覆盖调整过程事件、节点输出和最终 itinerary。
- 扩充高德 MCP Provider 测试，覆盖数组形式 `address` 的解析兼容。
- 完成 `/trip/generate`、保存、历史、导出、天气、RAG、存储等回归测试。

最近一次验证结果：

```text
python -m pytest tests/test_date_plan_features.py tests/test_api_trip.py -q
23 passed

python -m pytest tests -q
45 passed, 4 warnings

npm run build
构建通过，仅有 Vite chunk size warning

docker compose up --build -d frontend
backend healthy / frontend running / redis healthy
```

浏览器验收结果：

- 输入“上海外滩”可以返回地点候选。
- 选择候选后地图 marker 正确移动，中心点摘要、地址和坐标正确展示。
- 点击“生成约会路线”会进入新的流式执行页。
- 真实生成过程中成功展示约 22 条事件、6 个安排节点和 6 段路线。
- 生成完成后可以进入完整结果页，地图、时间线、预算、交通、天气和来源展示正常。
- 结果页点击“调整路线”会进入同一套流式执行页。
- 调整完成后可返回结果页保存或导出。

一次真实生成样例：

```text
中心点：外滩
时间：10:00-22:00
人数：2
预算：900
偏好：轻松聊天、美食探店、夜景氛围

生成节点：
1. 外滩
2. 瑞幸咖啡(外滩店)
3. TOR外滩一号·露台餐厅
4. 上海电信博物馆
5. 窠石园
6. The Fellas Terrace(七楼露台餐厅店)
```
