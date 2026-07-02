# NewsAgent

## 中文说明

NewsAgent 是一个 AI 新闻情报早报流水线，用于抓取新闻、事件聚类、论文挂载、历史去重、评分核验和生成中文早报。

## 整体流程

1. 抓取新闻源：RSS、NewsNow、站点列表、arXiv。
2. 使用标题向量聚类，再让 LLM 批量抽取事件。
3. 合并重复事件，并保留 `first_pubtime` 和 `latest_pubtime`。
4. 使用 `output/event_history.json` 做跨天历史去重。
5. 报告层完成分层、评分、核验、摘要和中文早报生成。

```text
sources / RSS / site lists / arXiv
  -> modnews_pipeline ingest and normalize
  -> title vector clustering + LLM event extraction
  -> event merge + history dedupe + paper attach
  -> output/combined_news.json
  -> src report layer
  -> data/output/daily_report.md
```

## 目录结构

```text
modnews_pipeline/        ingest, clustering, classification, paper attach, history dedupe
src/                     report layer: sectioning, scoring, verification, summarization
mock_data/               local mock data
config.example.json      public config template
config.bailian.example.json
config.local.json        local private config, ignored by git
output/                  upstream output, ignored by git
data/output/             report output, ignored by git
```

## 主要能力

- 多源新闻抓取：RSS、NewsNow、站点列表等。
- AI 新闻事件聚类：标题向量聚类 + LLM 批量抽取。
- 并发优化：默认 `batch_size=40`、`batch_concurrency=20`。
- 论文接入：从 arXiv 抓取近期 AI 论文，并判断是否挂到已有事件。
- 跨天去重：已报道过的重复事件默认不进早报。
- 时间字段：同时保留最早时间 `first_pubtime` 和最新时间 `latest_pubtime`。

## 本地配置

复制示例配置后填写自己的 API Key：

```powershell
Copy-Item config.example.json config.local.json
```

需要重点配置：

```json
{
  "classification": {
    "batch_size": 40,
    "batch_concurrency": 20,
    "llm": {
      "model": "YOUR_MODEL",
      "base_url": "https://example.com/v1",
      "api_key": "YOUR_LLM_API_KEY"
    },
    "embedding": {
      "model": "YOUR_EMBEDDING_MODEL",
      "base_url": "https://example.com/v1",
      "api_key": "YOUR_EMBEDDING_API_KEY"
    }
  },
  "paper_attach": {
    "enabled": true,
    "source": "arxiv",
    "limit": 40
  },
  "history_dedupe": {
    "enabled": true,
    "history_path": "output/event_history.json",
    "lookback_days": 14,
    "similarity_threshold": 0.72
  }
}
```

注意：不要提交 `config.local.json`，里面通常包含真实密钥。

## 运行方式

如果切换了新分类流程，建议先删除旧 checkpoint：

```powershell
Remove-Item output/classification_progress.json
```

运行上游抓取、聚类、论文挂载和历史去重：

```powershell
python -m modnews_pipeline.cli --config config.local.json
```

生成中文早报：

```powershell
python -m src.main --input output/combined_news.json --date 2026-07-02 --config config.local.json
```

只测试抓取，不跑分类：

```powershell
python -m modnews_pipeline.cli --config config.local.json --disable-classify
```

## 主要输出

```text
output/combined_news.json
output/news_with_events.json
output/events.json
output/discarded_news.json
output/arxiv_papers.json
output/paper_attach_decisions.json
output/event_history.json

data/output/daily_report.md
data/output/daily_report_debug.md
data/output/enriched_events.json
data/output/evidence_events.json
data/output/report_candidates.json
data/output/review_candidates.json
```

## 历史去重逻辑

每天跑完后，系统会把非重复事件写入 `output/event_history.json`。后续日期如果出现相似事件，会标记：

```json
{
  "is_duplicate": true,
  "duplicate_of_event_id": "evt_20260701_0001",
  "first_seen_date": "2026-07-01"
}
```

报告层读取 `combined_news.json` 时会默认跳过 `is_duplicate=true` 的事件。

## 论文处理逻辑

论文模块位于 `modnews_pipeline/papers/`。当前支持 arXiv：

- 抓取近期 AI 论文。
- LLM 判断论文是挂到已有事件、创建新研究事件，还是跳过。
- `paper` 和 `arxiv` 会归一化为 `research`，默认进入“研究与评测”候选。

## 注意事项

- `linux_do` 当前建议关闭，容易被 Cloudflare 或网络环境拦截。
- 如果 LLM 服务返回 `503`，一般是服务端繁忙或模型不可用，可以稍后重跑。
- `output/`、`data/output/`、`config.local.json` 不会提交到 GitHub。
