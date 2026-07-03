# ModNews 项目整理建议

日期：2026-07-03

## 当前判断

项目原本有三条主线混在一起：

1. `modnews_pipeline/`：旧主入口，负责 ingest、classify、WebUI API、managed extractor、repair、job store、runtime config。
2. `src/`：报告生成层，读取 `output/combined_news.json` 后做评分、核验、摘要和日报输出。
3. 根目录运行态/历史文件：`output/`、`runtime/`、`var/`、`.agent_work/`、嵌套的 `modnews/`、若干中文/PRD 文档和样例 JSON。

主要问题不是某个目录名，而是边界不清：`web.py` 同时做 Flask 路由、后台任务调度、配置读写、输出状态读取、extractor/job/repair API；`ingest`、`classify`、`web_extraction` 各自维护流程状态和事件；配置、缓存、checkpoint、job store 分散在多个模块。

## 目标结构

主包从 `modnews_pipeline` 改为更通用的 `modnews`。项目名 `newsagent` 可以保留为发行包名，但 Python import 包名和主程序入口统一为 `modnews`。最终形态不再保留 `modnews_pipeline` 包；外部脚本如仍引用旧包，需要迁移到 `modnews.*`。

推荐目标目录：

```text
 modnews/
  app/
    __init__.py
    server.py
    routes/
      __init__.py
      health.py
      runtime_config.py
      pipeline.py
      events.py
      extractors.py
      web_jobs.py
      repair_tasks.py
    router.py
  bootstrap/
    __init__.py
    pipeline_registry.py
    event_handlers.py
    service_registry.py
  core/
    context.py
    events.py
    event_queue.py
    task.py
    models.py
    paths.py
  service/
    pipeline/
      manager.py
      registry.py
      step.py
      checkpoint.py
      planner.py
      callbacks.py
      run_state.py
    ingest/
      registry.py
      steps/
        rss.py
        newsnow.py
        site_lists.py
    classify/
      tasks.py
      clustered_tasks.py
      io.py
    extraction/
      contract.py
      metadata.py
      web_contract.py
      registry.py
      runner.py
      web_runner.py
      repair_policy.py
      orchestrator.py
      repair.py
    report/
      __init__.py
      pipeline.py
  repository/
    runtime_config.py
    source_config.py
    outputs.py
    cache.py
    checkpoints.py
    web_jobs.py
    event_jsonl.py
    event_log.py
  cli/
    __init__.py
    main.py
    context.py
    output.py
    api_client.py
    local_client.py
    commands/
      __init__.py
      server.py
      run.py
      events.py
      queue.py
      config.py
      sources.py
      extractors.py
      jobs.py
      repair.py
      outputs.py
      cache.py
      checkpoints.py
```

这不是要求一次性搬完，而是给迁移时的最终形态。`pipeline`、`ingest`、`classify` 不应作为顶层公开包暴露；它们统一放在 `modnews/service/` 服务层下。顶层只暴露 `app`、`cli`、`core` 里稳定的基础类型，以及必要的 bootstrap 入口。当前分支已经删除 `modnews_pipeline/` 兼容包，后续不再新增旧包转发层，避免项目长期存在两个入口。

## 分层建议

### Router / Blueprint 层

旧 `modnews_pipeline/web.py` 已拆成 Flask blueprint：

- `app/routes/runtime_config.py`：`/api/runtime-config`、source config 增删改。
- `app/routes/pipeline.py`：`/api/run`、运行锁、后台线程启动。
- `app/routes/events.py`：`/api/events` SSE、`/api/state`。
- `app/routes/extractors.py`：extractor 列表、启停、删除。
- `app/routes/web_jobs.py`：web job 列表、详情、事件、单 source 运行。
- `app/routes/repair_tasks.py`：repair task CRUD、retry、promote。
- `app/router.py`：统一注册所有 blueprint。

路由层只做 HTTP 解析和响应，不直接拼路径、不直接读写 JSON、不直接调用 `emit()` 之外的底层细节。业务操作进入 service/orchestrator，持久化进入 repository。

### CLI 层

CLI 应该是一等入口，不依赖前端，也不要求用户一定启动 WebUI。它需要支持两种执行模式：

- API 模式：连接已运行的 `modnews-server`，通过 HTTP API 操作和查询。
- Local 模式：不启动 server，直接通过 bootstrap 初始化 service/repository，在当前进程内执行同样的操作。

默认行为建议：查询类命令优先尝试 API，连不上时自动降级 local；会启动长任务或修改配置的命令默认 local，也允许用 `--api-url` 强制走 API。这样既适合本地开发，也适合未来远程部署。

推荐 CLI 目录结构：

```text
modnews/cli/
  main.py              # 顶层命令入口，只做 parser/dispatch
  context.py           # CLI 上下文：project_root、api_url、format、mode
  output.py            # table/json/jsonl/text 输出
  api_client.py        # HTTP API client
  local_client.py      # 本地 service/repository client
  commands/
    server.py          # 启停/探活 API server
    run.py             # pipeline run/resume/cancel/status
    events.py          # 事件流监控
    queue.py           # 事件队列查询和控制
    config.py          # runtime config 查询/修改/导入导出
    sources.py         # rss/newsnow/site source 管理
    extractors.py      # managed extractor 扫描/启停/运行/校验
    jobs.py            # web job 查询/查看日志/重试
    repair.py          # repair task 管理
    outputs.py         # 输出文件状态/发布/打开路径
    cache.py           # cache 查看/清理
    checkpoints.py     # run checkpoint 查询/恢复/发布
```

CLI 不应直接 import `service/ingest` 或 `service/classify` 的具体实现。它只依赖 `api_client` 或 `local_client`，local client 通过 `bootstrap.configure_services()` 拿到统一服务。这样 CLI、API、未来前端调用的是同一套服务能力。

建议命令形态：

```bash
modnews server start --host 127.0.0.1 --port 5055
modnews server status

modnews run start --only rss --only newsnow
modnews run start --disable-classify
modnews run resume <run_id>
modnews run status <run_id>
modnews run list
modnews run cancel <run_id>

modnews events watch
modnews events watch --run <run_id>
modnews events list --run <run_id> --limit 100

modnews queue status
modnews queue list --state queued,running
modnews queue show <task_id>
modnews queue retry <task_id>
modnews queue cancel <task_id>
modnews queue skip <task_id> --reason "optional source blocked"

modnews config show
modnews config set classification.batch_size 40
modnews config set steps.newsnow.enabled false
modnews config export --output config.backup.json
modnews config import config.backup.json

modnews sources list
modnews sources rss add <id> <url> --name "..."
modnews sources rss disable <id>
modnews sources site add <id> <url> --extractor anthropic

modnews extractors scan
modnews extractors list
modnews extractors validate <id>
modnews extractors enable <id>
modnews extractors run <id> --limit 10

modnews jobs list
modnews jobs show <job_id>
modnews jobs events <job_id>

modnews repair list
modnews repair create <source_id>
modnews repair retry <task_id>
modnews repair promote <task_id>

modnews checkpoints list --run <run_id>
modnews checkpoints show <checkpoint_id>
modnews checkpoints publish <checkpoint_id>

modnews outputs status
modnews cache status
modnews cache clear --llm --embedding
```

输出格式统一支持 `--format table|json|jsonl`。所有会修改状态的命令支持 `--dry-run`，所有 watch 类命令支持 `--follow`/`--since-id`，所有 API 模式命令支持 `--api-url`。

### 事件队列与完成回调

当前 `progress.py` 是全局 `ProgressBus`，`web_extraction/events.py` 是 job-local JSONL，classify checkpoint 又单独 emit。建议统一为 `core/events.py` 和 `core/event_queue.py`：

- `EventBus`：内存广播，给 SSE 使用。
- `EventQueue`：负责接收任务事件、调度 worker、限制并发、维护任务状态。
- `EventLogRepository`：写入 job/pipeline 事件 JSONL。
- `EventRouter`：注册事件处理器，例如 `on("web_job.succeeded", callback)`。
- `CompletionCallbackRegistry`：统一注册自动回调，例如 web job 成功后刷新 output state，extractor repair promote 后更新 source config。

核心原则：实际执行不放在 step 内部。所有可执行工作都创建为事件/任务对象，带上并发和资源约束信息后注册到事件系统。事件系统统一处理并发、重试、状态落库、完成回调和失败回调。

网页爬取、LLM 调用、embedding 调用、Codex repair 都属于异步任务，不应由 ingest/classify step 自己开线程池或维护 retry/blocked 状态。step 只构造 `TaskEvent`，并声明 `concurrency_key`、`max_concurrency`、`max_attempts`、`depends_on`、`checkpoint_policy` 等调度信息；EventQueue 负责执行、重试、blocked 标记和日志落库。前端按 `task.type` 选择不同日志视图，例如 `web_source.run` 展示 web job events，`classify.batch_item.*` 展示 LLM/embedding 请求日志，`extractor.repair.codex` 展示 Codex JSONL 尾部和修复产物。

任务对象建议包含：

```python
class TaskEvent:
    id: str
    type: str
    pipeline_run_id: str
    step_id: str
    payload: dict
    concurrency_key: str | None
    max_concurrency: int | None
    depends_on: list[str]
    checkpoint_policy: str
```

事件命名建议分命名空间：

```text
pipeline.started
pipeline.stage_started
pipeline.stage_completed
pipeline.failed
ingest.source_started
ingest.source_completed
classify.checkpoint_written
web_job.created
web_job.succeeded
web_job.failed
repair_task.created
repair_task.promoted
cache.cleared
```

迁移时先让旧 `emit("step_start", ...)` 兼容转成新事件，避免一次改完所有调用点。

### Step 职责

step 不应再是“执行具体业务的 runner”。step 应该是“往事件队列注册哪些事件的判断系统”和“顺序依赖同步器”：

- 根据当前 run state、checkpoint、配置和上一步完成结果，判断下一批需要注册的 `TaskEvent`。
- 对必须顺序运行的任务，等待上一条任务完成回调后，才注册下一条任务。
- 对可并发任务，只声明 `concurrency_key`、`max_concurrency`、资源类型、依赖关系，不自己创建线程池。
- 不直接写 checkpoint，不直接写 output，不直接读写缓存。
- 接收 `task.completed`、`task.failed`、`task.blocked` 回调后，只做流程同步决策：注册下一批任务、停止该 run、或把确认可忽略的 blocked 任务标记为 skipped。

例如 ingest 的 RSS、NewsNow、managed extractor 都是任务事件；classify 的 batch relevance、embedding、event extraction、merge 也是任务事件。step 只决定“现在可以发哪些任务”，事件系统决定“什么时候执行、并发多少、完成后回调谁”。

blocked 的处理要分两类：

- 硬阻断：依赖失败、缺配置、登录/CAPTCHA、权限不足、extractor 需要修复等，保持 `blocked`，由 CLI/API/前端提示人工处理，必要时 `queue retry`。
- 安全跳过：可选 source、可选 batch、已确认无可恢复价值的外部阻断，step 的 `on_task_blocked(event, queue)` 回调可以调用 `queue.skip(task_id, reason=...)`。`skipped` 是终态，也是依赖可继续的成功类状态；下游依赖会自动从 blocked 释放回 queued。run 最终如果包含 skipped task，应标记为 `partial`，不误报完整成功。

### Repository 层

建议把所有“保存配置文件、读取配置文件、缓存/落库/运行态文件”收敛到 `modnews/repository/`：

- `RuntimeConfigRepository`：现在的 `runtime_config.py`。
- `SourceConfigRepository`：source 管理 facade，底层可复用 runtime config store，但对外暴露 `list`、RSS/site upsert、disable、restore builtins、enabled source 查询等领域方法。
- `OutputRepository`：读取 `combined_news.json`、`news_with_events.json`、`events.json`、`discarded_news.json` 状态，替代 `web.py::_output_state`。
- `CheckpointRepository`：classify checkpoint 读写，替代 `classify/checkpoint.py` 中直接写文件的部分。
- `CacheRepository`：LLM/embedding cache 路径、清理、统计。
- `WebJobRepository`：现在的 `web_extraction/job_store.py`。
- `ExtractorRepository`：extractors 根目录扫描、启停、删除、promote。
- `RunRepository`：保存每次 pipeline run 的元信息、状态和时间戳目录。

这样路由层和流程层都不直接碰文件布局。以后如果换 SQLite，也只影响 repository。

### 统一 checkpoint

每个步骤 checkpoint 需要有统一位置和统一格式，不应由 classify 单独维护。建议由 `service/pipeline/checkpoint.py` 提供 `CheckpointManager`，所有 step/task 通过它写 checkpoint。

目录建议：

```text
var/process/runs/
  20260703T153012Z-main/
    run.json
    events.jsonl
    checkpoints/
      ingest/
        20260703T153015Z-rss/
          checkpoint.json
          items.json
          raw.json
        20260703T153018Z-newsnow/
          checkpoint.json
          items.json
      classify/
        20260703T153100Z-clustered_event_extraction/
          checkpoint.json
          news_with_events.json
          events.json
          discarded_news.json
        20260703T153230Z-clustered_event_merge/
          checkpoint.json
          events.json
      extraction/
        20260703T153020Z-anthropic/
          checkpoint.json
          items.json
          raw_result.json
```

`checkpoint.json` 至少包含：

- `run_id`
- `step_id`
- `task_id`
- `status`
- `started_at`
- `finished_at`
- `input_refs`
- `output_refs`
- `stats`
- `error`

稳定输出仍可以写到 `output/combined_news.json`、`output/events.json` 等固定路径，但这些应该是 `OutputRepository` 从最新成功 checkpoint 发布出来的结果，而不是 step 随手写文件。

### 统一流程/事件系统

现在流程系统有三套：

- 顶层 `pipeline.py` 手写 ingest -> classification。
- `ingest/stage.py` 用 `STEP_FACTORIES`。
- `classify/runner.py` 用 `ClassifyStepRunner` 和 `ClassifyState.stage`。
- `web_extraction/orchestrator.py` 自己维护 `WebJob.state` 和 retry/repair。

建议统一到 `service/pipeline/manager.py`，但它不直接 import 具体 ingest/classify step。具体 step 在 bootstrap 阶段注册：

```python
class PipelineManager:
    def register_step(self, step): ...
    def start_run(self, request): ...
    def on_task_completed(self, event): ...
    def on_task_failed(self, event): ...

class PipelineStep(Protocol):
    id: str
    def plan(self, state, completed_event=None) -> list[TaskEvent]: ...
```

启动流程统一组装：

```python
def configure_services(container):
    manager = container.pipeline_manager
    manager.register_step(container.ingest_rss_step)
    manager.register_step(container.ingest_newsnow_step)
    manager.register_step(container.ingest_site_lists_step)
    manager.register_step(container.classify_cluster_extract_step)
    manager.register_step(container.classify_cluster_merge_step)
    container.event_router.on("task.completed", manager.on_task_completed)
    container.event_router.on("task.failed", manager.on_task_failed)
```

这样 `PipelineManager` 只管 step 注册、run 启动和完成/失败事件转发，`EventQueue` 管并发和执行，`CheckpointManager` 管落盘，具体业务 executor 只处理某一种 task。run 状态同步、完成后 payload patch、自动发布等副作用放在 `pipeline/run_state.py`、`pipeline/callbacks.py` 或 bootstrap event handler 中，避免 manager 重新变成大入口。`pipeline` 不直接关联 `ingest` 或 `classify` 的实现，关联关系只存在于 bootstrap 注册代码中。

## 当前迁移状态

截至 `refactor/modnews-service-architecture` 分支当前阶段：

- 已建立 `modnews/` 包、`app` router、`bootstrap`、`core`、`service`、`repository`、`cli` 骨架。
- 旧 `modnews_pipeline.web` 的 API/server 职责已迁入新 `modnews.app`。
- CLI 已支持 local/API 双模式，覆盖配置、事件、队列、run、extractor、job、repair、output、cache、checkpoint 查询和基础操作；`run resume` 会推进当前 run 的 queued/waiting task，`run cancel` 会取消未执行 task 并标记 run，`queue skip` 可在人工确认或 step 回调确认后安全跳过 blocked task。
- 已新增 `RunRepository`、`CheckpointManager`、`EventQueue`、`TaskEvent`，pipeline run 会通过 `pipeline.run_legacy` task 执行并写入 `var/process/runs/<run_id>/...`。
- `EventQueue` 已支持 `depends_on` 依赖等待、`concurrency_key`/`max_concurrency` 并发槽、完成/失败/业务阻断事件回调、`queue drain` 手动推进和 ready/waiting/blocked 状态查询。`waiting` 表示依赖或并发槽尚不可用；`blocked` 保留给依赖终止、CAPTCHA、权限、缺 extractor、需要人工修复等不会自动继续的业务阻断。
- CLI/API 已支持 `queue cancel <task_id>` / `POST /api/queue/<task_id>/cancel`，可取消尚未执行的 queued/waiting/blocked task；running task 当前只记录无法取消原因。`queue retry <task_id>` / `POST /api/queue/<task_id>/retry` 可把 failed/cancelled/blocked task 重置为 queued 并重新推进；`queue skip <task_id>` / `POST /api/queue/<task_id>/skip` 可把确认可忽略的 blocked/queued/waiting task 标记为 skipped，并自动释放依赖它的下游任务；`TaskEvent.max_attempts` 已支持执行失败后的队列内自动重试。
- 已新增 `TaskLogRepository`，`EventQueue` 会把 task registered/started/waiting/completed/failed/blocked/cancelled/retry 等状态变化写入 `var/process/task_logs/<task_id>.jsonl`；`queue show`/`GET /api/queue/<task_id>` 已返回 `logs`，前端可按 `task.type` 使用统一日志入口做差异化展示。
- 默认 pipeline run 已注册任务图：ingest step task -> `pipeline.combine_ingest` -> `classify.clustered_event_extraction` -> `classify.clustered_event_merge`，任务依赖由 `EventQueue` 推进；公开 `run start` CLI/API 不再提供旧同步端到端 runner fallback。`PipelineManager.on_task_blocked` 会把 blocked 回调转发给已注册 step，step 可据此安全跳过可选任务或注册替代任务。
- ingest 单步已支持 `ingest.run_step` task，可通过 CLI/API 单独运行并写入 run checkpoint。
- classify 已支持 `classify.clustered_event_extraction` 和 `classify.clustered_event_merge` 两个阶段 task；公开 classify CLI/API 入口已切到 `classify.clustered_pipeline`，旧 `classify.run_legacy` 仅作为低层 executor 兼容路径保留。
- managed web source 单源运行已通过 `web_source.run` task 执行，且 `skipped_unrepairable`、`repair_queued`、`repairing` 等不可直接继续状态会映射为统一 `TaskBlocked`/`task.blocked`。
- `CompletionCallbackRegistry` 已接入 bootstrap，`task.completed`/`task.failed`/`task.blocked` 的自动发布、payload patch、run 状态推进统一通过回调注册层绑定到 `EventRouter`；`queue status` 会返回已注册回调摘要。
- `CheckpointRepository` 已保证同一 `run_id`/`step_id`/`task_id` 的 artifact 与 `checkpoint.json` 写入同一个带 UTC 时间戳的目录，并补齐 `started_at`/`finished_at` 默认值。
- classify task 写统一 run checkpoint 时，已把 `news_with_events.json`、`events.json`、`discarded_news.json` 和 `classification_progress.json` 作为 checkpoint artifact 写入同一个时间戳任务目录；task resume 会优先读取 run checkpoint 里的 `classification_progress` artifact，找不到时再回退固定配置路径。固定 `output/` 文件仍保留为兼容发布结果。
- managed extractor registry 实现已迁入 `modnews/service/extraction/registry.py`；安装方式继续靠扫描 `extractors/*/current/manifest.json`。
- managed extractor contract、metadata、repair manager 实现已迁入 `modnews/service/extraction/`。
- Codex extractor repair 已接入统一队列：`repair create`/`repair retry` 会注册并执行 `TaskEvent(type="extractor.repair.codex")`，由 `EventQueue` 负责并发、blocked、重试和 task logs；原 repair task 记录继续作为工作目录、Codex 输出和 promote 结果仓储。
- managed web source contract、runner、repair policy、orchestrator 已迁入 `modnews/service/extraction/`；web job store 和 JSONL event helper 已迁入 `modnews/repository/`。
- `RuntimePaths`/`runtime_paths` 和核心数据模型 `NewsItem`、`EventRecord`、`StepResult`、`PipelineResult` 已迁入 `modnews/core/`。
- runtime/source config store 实现已迁入 `modnews/repository/runtime_config.py` 与 `modnews/repository/source_config.py`。
- `SourceConfigRepository` 已从单纯别名改为 source 领域 facade；`modnews sources` 已支持 `list`、`rss add`、`rss disable` 和 `site add`，Local/API source 修改走 repository 层。
- pipeline 配置 dataclass、`load_config`、`apply_runtime_overrides` 与 `PipelineContext` 已迁入 `modnews/core/config.py` 和 `modnews/core/context.py`。
- legacy progress bus 已迁入 `modnews/core/progress.py`，并会把 `emit(...)` 事件桥接到当前容器的 `EventRouter`（`progress` 与 `progress.<event_type>`）；后续还需要继续减少 classify 内部直接使用旧式 progress event 的地方。
- ingest base/stage 和 RSS、NewsNow、site_lists step 实现已迁入 `modnews/service/ingest/`。
- classify runtime、LLM client、retriever、checkpoint、clustered/event/relevance step 实现已迁入 `modnews/service/classify/`。
- classify 内部 batch/embedding 并发已集中到 `modnews/service/classify/batch_executor.py`；executor 现在带有 `task_type`、`concurrency_key`、batch index 和 labels 元数据，并定义了可替换 backend 协议。standalone 调用默认仍使用本地线程池；bootstrap 注册的 classify task 会注入 `EventQueueBatchExecutionBackend`，使 LLM batch 和 embedding batch item 注册成 `TaskEvent` 并通过统一队列收集结果。
- legacy pipeline runner 已迁入 `modnews/service/pipeline/legacy_runner.py`；内置 RSS/NewsNow seed 数据已迁入 `modnews/data/`。公开 run 入口不再暴露 legacy fallback，旧同步 runner 只保留给显式低层兼容路径。
- 顶层 `modnews` 包已停止导出旧同步 `run_pipeline`；旧同步 runner 只通过显式兼容路径 `modnews.service.pipeline.compat`/`legacy` 保留，避免把 legacy runner 误认为新主入口。
- `modnews_pipeline/` 兼容包已删除，wheel 只打包 `modnews`；安装后的主入口统一为 `modnews`、`modnews-server`、`modnews-report`，旧命令名 `newsagent-report` 仅作为指向同一 `modnews` report entry 的兼容别名保留。
- report 生成主实现已迁入 `modnews/service/report/pipeline.py`，并接入 `modnews report generate`、`modnews-report` 和 `newsagent-report` 入口；源码内 `src.main` 只保留为兼容转发壳。
- report 配置默认值、数据模型、utils、规则表、IO helper、evidence/editor/reporter 和分类/评分/摘要/核验 stages 已迁入 `modnews/service/report/`；`src.config`、`src.models`、`src.utils.*`、`src.rules.*`、`src.io.*` 与 `src.pipeline.*` 现在是兼容转发层，report 子模块已改用新路径。
- `OutputRepository` 已支持从 checkpoint `output_refs` 发布固定输出，CLI/API 可执行 `checkpoints publish`；关键 task 返回 `auto_publish_checkpoint` 时，`CompletionCallbackRegistry` 会在 `task.completed` 回调中自动发布固定输出。
- WebUI Progress 页已展示 runs、queue、checkpoints。

仍是兼容层的部分：

- 默认端到端 run 只注册任务图，不再提供公开 legacy fallback；但 ingest/classify 的具体业务 executor 仍有部分复用旧同步实现，后续要继续拆细。
- clustered classify 已拆到 extraction/merge 两个 task，但每个阶段内部仍复用现有 step 实现；batch relevance、embedding、LLM batch item 在队列执行 classify task 时已走 `EventQueueBatchExecutionBackend`，后续还需要把阶段级 executor 继续拆小，并把更细粒度的完成回调和 checkpoint 发布补齐。
- 任务执行期间的 progress/LLM 事件已通过当前 task 上下文写入 `TaskLogRepository`，`queue show` 可看到 `progress.llm_request_*` 等日志；Codex repair task 已把 `codex.jsonl` 路径、尾部摘要和字节数写入 task result，并通过 `progress.codex_repair_log` 进入 task logs；web extraction 的 `WebJobStore.append(...)` 事件也会以 `progress.web_job_event` 写入当前 task logs。
- legacy classify 自己的固定路径 `classification_progress.json` 仍存在，当前作为 standalone/旧入口 resume 兼容文件保留；新 task checkpoint 已在 run checkpoint 目录内保存同名 artifact，task 流程会优先使用 run checkpoint artifact。
- report 层已有 `modnews/service/report` facade、新 CLI 入口、主 pipeline 实现、配置默认值、模型、utils、规则表、IO helper、evidence、editor、reporter 和 stages；wheel 已不再发布 `src` 包，源码内 `src/` report 相关模块当前仅作为 repo 内兼容转发层保留，后续可在确认旧入口不再需要后删除。
- 固定输出已支持手动从 checkpoint 发布，也已支持关键 task 成功回调自动发布；后续要继续减少固定输出作为内部状态源的使用。

## Managed Extractors

根目录 `extractors/anthropic/current` 和 `extractors/huggingface_papers_trending/current` 已经是适合提交的形态，并且 `.gitignore` 已排除 `.agent_work/`。建议保留并正式注册安装：

- `extractors/<source_id>/current/extractor.py`
- `extractors/<source_id>/current/manifest.json`

注册方式建议只靠扫描目录，不维护统一 `registry.json`。`ExtractorRegistry` 扫描 `extractors/*/current/manifest.json`，只要目录内元数据完整且状态为 enabled，就视为已安装 extractor。

```text
extractors/
  anthropic/
    current/
      manifest.json
      extractor.py
  huggingface_papers_trending/
    current/
      manifest.json
      extractor.py
```

`manifest.json` 应包含完整元数据：

- `id`
- `name`
- `kind`
- `status`
- `version`
- `entrypoint`
- `target_url`
- `source_ids`
- `promoted_from_task`
- `created_at`
- `updated_at`
- `capabilities`
- `content_type`

如果 `extractor.py` 顶部还保留 `MODNEWS_EXTRACTOR` 注释元数据，应该把它作为兼容/校验信息；最终以目录内 `manifest.json` 为准。promote 时只更新对应 extractor 目录下的 `current/manifest.json` 和 `current/extractor.py`。`.agent_work/extractors/**` 继续作为生成和调试日志，不提交。

## 文件整理建议

### 已移动到 docs/

这些文档已经从根目录移到 `docs/`：

- `News PRD 38ad6fd653bd803bb463e1d3654c8bd2.md` -> `docs/prd.md`
- `信息源.md` -> `docs/sources.md`
- `新闻归类流程.md` -> `docs/classification_flow.md`
- `README.modnews.md` -> `docs/legacy_readme.md`

### 建议删除或改为未跟踪运行态

这些不应作为源码维护：

- `events(1).json`：已作为案例改名放入 `mock_data/events.sample.json`。
- 根目录 `output/`：运行输出，已在 `.gitignore`，不应提交新文件。
- 根目录 `runtime/`：运行配置，已在 `.gitignore`；保留 `config.example.json` 作为模板。
- 根目录 `var/`：缓存/checkpoint，已在 `.gitignore`。
- `.agent_work/`：managed Codex 工作目录，已在 `.gitignore`。
- 嵌套 `modnews/`：当前是历史运行目录，含 `.venv`、`.env.runtime`、输出和 pyc，应本地删除，不进仓库。

注意：根目录 Markdown 和 `events(1).json` 已用 `git mv` 清理；后续如果发现运行态文件被跟踪，也需要用 `git rm --cached` 明确处理，不能只依赖 `.gitignore`。

### 建议保留

- `mock_data/`：作为测试快照保留，但应区分 `snapshot` 和大型临时 mock API 数据。
- `mock_server.py`：如果仍用于 `NEWS_MODE=mock`，保留；后续可移动到 `tools/mock_server.py`。
- `config.example.json`、`config.bailian.example.json`：保留为配置模板，后续统一到 `examples/` 也可以。

## 迁移顺序

建议分五个小 PR/提交做，降低风险。

1. 文档和清理
   - 移动根目录 Markdown 到 `docs/`。
   - 删除 `events(1).json` 或移动成 sample。
   - 确认运行态目录都未跟踪。
   - 增加本建议文档。

2. 包名和入口兼容
   - 新建 `modnews/` 源码包。
   - 删除 `modnews_pipeline` 旧入口，所有 import 和命令入口迁移到 `modnews.*`。
   - `pyproject.toml` scripts 改为更通用名称，例如：
     - `modnews = "modnews.cli.main:main"`
     - `modnews-server = "modnews.app.server:main"`
     - `modnews-report = "modnews.cli.commands.report:main"`
   - 不再新增 `modnews-pipeline` 或 `modnews_pipeline` 兼容入口。

3. 建立 service 和 bootstrap 壳
   - 新建 `modnews/service/`，把 pipeline、ingest、classify、extraction 作为内部服务放进去。
   - 新建 `modnews/bootstrap/`，集中注册 pipeline step、task executor、event handler。
   - 先只做转发和注册，不移动大量业务实现。

4. 拆 Web 路由
   - 从 `web.py` 拆 blueprint。
   - `app/server.py` 创建 Flask app。
   - `app/router.py` 统一注册。
   - 先不改业务逻辑，只迁移函数位置。

5. 收敛 repository 和 checkpoint
   - 移动 runtime config/source config/output state/cache/job store/checkpoint 到 `repository/`。
   - 增加 `RunRepository` 和 `CheckpointManager`。
   - checkpoint 改为 `var/process/runs/<run_id>/checkpoints/<step>/<timestamp>/` 结构。
   - 固定输出路径由 `OutputRepository` 从最新成功 checkpoint 发布。
   - 路由层和 orchestrator 改为依赖 repository。
   - `sources/config_store.py` 改为兼容 facade，后续删除。

6. 统一事件队列和任务执行
   - 新增 `EventQueue`、`TaskEvent`、`TaskExecutorRegistry`。
   - 先让 ingest source 运行改成注册 task event，由事件系统执行。
   - 再把 classify batch/embedding/extract/merge 改成 task event。
   - 最后把 web extraction job 状态接入同一套 EventQueue、EventRouter、CheckpointManager。
   - 保留旧事件名兼容 SSE 前端，待 WebUI 迁移后再删除。

7. 建立完整 CLI
   - 新建 `modnews/cli/main.py` 和 `commands/` 分组。
   - 增加 `api_client.py` 和 `local_client.py`，保证不启动前端也能操作。
   - 先覆盖 config、events、queue、run、extractors、jobs、repair、outputs、cache、checkpoints。
   - 所有命令统一支持 `--format`，修改类命令支持 `--dry-run`。

## 需要重点验证的地方

- `python -m modnews.cli.main run start` 和 `modnews run start` 是主 pipeline CLI 入口；仓库中不再存在 `modnews_pipeline` 入口或兼容包。
- `modnews-server` 的 `/api/events` SSE 兼容现有 WebUI。
- 不启动前端和 server 时，CLI local 模式可以查询事件队列、修改配置、启动 run、查看 checkpoint。
- 启动 server 时，CLI API 模式和前端看到的状态一致。
- `runtime/config.json` 自动迁移和备份逻辑不丢用户配置。
- `extractors/anthropic/current`、`extractors/huggingface_papers_trending/current` 可以通过 registry 运行。
- classify resume checkpoint 在统一 run checkpoint 结构迁移后仍能恢复；必要时增加 checkpoint version/migration。
- 并发任务由 `EventQueue` 限制，不由 step 内部线程池各自控制。
- 必须顺序运行的任务只有在上一条任务完成回调后才注册下一条。
- 固定输出文件与 run checkpoint 可追溯对应。
- `modnews report generate`、`modnews-report` 和旧命令别名 `newsagent-report` 在同一输入下输出完全一致；`src/` 报告兼容层迁入/删除期间仍要保持源码兼容入口可转发到同一实现。

## 命名建议

推荐：

- Python 包：`modnews`
- CLI 主命令：`modnews`
- API 服务：`modnews-server`
- CLI API 地址参数：`--api-url`
- CLI 执行模式参数：`--mode auto|api|local`
- 旧包兼容：不保留；旧引用迁移到 `modnews.*`

避免继续把主程序叫 `modnews_pipeline`，因为现在它已经不只是 pipeline：它还包含 API server、runtime config、extractor registry、repair、job store 和报告桥接。

## 最小可落地第一步

第一步不要做大规模重构，建议只做：

1. 把文档移动到 `docs/`。
2. 删除或取消跟踪运行态文件。
3. 补齐现有 managed extractors 的目录内 `manifest.json` 元数据，并确认 registry 只靠扫描目录安装。
4. 新增 `modnews/` 包壳、`service/`、`bootstrap/`，并删除 `modnews_pipeline/` 旧入口。
5. 先定义 `TaskEvent`、`EventQueue`、`CheckpointManager` 接口，并用 adapter 包住现有同步实现。
6. 建立 `modnews/cli/` 骨架，先实现 `config show`、`events list/watch`、`queue status`、`run start/status` 的 local 模式。
7. 把 `web.py` 拆成 blueprint，但暂时保持原业务函数。

这样可以先把入口和项目形态整理出来，再逐步做 repository 和 flow 的实质收敛。
