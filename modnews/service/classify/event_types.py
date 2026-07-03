from __future__ import annotations


EVENT_TYPES = (
    "model",
    "product",
    "research",
    "infrastructure",
    "hardware",
    "funding",
    "partnership",
    "policy",
    "safety",
    "security",
    "open_source",
    "company",
    "acquisition",
    "litigation",
    "application",
    "benchmark",
    "other",
)

DEFAULT_EVENT_TYPE = "other"

EVENT_TYPE_DESCRIPTIONS = {
    "model": "model release, model update, model capability, or model access change",
    "product": "AI product, feature, tool, app, service, or product update",
    "research": "AI research paper, technical method, lab result, or scientific breakthrough",
    "infrastructure": "AI infrastructure, cloud, data center, developer platform, or deployment stack",
    "hardware": "AI chip, accelerator, robotics hardware, device, or hardware supply chain",
    "funding": "funding, investment, IPO, grant, revenue, or financial performance",
    "partnership": "partnership, integration, customer deal, ecosystem collaboration, or joint launch",
    "policy": "AI regulation, government policy, standards, export controls, or public-sector action",
    "safety": "AI safety, alignment, evals, risk, misuse prevention, or responsible AI governance",
    "security": "AI cybersecurity, vulnerability, privacy, data leak, abuse, or security incident",
    "open_source": "open-source model, dataset, framework, tool, or community release",
    "company": "company strategy, hiring, reorganization, leadership, legal entity, or operations",
    "acquisition": "acquisition, merger, asset purchase, or acquihire",
    "litigation": "lawsuit, copyright case, antitrust case, settlement, or legal ruling",
    "application": "AI use case, enterprise deployment, industry application, or implementation result",
    "benchmark": "benchmark, ranking, leaderboard, evaluation result, or performance comparison",
    "other": "concrete high-value AI event that does not fit the other categories",
}

EVENT_TYPE_GUIDANCE = "\n".join(
    f"- {event_type}: {description}" for event_type, description in EVENT_TYPE_DESCRIPTIONS.items()
)


def normalize_event_type(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return DEFAULT_EVENT_TYPE
    if text in EVENT_TYPES:
        return text
    return DEFAULT_EVENT_TYPE
