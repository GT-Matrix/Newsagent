# 新闻归类流程

目标：把抓取到的新闻按“AI 核心事件”归类，输出 `news_with_events.json` 和 `events.json`。和 AI 无关、泛泛讨论、信息弱的新闻不进入最终事件，但会写入 `discarded_news.json` 方便排查。

## 总体链路

当前归类步骤是一个 LLM 驱动的 pipeline stage，围绕标题聚类抽取和事件聚类合并两段任务运行。

1. 标题聚类抽取
2. 事件级候选召回与二次合并
3. 写出结果和丢弃记录

## 1. 标题聚类抽取

程序会先按 embedding 把标题聚成一批一批的局部簇，再把每个簇交给 LLM 一次性抽取事件、疑似项和丢弃项。

标题聚类抽取阶段使用 `batch_size` 和 `batch_concurrency` 控制批大小和并发量。

LLM 对每个簇输出：

```json
{
  "index": 0,
  "events": [],
  "suspects": [],
  "discards": []
}
```

抽取结果里：

- `events`：要创建的事件，以及各自的 `source_news_ids`
- `suspects`：仅凭标题仍不确定的新闻
- `discards`：直接丢弃的新闻和原因

当前主链路里不会再进入“抓正文再复判”的二级分支；`suspect` 会直接进入丢弃记录。

## 2. 事件级候选召回与二次合并

事件进入合并前，程序先从当前已有事件中召回候选事件。

召回不使用 LLM，也不看全部事件列表。当前使用本地向量检索：

- 用事件文本生成查询向量
- 用 `event_label + event_summary + key_entities + event_type + representative_titles` 生成事件向量
- 向量结果缓存到 `output/event_vector_cache.sqlite3`
- 默认只优先比较 `72` 小时窗口内事件

然后 pipeline 做事件级二次合并。每轮从上到下处理事件，被合并进其他事件的候选会跳过。

每个 seed event 用向量召回 top `5` 个相似事件，把 seed 和 5 个候选一起交给 LLM。LLM 只需要返回应该合并到 seed 的候选事件 ID。

LLM 输出：

```json
{
  "merge_event_ids": ["evt_20260629_0012", "evt_20260629_0044"],
  "reason": "这些事件都描述同一次模型发布"
}
```

只有确认是同一具体事件才合并；同公司、同赛道、同主题但不是同一件事，不合并。程序会过滤掉不在候选列表里的 event id。

## 3. 输出文件

分类 stage 写出三个文件：

- `output/news_with_events.json`：所有新闻及其分类字段
- `output/events.json`：最终事件列表
- `output/discarded_news.json`：丢弃记录和原因
- `output/classification_progress.json`：中间进度快照，包含当前阶段、items、events、discarded

`NewsItem` 会追加这些中间字段：

- `is_ai_relevant`
- `relevance_score`
- `canonical_summary`
- `entities`
- `event_type`
- `classification_decision`
- `classification_reason`

`EventRecord` 会追加：

- `event_summary`
- `event_type`
- `key_entities`
- `source_news_ids`
- `last_llm_updated_at`

## 运行配置

运行环境变量保持简单：

```bash
NEWS_MODE=mock
LLM_MODEL=qwen-plus
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_API_KEY=
CLASSIFICATION_BATCH_CONCURRENCY=8
SOURCE_LAB_PROXY=
```

`NEWS_MODE=mock` 只影响新闻来源抓取，会自动启动本地 mock server。LLM 分类始终走 `LLM_BASE_URL` 和 `LLM_API_KEY`，事件向量召回始终走 `EMBEDDING_BASE_URL` 和 `EMBEDDING_API_KEY`。

LLM 调用使用本地 SQLite 缓存：

```text
output/llm_classification_cache.sqlite3
```

缓存 key 包含任务名、模型、temperature 和完整 messages，保证重复运行时不会重复请求相同输入。
