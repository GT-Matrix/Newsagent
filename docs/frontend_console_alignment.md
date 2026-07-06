# ModNews 前端联动重构清单

日期：2026-07-06

本文档基于两个代码库的当前状态整理：

- 后端：`/Users/zyf/Code/Projects/modnews`
- 前端：`/Users/zyf/Code/Projects/modnews_webUI`

目的不是重写前端设计，而是明确现在这个新前端已经具备什么能力、它和当前重构中的后端还差哪些关键接口与语义，以及后续每次后端重构时需要同步遵守的联动原则。

## 1. 当前前端已经具备的能力

新前端已经不是简单配置页集合，而是一个基本可用的运维控制台。

一级页面已经固定为六块：

1. `Overview`
2. `Runs`
3. `Sources`
4. `Agents`
5. `Reports`
6. `Settings`

从现有代码看，前端已经覆盖了这些能力：

### 1.1 Overview

- 汇总最近 run、队列状态、输出完整度、异常任务数。
- 根据 `combined_news / events / report` 是否存在，给出下一步建议动作。
- 展示 RSS、NewsNow、网页源的有效覆盖数。

这说明前端已经有“控制台首页”的形态，不再只是来源配置入口。

### 1.2 Runs

- 启动完整 run。
- 选择只跑部分 ingest source。
- 选择只采集不分类。
- 查看最近 run，支持 `resume / cancel`。
- 查询队列任务，支持 `retry / cancel / skip / drain`。
- 浏览 checkpoint，支持按 `run / step / status` 过滤。
- 从 UI 直接触发 `classify run` 和 `report generate`。
- 通过 `/api/events` 和 `/api/state` 显示运行事件。
- 每个关键动作都配了 CLI 对照命令。

这部分已经具备运维台的骨架。

### 1.3 Sources

- 统一管理 RSS、NewsNow、网页源。
- 展示“下次运行是否会参与”的有效性判断。
- 支持批量启停。
- 支持网页源新建、编辑、删除、绑定 extractor、直接运行。
- 可编辑 `steps.site_lists.sites` 白名单。

这说明前端已经把“source 配置”和“运行有效性”部分结合起来了。

### 1.4 Agents

- 展示 extractor 注册表。
- 展示 web job 列表。
- 展示 Codex repair task 列表。
- 支持 extractor 启停、运行、删除。
- 支持 repair task 的创建、重试、promote、删除。
- 支持打开任务细节和日志。

这块已经形成了“网页抓取执行能力 + 修复能力”的专门工作台。

### 1.5 Reports

- 允许直接生成 report。
- 支持从 `events`、分类 checkpoint、最近 checkpoint 里选输入。
- 支持预览 Markdown / JSON 类输出。
- 已经把 report 产物和采集/分类产物分开展示。

这说明 report 层已经有独立操作面，不再只是 CLI 附属能力。

### 1.6 Settings

- 展示 runtime 配置。
- 展示环境健康信息。
- 展示只读路径与诊断信息。
- 提供配置修改前后的差异确认。

这块已经具备比较完整的运行时配置控制面。

## 2. 当前前端和目标架构的主要差距

虽然前端能力已经不弱，但它依赖的后端语义还没有完全对齐到你要的重构目标。

### 2.1 Runs 页仍然偏“旧 classify 事件视角”

`usePipelineProgress.ts` 里仍然写死了这类步骤：

- `start_checkpoint`
- `clustered_event_extraction`
- `clustered_event_merge`
- `outputs`

这说明它目前仍主要围绕“分类过程事件”来建模，而不是围绕统一 step registry 和统一任务系统来建模。

目标上应该改成：

- 前端不写死 classify 特有步骤名。
- 后端返回统一的 `run graph / step graph / task graph` 结构。
- 前端根据结构动态渲染 step，而不是硬编码当前有哪些步骤。

### 2.2 前端能操作 report，但 report 还不是统一 run graph 的标准尾步骤

现在 Reports 页和 Runs 页都能单独触发 `report generate`，这很好。

但从架构上看，report 仍然更像“独立动作”，不是 pipeline 默认末端 step 的统一表现。

因此前端现在看到的是：

- 先 run
- 再 classify
- 再 report

而不是一个统一 run 内部自然完成：

- `pipeline_ingest`
- `pipeline_combine_ingest`
- `pipeline_classify`
- `pipeline_report`

这会导致前端的 run 视图和 report 视图仍是分裂的。

### 2.3 Agents 页仍然同时面对三套任务语义

当前前端里至少并行存在三类对象：

- `QueueTask`
- `WebJob`
- `RepairTask`

这在展示上是合理的，但在后端语义上仍没有完全收平：

- 网页抓取是异步任务。
- repair/codex 修复是异步任务。
- classify 内部 LLM / embedding / batch merge 也是异步任务。

目标应该是：

- 这些都先统一落到任务系统。
- 前端再按 `task.type` 选择不同详情视图。
- `WebJob`、`RepairTask` 更像是某些任务类型的领域投影视图，而不是平行于队列系统的另一套主语义。

### 2.4 blocked / retry / callback 还没有形成统一可观察模型

你要求的目标是：

- blocked 由任务系统统一判定和落库。
- 重试由任务系统统一处理。
- step 收到 blocked 回调后可安全跳过。
- 不同任务类型展示不同日志样式。

当前前端虽然已经有失败任务、blocked repair task、queue retry/skip/cancel 的操作面，但缺少统一模型：

- 看不到某个 step 因哪个 task blocked 而停住。
- 看不到 blocked 回调后 step 是“跳过继续”还是“等待人工”。
- 看不到某个任务的自动重试历史和最终决策。
- 看不到 step 和 task 之间的因果关系图。

### 2.5 checkpoint 已经可用，但还没完全变成“统一恢复入口”

前端已经支持：

- 列 checkpoint
- 发布 checkpoint
- 把 checkpoint 当 classify/report 输入

但目标上还应该更进一步：

- 每个 step 输出目录都作为标准恢复单元。
- 同时支持传目录和 `checkpoint.json`。
- 前端展示 checkpoint 对应的 `input refs / output refs / callback result / blocked summary`。
- run 恢复时不要求用户自己理解 classify 内部文件名。

### 2.6 前端还看不到真正的统一任务日志分层

现在前端已经有：

- queue 详情抽屉
- web job 抽屉
- repair task 日志
- codex log viewer

但是还没做到：

- `web_source.run` 用网页抓取日志视图
- `extractor.repair.codex` 用 Codex 日志视图
- `classify.embedding` 用 embedding 请求汇总视图
- `classify.batch_relevance` / `classify.clustered_event_merge.batch` 用 LLM batch 视图

也就是前端组件已经准备出雏形，但后端还缺一个统一的“任务详情 schema”。

## 3. 对后续后端重构的约束

后面继续改后端时，不能只考虑 Python 目录结构，还要同时满足下面这些联动约束。

### 3.1 新能力必须优先落在统一 API 语义上

如果后端把流程进一步统一到 step registry 和任务系统，前端应该优先消费这些统一接口，而不是继续追加某个模块的专用接口。

优先级应是：

1. 统一 run / step / task 读模型
2. 统一 checkpoint / artifact 读模型
3. 特定领域详情接口作为补充

而不是继续增长更多平行 API。

### 3.2 前端页面应尽量围绕统一对象工作

后续联动时，页面应逐步收敛到下面几类核心对象：

- `Run`
- `Step`
- `Task`
- `Checkpoint`
- `Artifact`
- `Source`

`WebJob`、`RepairTask`、`ExtractorDetail` 可以保留，但最好作为这些核心对象的扩展详情，而不是独立维护第二套主模型。

### 3.3 新任务类型必须带展示元数据

如果后端新增统一任务类型，建议每个任务类型都带最少这类前端展示元数据：

- `task_type`
- `title`
- `summary`
- `log_kind`
- `detail_kind`
- `related_run_id`
- `related_step_id`
- `related_source_id`
- `related_artifacts`
- `retry_state`
- `blocked_state`

这样前端才能在不写死业务细节的情况下渲染对应抽屉和日志视图。

### 3.4 step 不再隐藏内部实际执行过程

你现在的方向是对的：

- step 只负责判断注册哪些任务
- 任务系统负责并发、blocked、重试、日志
- step 只接收完成/失败/blocked 回调

这对前端也有直接价值，因为它能让 Runs 页真正展示：

- 这个 step 注册了哪些任务
- 哪些任务还在跑
- 哪些任务 blocked 后被跳过
- 这个 step 最后为什么完成

## 4. 建议增加的统一后端读模型

为减少前端继续绑死旧语义，建议后面逐步补齐下面这些统一接口或字段。

### 4.1 Run 详情中补 step graph

建议 `/api/runs/<run_id>` 最终稳定包含：

- `run`
- `steps[]`
- `tasks[]`
- `checkpoints[]`
- `artifacts[]`
- `latest_events[]`

其中 `steps[]` 至少应包含：

- `step_id`
- `status`
- `depends_on`
- `queued_task_ids`
- `completed_task_ids`
- `blocked_task_ids`
- `skipped_task_ids`
- `latest_checkpoint`

这样 Runs 页就不需要再从 SSE 事件里推断状态。

### 4.2 Queue task 详情中补领域投影

建议 `/api/queue/<task_id>` 最终补齐：

- `task`
- `attempt_history`
- `blocked_reason`
- `callbacks`
- `artifacts`
- `domain_view`

其中 `domain_view` 可按类型返回：

- web source task: 绑定 `web_job`
- repair codex task: 绑定 `repair_task`
- classify task: 绑定 batch 信息、llm/embedding 统计
- report task: 绑定 report 输入和输出产物

### 4.3 Checkpoint 详情中补结构化引用

目前 checkpoint 列表已经够用，但后面最好再补：

- `input_refs`
- `output_refs`
- `task_refs`
- `resume_hint`
- `callback_summary`

这样前端可以直接给出：

- 从这里恢复 classify
- 从这里生成 report
- 重新发布这里的输出

而不是让用户理解底层文件命名。

## 5. 当前建议的联动重构顺序

后面如果继续做架构收口，我建议按这个顺序做，并同步带前端一起改。

### 第一阶段：先把 run/step/task 读模型补齐

目标：

- 不再让前端从事件流推断主状态。
- Runs 页改为以 run 详情和队列详情为主，SSE 只做增量刷新。

这一步完成后，前端就能开始摆脱 classify 特有事件名。

### 第二阶段：把 report 正式并入统一 step graph

目标：

- 最近 run 详情里能直接看到 report step。
- Overview 的“建议下一步”不再依赖多个散落输出文件自己猜。

### 第三阶段：把 task 日志视图按 `task.type` 统一

目标：

- queue task 抽屉成为统一入口。
- web job / repair task / classify batch 作为 task 的不同 detail renderer。

这样前端的 Agents 和 Runs 才会真正收敛到同一个任务系统。

### 第四阶段：把 checkpoint 恢复做成标准工作流

目标：

- 前端直接展示“目录恢复”和“checkpoint.json 恢复”。
- classify / report / pipeline 都走统一恢复语义。

## 6. 结论

新的 `modnews_webUI` 已经具备继续联动重构的基础，不需要推倒重来。

它目前最有价值的地方是：

- 信息架构已经重新整理过；
- CLI 对照已经铺得比较完整；
- Runs / Sources / Agents / Reports 四块都已经有实际操作能力。

它当前最大的结构性短板不是前端界面本身，而是后端还没有完全提供统一的：

- step graph
- task graph
- blocked/retry/callback 语义
- task type 详情 schema

所以后续策略应当是：

- 保留这套前端；
- 后端继续按统一 step / task / checkpoint 架构收口；
- 每做完一块后端重构，就同步把对应页面从“旧事件推断视角”迁到“统一读模型视角”。
