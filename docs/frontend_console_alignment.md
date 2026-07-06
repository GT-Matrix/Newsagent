# ModNews 前端联动重构清单

日期：2026-07-06

本文档基于两个代码库的当前状态整理：

- 后端：`/Users/zyf/Code/Projects/modnews`
- 前端：`/Users/zyf/Code/Projects/modnews_webUI`

目的不是重写前端设计，而是明确现在这个新前端已经具备什么能力、它和当前重构中的后端还差哪些关键接口与语义，以及后续每次后端重构时需要同步遵守的联动原则。

## 0. 当前判断

先给结论，避免后面讨论跑偏：

1. `modnews_webUI` 已经不是“后面再适配”的状态，而是已经接上了大部分运行控制能力。
2. 当前不需要重做一套前端信息架构，后续重构可以继续沿用这个前端仓库同步推进。
3. 接下来前后端联动的重点，不是补更多零散页面，而是把后端统一 step/task/checkpoint 语义继续收敛，让前端减少硬编码。

补一条这次重新查看代码后的判断：

4. `modnews_webUI` 现在已经同时消费了统一快照、统一 run 详情、统一 queue 接口，不再只是“后端旁边的一个演示台”。
5. 当前真正的联动断点，不是页面数量不够，而是前端仍保留了一部分旧 classify 事件视角，同时 `src/types/domain.ts` 还没完整吃进后端最近补上的统一任务详情字段。

结合 2026-07-06 的代码看，前端已经明确覆盖了这些后端能力：

- `RunsPage` 可启动 run、恢复 run、取消 run、查看 queue、发布 checkpoint、触发 classify、触发 report。
- `RunDrawer` 已能读取 `/api/runs/:id` 的 detail 读模型，展示 `pipeline_steps`、`callback_events`、`followups`、`checkpoints`、`artifacts`。
- `QueueTaskDrawer`、`TaskDrawer`、`CodexLogViewer` 已经把“按任务类型展示不同细节”的方向做出来了。
- `ReportsPage` 已支持基于 checkpoint 或产物继续生成 report。
- `useRuntimeSnapshot` 已经把 source / extractor / web job / repair / run / queue / checkpoint / outputs 聚合成统一运行态快照。
- `usePipelineProgress` 仍在同时消费 `/api/state` 和 `/api/events`，但它内部的 step 列表还是固定写死的。

所以，后续“带着前端一起改”应理解为：

- 后端每次收敛统一语义时，顺手保证前端读模型不退化。
- 当前端还写死旧分类步骤名或任务类型特判时，跟着后端重构一起收口。

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

另外，这页已经明显开始转向统一读模型：

- `RunDrawer` 直接消费 `/api/runs/:id` 的 `pipeline_steps / steps / checkpoints / artifacts`。
- queue 操作面已经围绕 `/api/queue`、`/api/queue/:id` 的统一任务对象工作。
- 每个关键动作都已经给了 CLI 对照命令，这意味着前后端语义已经不是只服务 WebUI。

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

### 2.2 report 已经进了 run graph，但前端仍同时保留“单独触发 report”的操作心智

这块和更早之前相比已经前进了一步。按当前后端代码和测试，默认 run 已经注册：

- `pipeline_ingest`
- `pipeline_combine_ingest`
- `pipeline_classify`
- `pipeline_report`

并且支持 `disable_report`，`disable_classification` 时也不会继续注册 report followup。

所以这里更准确的说法不是“report 还没进统一流程”，而是：

- report 已经是统一 run graph 的标准尾步骤之一。
- 但前端仍同时保留 `ReportsPage`、Runs 页里的独立 report 触发入口，因此用户心智上依然像“既可以随 run 自动走，也可以单独再来一次”。
- 后端下一步更需要统一的是 report 的任务详情 schema、checkpoint 恢复语义、以及它和分类产物之间的标准引用关系。

也就是说，report 的“是否在统一流程里”这个问题基本解决了，剩下的是“统一流程和单独操作面之间怎样共用同一套读模型”。

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

补充一个这次代码确认后的现实状态：

- 后端 `/api/queue` 读模型已经补了 `title / summary / log_kind / detail_kind / retry_state / blocked_state / related_* / attempt_history / domain_view`。
- 但 `modnews_webUI/src/types/domain.ts` 里的 `QueueTask` 仍只声明了较薄的一层字段。
- 所以前端现在是“接口能力已经先到了，类型和渲染层还没完全跟上”。

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

不过这里要注意一个现实判断：

- `RunDrawer` 已经能展示 step callback 和 changed task。
- `QueueTaskDrawer` 已能看 payload 和错误。
- `CodexLogViewer` 已能把 repair/codex 日志结构化显示。

也就是说，前端缺的已经不是“有没有地方展示”，而是后端还没有给出足够统一的 detail schema。

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

这句现在也要修正得更准确一些：

- 后端并不是完全没有统一任务详情 schema，而是 schema 已经开始成形。
- 当前缺口主要在于前端还没有全面消费 `log_kind / detail_kind / domain_view / attempt_history` 这些字段。
- 换句话说，下一阶段前后端联动的重点应从“后端先定义字段”切到“前端开始真正按字段分派详情视图”。

## 2.7 当前前端最值得保留的部分

后面继续重构时，下面这些前端能力应该保留并作为兼容目标，不要在后端收敛语义时把它们弄丢：

1. `RunDrawer` 对注册式 pipeline step 的详情展示
2. 队列任务的 `retry / skip / cancel / drain` 操作链路
3. checkpoint 的筛选、发布、作为 classify/report 输入
4. repair / codex 日志的专门展示器
5. artifact 预览抽屉和 CLI 对照命令

这些能力已经构成了“能操作、能排障、能恢复”的基本控制台，不应因为后端目录重构而退回成只能看列表。

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

### 3.5 前后端联动时优先改读模型，不优先改页面结构

下一阶段如果后端继续统一 classify / report / repair / web extraction，前端联动顺序建议固定为：

1. 先补统一 API 字段
2. 再适配 `src/types/domain.ts`
3. 最后才改页面表现

原因很简单：当前前端页面结构已经够用，真正不稳定的是后端对象语义。

## 4. 下一阶段联动工作项

按现在的后端状态，下一阶段前后端一起改，优先顺序建议如下。

### 4.1 优先项：统一任务详情 schema

目标：让前端可以真正按 `task.type` 动态选择日志和详情视图，而不是继续堆条件分支。

当前后端已经基本具备、但前端还未全面接入的字段包括：

- `id`
- `type`
- `title`
- `summary`
- `state`
- `attempts`
- `max_attempts`
- `blocked_reason`
- `retry_state`
- `step_id`
- `pipeline_run_id`
- `log_kind`
- `detail_kind`
- `artifacts`
- `related_source_id`
- `related_checkpoint_path`
- `related_run_id`
- `related_step_id`
- `related_artifacts`
- `attempt_history`
- `domain_view`

所以下一轮联动的重点，不是后端再凭空设计一版字段，而是：

1. 以后端现有 queue read model 为准收敛前端类型定义。
2. 让 `QueueTaskDrawer` 成为统一入口，再按 `detail_kind` 分派网页抓取、Codex 修复、分类批任务、report 任务的详情区块。
3. 保留 `WebJob`、`RepairTask` 页面，但把它们更多当作任务系统的领域投影视图。

### 4.2 优先项：统一 report 的 pipeline 规划语义

目标：让前端看到的 report，不再只是“额外动作”，而是 run graph 里的标准末端 step。

最少要补清楚：

- 默认 run 是否总是包含 report
- 是否支持显式关闭 report
- `disable_classification` 时 report 是否必然不注册
- report step 的状态、checkpoint、artifact 是否统一回到 run detail

### 4.3 第二优先级：减少前端对 classify 固定步骤名的依赖

当前 `usePipelineProgress.ts` 仍然偏旧分类事件视角，这部分后面应逐步改成：

- 基于后端返回的 step/task graph 动态渲染
- 不再把 `clustered_event_extraction`、`clustered_event_merge` 当固定产品概念写死

### 4.4 第二优先级：把 repair / web job 逐步变成统一任务系统的领域视图

不是删掉这些对象，而是把它们的位置摆正：

- 统一任务系统是主语义
- `WebJob` / `RepairTask` 是扩展详情投影

这样后面 classify 的异步子任务、爬虫任务、codex 修复任务才能在前端形成同一套观察方式。

## 5. 实施原则

后续继续重构时，前端联动按下面三条执行：

1. 后端新增统一字段时，同步更新 `modnews_webUI/src/types/domain.ts`
2. 后端替换旧语义时，优先保持 `/api/runs/:id`、`/api/queue`、`/api/checkpoints` 这些核心接口稳定
3. 只有当统一读模型已经稳定后，再考虑进一步调整页面结构或视觉层级

按这个方式推进，`modnews_webUI` 可以继续沿用，不需要因为这次架构收敛重新开一套前端。

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

这一步里有一个很具体的前端动作，应当优先落地：

- 把 `src/types/domain.ts` 中的 `QueueTask`、`PipelineTaskDetail` 扩成和后端 queue read model 对齐。
- 然后让 `QueueTaskDrawer` 优先展示统一字段，减少对 `WebJob` / `RepairTask` 专用抽屉的依赖。

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

但按这次重新核对代码后的结果，这里也要收紧一下表述：

- `step graph` 和 `task type` 详情 schema 已经有了第一版，至少 `/api/runs/:id` 和 `/api/queue` 不再是空壳。
- 真正还没完成的是前端从“旧事件推断视角”迁到“统一读模型视角”的最后一段路。

所以后续策略应当是：

- 保留这套前端；
- 后端继续按统一 step / task / checkpoint 架构收口；
- 每做完一块后端重构，就同步把对应页面从“旧事件推断视角”迁到“统一读模型视角”。
