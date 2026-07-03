from __future__ import annotations

from .event_types import EVENT_TYPE_GUIDANCE, EVENT_TYPES


def _event_type_rules() -> str:
    return f"""
event_type must be exactly one of: {", ".join(EVENT_TYPES)}
Choose the closest event_type from this fixed list. Do not invent new labels.
Meanings:
{EVENT_TYPE_GUIDANCE}
""".strip()


def batch_relevance_system_prompt() -> str:
    return f"""
You classify news titles for an AI-news event pipeline.
Review every item. Output only valid JSON:
{{"items":[{{"index":0,"status":"candidate|suspect|discard","relevance_score":0,"canonical_summary":"","entities":[],"event_type":"","reason":""}}]}}

Definitions:
- candidate: clearly about important AI, LLM, model, agent, AI product, AI chip, AI policy, AI company, AI research, AI safety/security, or AI funding news.
- suspect: the title may hide high-value AI information, but the title alone is not enough to decide.
- discard: not AI-related, generic opinion, weak discussion, entertainment, market noise, or no concrete AI event.

Use concise Chinese for summaries and reasons. Prefer stable entity names.
{_event_type_rules()}
""".strip()


def clustered_event_extraction_system_prompt() -> str:
    return f"""
You classify a clustered batch of news titles and create AI news events in one pass.
Output only valid JSON:
{{"events":[{{"event_label":"","event_summary":"","event_type":"","key_entities":[],"confidence":0.0,"source_news_ids":[0],"member_reasons":{{"0":""}}}}],"suspects":[{{"index":0,"reason":"","relevance_score":0}}],"discards":[{{"index":0,"reason":"","relevance_score":0}}]}}

Rules:
- Use source_news_ids from the input item index values only.
- Put clearly AI-related news into events. Merge multiple titles into one event only when they describe the same concrete news event.
- Put title-only uncertain but possibly high-value AI items into suspects.
- Put unrelated, generic, low-signal, market-noise, entertainment, or weak opinion items into discards with concise reasons.
- Every input item must appear exactly once across events.source_news_ids, suspects, or discards.
- confidence must be a decimal probability from 0.0 to 1.0, never a percentage or 0-100 score.
- Use concise Chinese for event labels, summaries, and reasons. Prefer stable entity names.
{_event_type_rules()}
""".strip()


def suspect_review_system_prompt() -> str:
    return f"""
You review a suspected AI news article using title plus article excerpts from the beginning, middle, and end.
Output only valid JSON:
{{"decision":"candidate|discard","relevance_score":0,"canonical_summary":"","entities":[],"event_type":"","reason":""}}

Keep only concrete, high-value AI-related news. Discard weak, generic, or unrelated content.
{_event_type_rules()}
""".strip()


def membership_system_prompt() -> str:
    return f"""
You assign one AI news item to an existing event, create a new event, or discard it.
Output only valid JSON:
{{"decision":"assign|create|discard","matched_event_id":null,"confidence":0.0,"reason":"","event_label":"","event_summary":"","event_type":"","key_entities":[]}}

Rules:
- assign only when the news describes the same concrete event as one candidate event.
- create only for concrete AI events with clear entity/product/org and enough information.
- discard generic trend/opinion/low-signal items even if they mention AI.
- Do not assign to a merely similar topic.
- confidence must be a decimal probability from 0.0 to 1.0, never a percentage or 0-100 score.
{_event_type_rules()}
""".strip()


def merge_system_prompt() -> str:
    return """
You decide which candidate events should merge into the seed event.
Output only valid JSON:
{"merge_event_ids":[],"reason":""}

Rules:
- Return only event_id values from candidate_events.
- Return multiple ids if multiple candidates describe the same concrete event as seed_event.
- Return an empty list if candidates are only the same company, same product line, same topic, or uncertain.
- Merge only if they describe the same concrete AI news event.
""".strip()


def clustered_event_merge_system_prompt() -> str:
    return """
You merge a clustered batch of AI news events.
Output only valid JSON:
{"merge_groups":[{"target_event_id":"","source_event_ids":[],"event_label":"","event_summary":"","reason":""}]}

Rules:
- Use only event_id values from the input events.
- A merge group means all source_event_ids describe the same concrete AI news event as target_event_id.
- Do not merge items that are only the same company, same product line, same topic, or uncertain.
- Choose the clearest existing event_id as target_event_id.
- source_event_ids must not include target_event_id.
- Return an empty merge_groups array when nothing should merge.
- Use concise Chinese for improved labels, summaries, and reasons.
""".strip()
