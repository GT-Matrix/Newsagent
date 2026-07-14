from __future__ import annotations


IMPORTANCE_BASE = {
    "model_release": 80.0,
    "policy": 78.0,
    "hardware": 76.0,
    "infrastructure": 72.0,
    "product_release": 72.0,
    "partnership": 68.0,
    "legal": 70.0,
    "funding": 65.0,
    "acquisition": 66.0,
    "research": 64.0,
    "benchmark": 60.0,
    "open_source": 62.0,
    "tooling": 58.0,
    "company_business": 58.0,
    "company_policy": 56.0,
    "rumor": 45.0,
    "unknown": 45.0,
}

WHY_IMPORTANT_BY_TYPE = {
    "model_release": "这可能影响模型能力边界、开发者工具链和同类产品竞争。",
    "product_release": "这会影响 AI 产品形态、用户工作流以及竞品后续跟进方向。",
    "partnership": "这说明 AI 能力正在通过产业合作进入更大规模的落地阶段。",
    "funding": "这反映资本对该方向的持续关注，也可能改变赛道竞争格局。",
    "policy": "这可能影响 AI 产品合规、市场进入和企业部署策略。",
    "hardware": "这会影响推理成本、算力供给和 AI 基础设施竞争。",
    "infrastructure": "这关系到模型部署、推理效率和企业级 AI 应用的成本结构。",
    "research": "这类内容适合作为团队理解技术趋势和方法论的参考。",
    "benchmark": "这有助于判断模型或工具在真实任务中的能力边界。",
    "open_source": "这类资源适合进入长期资产池，后续可用于工程实践或方案参考。",
    "tooling": "这可能提升研发效率，适合作为团队工具链候选项观察。",
    "legal": "这可能影响 AI 内容使用、版权合规和平台责任边界。",
}
