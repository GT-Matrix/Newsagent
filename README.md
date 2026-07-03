# NewsAgent

NewsAgent is an AI news pipeline with three layers:

1. Ingest RSS, NewsNow, and managed web extractors into normalized news items.
2. Cluster and classify AI-related items into event records.
3. Run the report layer through `modnews report generate` to score, verify, section, summarize, and generate the daily report.

## Pipeline

```text
runtime/config.json
  -> RSS / NewsNow / managed web extractors
  -> output/combined_news.json
  -> modnews/service/report
  -> data/output/daily_report.md
```

Papers are modeled as normal sources with `content_type=paper`. There is no separate arXiv attach stage.

## Configuration

Runtime source and step settings live in `runtime/config.json` and are editable from the WebUI. Secrets and model endpoints stay in environment variables:

```bash
LLM_MODEL=...
LLM_BASE_URL=...
LLM_API_KEY=...
EMBEDDING_MODEL=...
EMBEDDING_BASE_URL=...
EMBEDDING_API_KEY=...
NEWS_MODE=real
```

The backend loads env from `MODNEWS_ENV_FILE`, `.env.runtime`, or the legacy `modnews/.env.runtime` path.

## Run

```bash
python -m modnews.cli.main run start
python -m modnews.cli.main report generate --input output/combined_news.json --date 2026-07-02
```

## Outputs

```text
output/combined_news.json
output/news_with_events.json
output/events.json
output/discarded_news.json

data/output/daily_report.md
data/output/daily_report_debug.md
data/output/enriched_events.json
data/output/evidence_events.json
data/output/report_candidates.json
data/output/review_candidates.json
```

## Web Extraction

Managed extractors live under `extractors/<source_id>/current/`. Agent work directories and logs live under `.agent_work/` and are not committed.

Current committed extractors:

- `anthropic`
- `huggingface_papers_trending`

## 中文使用说明

下面这一段只写日常最常用的 CLI 用法。默认都在项目根目录执行。

### 1. 从头完整跑一遍

前台完整运行一轮：

```bash
python -m modnews.cli.main --mode local run start --foreground
```

只跑部分 ingest source：

```bash
python -m modnews.cli.main --mode local run start --foreground --only rss
python -m modnews.cli.main --mode local run start --foreground --only rss --only newsnow
```

只抓取，不做 classify：

```bash
python -m modnews.cli.main --mode local run start --foreground --disable-classify
```

说明：

- `--foreground` 适合本地直接跑完整流程
- 当前 `local` 模式下，后台队列是进程内存态，跨进程恢复能力有限，所以本地完整跑建议优先用前台模式

### 2. 查看 run 状态

查看所有 run：

```bash
python -m modnews.cli.main --mode local run list
```

查看某个 run 的状态：

```bash
python -m modnews.cli.main --mode local run status 20260703T162738-main
```

查看当前整体状态：

```bash
python -m modnews.cli.main --mode local run status
```

### 3. 从已有 checkpoint 往后继续

如果上一轮已经完成了抓取或 classify 中间步骤，不想重复抓取，推荐直接从已有 checkpoint 产物继续，而不是重新 `run start`。

#### 3.1 从已有 classify checkpoint 继续 merge

如果某个 run 已经跑完 ingest，继续 classify 时不需要自己找具体 JSON，下面几种输入都支持：

- `__combined_ingest__`
- 上一步输出目录
- 上一步的 `checkpoint.json`

最短写法：

```bash
python -m modnews.cli.main --mode local --format json classify run --run-id 20260703T162738-main --input __combined_ingest__
```

也可以直接传 combine_ingest 的输出目录：

```bash
python -m modnews.cli.main --mode local --format json classify run \
  --run-id 20260703T162738-main \
  --input var/process/runs/20260703T162738-main/checkpoints/pipeline/combine_ingest/20260703T082805Z-pipeline-20260703T162738-main-combine-ingest
```

或者直接传 combine_ingest 的 `checkpoint.json`：

```bash
python -m modnews.cli.main --mode local --format json classify run \
  --run-id 20260703T162738-main \
  --input var/process/runs/20260703T162738-main/checkpoints/pipeline/combine_ingest/20260703T082805Z-pipeline-20260703T162738-main-combine-ingest/checkpoint.json
```

这条命令会：

- 通过 `run_id` 找到这个 run 下最新的 `classification_progress` checkpoint
- 从 checkpoint 恢复 classify 状态
- 继续执行后续 classify 步骤

不会重复做 ingest。

#### 3.2 直接从上一步输出继续生成 report

现在 `report generate` 支持以下几种输入：

- `classification_progress.json`
- classify 输出目录
- classify 的 `checkpoint.json`
- `combined_news.json`

```bash
python -m modnews.cli.main --mode local report generate \
  --input var/process/runs/20260703T162738-main/checkpoints/classify/clustered_event_merge/20260703T085238Z-classify-20260703T162738-main-clustered-event-merge \
  --output-dir data/output
```

如果你更习惯显式传 `checkpoint.json`：

```bash
python -m modnews.cli.main --mode local report generate \
  --input var/process/runs/20260703T162738-main/checkpoints/classify/clustered_event_merge/20260703T085238Z-classify-20260703T162738-main-clustered-event-merge/checkpoint.json \
  --output-dir data/output
```

如果要用 LLM 做 report polish 和趋势总结，再加配置文件：

```bash
python -m modnews.cli.main --mode local report generate \
  --input var/process/runs/20260703T162738-main/checkpoints/classify/clustered_event_merge/20260703T085238Z-classify-20260703T162738-main-clustered-event-merge \
  --output-dir data/output \
  --config config.example.json
```

#### 3.3 发布某个 checkpoint 对应的输出文件

把 checkpoint 里的产物重新发布到 `output/`：

```bash
python -m modnews.cli.main --mode local checkpoints publish /abs/path/to/checkpoint.json
```

列出某个 run 下的 checkpoints：

```bash
python -m modnews.cli.main --mode local checkpoints list --run 20260703T162738-main
```

### 4. 单独执行某个步骤

只跑某个 ingest step：

```bash
python -m modnews.cli.main --mode local ingest run rss
python -m modnews.cli.main --mode local ingest run newsnow
python -m modnews.cli.main --mode local ingest run site_lists
```

只跑 classify：

```bash
python -m modnews.cli.main --mode local classify run --run-id my-run --input output/combined_news.json
```

也可以直接传上一步目录或 `checkpoint.json`：

```bash
python -m modnews.cli.main --mode local classify run --run-id my-run --input var/process/runs/<run_id>/checkpoints/pipeline/combine_ingest/<step-dir>
python -m modnews.cli.main --mode local classify run --run-id my-run --input var/process/runs/<run_id>/checkpoints/pipeline/combine_ingest/<step-dir>/checkpoint.json
```

只跑 report：

```bash
python -m modnews.cli.main --mode local report generate --input output/combined_news.json
```

或者：

```bash
python -m modnews.cli.main --mode local report generate --input var/process/classification_progress.json
```

也可以：

```bash
python -m modnews.cli.main --mode local report generate --input var/process/runs/<run_id>/checkpoints/classify/<step-dir>
python -m modnews.cli.main --mode local report generate --input var/process/runs/<run_id>/checkpoints/classify/<step-dir>/checkpoint.json
```

### 5. 用 CLI 查看任务队列和进度

查看队列状态：

```bash
python -m modnews.cli.main --mode local queue status
```

列出队列任务：

```bash
python -m modnews.cli.main --mode local queue list
python -m modnews.cli.main --mode local queue list --state queued,running,waiting,blocked
```

查看单个任务详情：

```bash
python -m modnews.cli.main --mode local queue show <task_id>
```

查看最近事件：

```bash
python -m modnews.cli.main --mode local events list --limit 100
```

### 6. 用 CLI 修改运行时配置

查看当前运行时配置：

```bash
python -m modnews.cli.main --mode local config show
```

修改分类并发：

```bash
python -m modnews.cli.main --mode local config set classification.batch_concurrency 15
```

关闭某个 step：

```bash
python -m modnews.cli.main --mode local config set steps.newsnow.enabled false
```

修改 site list 站点列表：

```bash
python -m modnews.cli.main --mode local config set steps.site_lists.sites '["anthropic","huggingface_papers_trending"]'
```

修改单站抓取上限：

```bash
python -m modnews.cli.main --mode local config set steps.site_lists.limit_per_site 10
```

只做预览，不真正写入：

```bash
python -m modnews.cli.main --mode local config set classification.batch_concurrency 20 --dry-run
```

说明：

- `config set` 会自动尝试解析 JSON
- 所以布尔值、数字、数组、对象都可以直接传
- 运行时配置主要落在 `runtime/config.json`
- 模型地址、API Key、`NEWS_MODE` 这类仍然走环境变量，不走 `config set`

### 7. 常看输出文件

分类主输出：

```text
output/combined_news.json
output/news_with_events.json
output/events.json
output/discarded_news.json
var/process/classification_progress.json
```

report 输出：

```text
data/output/daily_report.md
data/output/daily_report_debug.md
data/output/enriched_events.json
data/output/evidence_events.json
data/output/report_candidates.json
data/output/review_candidates.json
data/output/trend_summary.json
```

run 级 checkpoint 目录：

```text
var/process/runs/<run_id>/checkpoints/
```

### 8. 当前推荐的本地使用方式

如果只是本机直接跑，推荐这两种：

1. 从头完整跑：

```bash
python -m modnews.cli.main --mode local run start --foreground
```

2. 某一轮 ingest 已经跑完后，从 classify/report 继续：

```bash
python -m modnews.cli.main --mode local --format json classify run --run-id <run_id> --input __combined_ingest__
python -m modnews.cli.main --mode local report generate --input var/process/runs/<run_id>/checkpoints/classify/<step-dir>
```

如果要长期查询任务进度、跨进程查看队列，建议启 API server 后用 `--mode api`。
