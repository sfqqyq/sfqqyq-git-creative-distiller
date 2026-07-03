TEMPLATE_SCENARIO_NAMES = {
    "企业内部系统改造",
    "数据处理和自动化流程",
    "AI 辅助研发工具",
    "可迁移场景",
    "应用场景",
}

TEMPLATE_DESCRIPTION_FRAGMENTS = [
    "这类做法迁移到老系统升级",
    "用于把重复、耗时、容易出错",
    "不只回答问题，还能沉淀",
    "可以把这个思路迁移到类似业务流程",
]

SCENARIO_VALUE_KEYWORDS = [
    "减少",
    "降低",
    "提升",
    "避免",
    "防止",
    "节省",
    "缩短",
    "定位",
    "发现",
    "排查",
    "保证",
    "确保",
    "统一",
    "复用",
    "稳定",
    "风险",
    "成本",
    "误报",
    "维护",
    "冲突",
    "一致",
    "追踪",
    "审计",
]


def normalize_scenarios(items: list) -> list[dict]:
    scenarios = []
    for item in items:
        if isinstance(item, str):
            scenarios.append({"name": item, "description": ""})
        elif isinstance(item, dict):
            scenarios.append({
                "name": str(item.get("name") or item.get("scenario") or item.get("domain") or "").strip(),
                "description": str(item.get("description") or item.get("example") or "").strip(),
            })
    return scenarios


def unique_real_scenarios(items: list[dict]) -> list[dict]:
    result = []
    seen = set()
    for item in items:
        name = item.get("name", "").strip()
        description = item.get("description", "").strip()
        if not is_real_scenario(name, description):
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append({"name": name, "description": description})
    return result


def is_real_scenario(name: str, description: str) -> bool:
    if not name or name in TEMPLATE_SCENARIO_NAMES:
        return False
    if len(description) < 18:
        return False
    if not any(keyword in description for keyword in SCENARIO_VALUE_KEYWORDS):
        return False
    return not any(fragment in description for fragment in TEMPLATE_DESCRIPTION_FRAGMENTS)
