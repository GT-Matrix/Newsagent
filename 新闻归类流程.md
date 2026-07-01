# 新闻归类流程

目标：把抓取到的新闻按“AI 核心事件”归类，输出 `news_with_events.json` 和 `events.json`。和 AI 无关、泛泛讨论、信息弱的新闻不进入最终事件，但会写入 `discarded_news.json` 方便排查。

## 总体链路

当前归类步骤是一个 LLM 驱动的 pipeline stage，不再使用 embedding 聚类。

1. 全量标题批判定
2. 疑似池正文复判
3. 候选事件召回
4. LLM 单条归并或新建事件
5. 事件级二次合并
6. 写出结果和丢弃记录

## 1. 全量标题批判定

所有新闻都会先给 LLM 看一遍，不做规则召回。

每批固定默认 `25` 条。标题判定阶段不依赖事件表，默认允许 `8` 个 batch 并发。

LLM 对每条标题输出：

```json
{
  "index": 0,
  "status": "candidate",
  "relevance_score": 90,
  "canonical_summary": "OpenAI发布新模型",
  "entities": ["OpenAI"],
  "event_type": "model",
  "reason": "标题明确描述AI模型发布"
}
```

`status` 只有三类：

- `candidate`：明确是高价值 AI 新闻，进入事件归并
- `suspect`：标题可能有价值，但仅凭标题无法确认，进入疑似池
- `discard`：非 AI、泛泛观点、低信息量内容，不进入事件

`event_type` 固定从以下值中选择，不允许自由生成：
`model`, `product`, `research`, `infrastructure`, `hardware`, `funding`, `partnership`, `policy`, `safety`, `security`, `open_source`, `company`, `acquisition`, `litigation`, `application`, `benchmark`, `other`.

## 2. 疑似池正文复判

`CLASSIFICATION_SUSPECT_MODE=discard` 时，`suspect` 新闻会直接丢弃，不抓原文。当前默认使用这个模式，方便先测试主分类链路。

`CLASSIFICATION_SUSPECT_MODE=article` 时，pipeline 会尝试拉取原文。

为了控制 token，只截取：

- 开头 200 字
- 中间 200 字
- 结尾 200 字

然后把标题、来源、URL 和这三段正文交给 LLM 复判。

复判结果只有：

- `candidate`：确认是 AI 核心新闻，送入事件归并
- `discard`：仍无法确认或价值不足，写入 `discarded_news.json`

如果原文拉取失败，也会写入丢弃记录，stage 标记为 `suspect_article_fetch`。

## 3. 候选事件召回

单条新闻进入事件归并前，程序先从当前已有事件中召回 top `5` 个候选事件。

召回不使用 LLM，也不看全部事件列表。当前使用本地向量检索：

- 用 `canonical_summary + title + entities + event_type` 生成新闻查询向量
- 用 `event_label + event_summary + key_entities + event_type + representative_titles` 生成事件向量
- 向量结果缓存到 `output/event_vector_cache.sqlite3`
- 默认只优先比较 `72` 小时窗口内事件

这一步只负责缩小范围，不做最终判断。

## 4. LLM 事件归并

每次只给 LLM 一条新闻和最多 `5` 个候选事件。

LLM 输出：

```json
{
  "decision": "assign",
  "matched_event_id": "evt_20260629_0001",
  "confidence": 0.92,
  "reason": "同一公司同一产品发布",
  "event_label": "OpenAI发布新模型",
  "event_summary": "OpenAI发布新一代模型并开放使用",
  "event_type": "model",
  "key_entities": ["OpenAI"]
}
```

`decision` 只有三类：

- `assign`：归入已有事件
- `create`：没有合适事件，新建事件
- `discard`：虽然提到 AI，但不是值得建事件的核心新闻

`confidence` 使用 `0.0` 到 `1.0` 的实际概率值，不使用百分比或 0-100 分数。

新建事件要求是具体事件，通常需要明确实体、产品、机构或政策。泛泛趋势、评论、热议类标题应该丢弃。

## 5. 事件级二次合并

顺序归并后，仍可能产生重复事件。

pipeline 会做两轮事件合并。每轮从上到下处理事件，被合并进其他事件的候选会跳过。

每个 seed event 用向量召回 top `5` 个相似事件，把 seed 和 5 个候选一起交给 LLM。LLM 只需要返回应该合并到 seed 的候选事件 ID。

LLM 输出：

```json
{
  "merge_event_ids": ["evt_20260629_0012", "evt_20260629_0044"],
  "reason": "这些事件都描述同一次模型发布"
}
```

只有确认是同一具体事件才合并；同公司、同赛道、同主题但不是同一件事，不合并。程序会过滤掉不在候选列表里的 event id。

## 6. 输出文件

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
CLASSIFICATION_SUSPECT_MODE=discard
CLASSIFICATION_BATCH_CONCURRENCY=8
SOURCE_LAB_PROXY=
```

`NEWS_MODE=mock` 只影响新闻来源抓取，会自动启动本地 mock server。LLM 分类始终走 `LLM_BASE_URL` 和 `LLM_API_KEY`，事件向量召回始终走 `EMBEDDING_BASE_URL` 和 `EMBEDDING_API_KEY`。

LLM 调用使用本地 SQLite 缓存：

```text
output/llm_classification_cache.sqlite3
```

缓存 key 包含任务名、模型、temperature 和完整 messages，保证重复运行时不会重复请求相同输入。
