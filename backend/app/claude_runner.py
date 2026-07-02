import json
import os
import re
import subprocess
from json import JSONDecodeError
from pathlib import Path

from app.config import get_settings


def run_creative_skill(
    repo_path: str,
    analysis_depth: str,
    mode: str = "full",
    existing_points: list[dict] | None = None,
) -> dict:
    """调用 Claude Code。未启用时返回演示结果，保证开源项目可直接体验。"""

    settings = get_settings()
    existing_points = existing_points or []
    if not settings.enable_claude:
        return build_demo_result(repo_path, analysis_depth, mode, existing_points)

    prompt = build_prompt(repo_path, analysis_depth, settings.skill_file_path, mode, existing_points)
    env = os.environ.copy()
    if settings.anthropic_api_key:
        env["ANTHROPIC_API_KEY"] = settings.anthropic_api_key

    claude_env = build_claude_env(env)
    completed = run_claude_command(settings.claude_command, prompt, repo_path, claude_env, timeout=1800)
    result = parse_with_json_repair(completed.stdout, settings.claude_command, repo_path, claude_env)
    if should_retry_missing_creative_points(result, mode):
        retry_prompt = build_missing_points_prompt(repo_path, analysis_depth, existing_points, result)
        retried = run_claude_command(settings.claude_command, retry_prompt, repo_path, claude_env, timeout=1800)
        result = parse_with_json_repair(retried.stdout, settings.claude_command, repo_path, claude_env)
    return normalize_result(result, mode)


def run_claude_command(command: str, prompt: str, repo_path: str, env: dict, timeout: int) -> subprocess.CompletedProcess:
    completed = subprocess.run(
        [command, "-p", prompt],
        cwd=repo_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        if len(detail) > 600:
            detail = detail[-600:]
        message = "Claude Code 调用失败，请检查认证、命令路径和项目访问权限"
        if detail:
            message = f"{message}：{detail}"
        raise RuntimeError(message)
    return completed


def parse_with_json_repair(raw_text: str, command: str, repo_path: str, env: dict) -> dict:
    try:
        return parse_claude_json(raw_text)
    except JSONDecodeError as exc:
        repair_prompt = build_repair_prompt(raw_text, str(exc))
        repaired = run_claude_command(command, repair_prompt, repo_path, env, timeout=600)
        try:
            return parse_claude_json(repaired.stdout)
        except JSONDecodeError as repair_exc:
            snippet = raw_text.strip().replace("\n", " ")[:600]
            raise RuntimeError(f"Claude 返回内容不是合法 JSON，自动修复也失败：{repair_exc}。原始输出片段：{snippet}") from repair_exc


def should_retry_missing_creative_points(result: dict, mode: str) -> bool:
    if mode != "incremental":
        return False
    creative_points = result.get("creative_points")
    if creative_points:
        return False
    candidate_count = sum(int(item.get("candidates_count", 0) or 0) for item in result.get("scan_lines", []))
    return candidate_count > 0


def normalize_result(result: dict, mode: str) -> dict:
    result.setdefault("project", {})
    result.setdefault("scan_lines", [])
    result.setdefault("creative_points", [])
    if not result.get("final_report_markdown"):
        project_name = result.get("project", {}).get("name") or "项目"
        if mode == "incremental" and not result["creative_points"]:
            result["final_report_markdown"] = f"# {project_name} 创意蒸馏报告\n\n本轮增量识别没有产出可入库的新创意点。"
        else:
            result["final_report_markdown"] = f"# {project_name} 创意蒸馏报告\n\n本轮识别返回 {len(result['creative_points'])} 个创意点。"
    return result


def build_claude_env(base_env: dict) -> dict:
    settings = get_settings()
    env = base_env.copy()
    claude_vars = {
        "ANTHROPIC_API_KEY": settings.anthropic_api_key,
        "ANTHROPIC_BASE_URL": settings.anthropic_base_url,
        "ANTHROPIC_AUTH_TOKEN": settings.anthropic_auth_token,
        "ANTHROPIC_MODEL": settings.anthropic_model,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": settings.anthropic_default_opus_model,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": settings.anthropic_default_sonnet_model,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": settings.anthropic_default_haiku_model,
        "CLAUDE_CODE_SUBAGENT_MODEL": settings.claude_code_subagent_model,
        "CLAUDE_CODE_EFFORT_LEVEL": settings.claude_code_effort_level,
    }
    for key, value in claude_vars.items():
        if value:
            env[key] = value
    return env


def build_prompt(
    repo_path: str,
    analysis_depth: str,
    skill_path: Path,
    mode: str,
    existing_points: list[dict],
) -> str:
    skill_text = skill_path.read_text(encoding="utf-8") if skill_path.exists() else ""
    existing_text = json.dumps(existing_points, ensure_ascii=False, indent=2)
    return f"""
识别模式：{mode}
已有创意点 JSON：
{existing_text}

你是 Git 项目创意蒸馏器，请严格按照下面的 Skill 方法分析当前项目。

项目路径：{repo_path}
分析深度：{analysis_depth}

请只输出一个合法 JSON，不要输出 Markdown 包裹符号。
JSON 必须能被 Python json.loads 直接解析。
所有字符串中的双引号必须转义，所有换行必须写成 \\n。
不要在 JSON 前后添加任何说明文字。
不要使用单引号，不要写注释，不要写尾随逗号。
如果证据行号不确定，line_start 和 line_end 使用 1。

{skill_text}
"""


def parse_claude_json(text: str) -> dict:
    content = text.strip()
    if content.startswith("```"):
        lines = [line for line in content.splitlines() if not line.strip().startswith("```")]
        content = "\n".join(lines)
    start = content.find("{")
    end = content.rfind("}")
    if start >= 0 and end > start:
        content = content[start:end + 1]
    try:
        return json.loads(content)
    except JSONDecodeError:
        repaired = repair_common_json_text(content)
        if repaired != content:
            return json.loads(repaired)
        raise


def repair_common_json_text(content: str) -> str:
    """修复 Claude 偶发的轻微 JSON 格式问题，修不好再交给二次模型修复。"""

    content = re.sub(r",\s*([}\]])", r"\1", content)
    result: list[str] = []
    in_string = False
    escaped = False
    length = len(content)

    for index, char in enumerate(content):
        if escaped:
            result.append(char)
            escaped = False
            continue

        if in_string and char == "\\":
            result.append(char)
            escaped = True
            continue

        if char == '"':
            if not in_string:
                in_string = True
                result.append(char)
                continue

            next_index = index + 1
            while next_index < length and content[next_index].isspace():
                next_index += 1
            next_char = content[next_index] if next_index < length else ""
            if next_char in {":", ",", "}", "]", ""}:
                in_string = False
                result.append(char)
            else:
                result.append('\\"')
            continue

        result.append(char)

    return "".join(result)


def build_repair_prompt(raw_text: str, error_message: str) -> str:
    return f"""
下面是一段原本应该是 JSON 的内容，但它无法被 Python json.loads 解析。
解析错误：{error_message}

请只输出修复后的严格 JSON，不要输出 Markdown，不要输出解释文字。
要求：
- 所有对象 key 必须使用双引号。
- 字符串必须使用双引号。
- 不要使用注释。
- 不要使用尾随逗号。
- 不要省略数组或对象的闭合符号。
- 保留原始语义和字段，不要新增无关内容。

原始内容：
{raw_text}
"""


def build_missing_points_prompt(
    repo_path: str,
    analysis_depth: str,
    existing_points: list[dict],
    previous_result: dict,
) -> str:
    existing_text = json.dumps(existing_points, ensure_ascii=False, indent=2)
    previous_text = json.dumps(previous_result, ensure_ascii=False, indent=2)
    return f"""
你刚才执行了增量识别，但只返回了 scan_lines，没有返回可入库的 creative_points。
这会导致页面显示“扫描到了候选”，但创意点数量没有增加。

请基于当前仓库重新深挖，并只输出一个合法 JSON，不要输出 Markdown 包裹符号。
项目路径：{repo_path}
分析深度：{analysis_depth}

已有创意点 JSON：
{existing_text}

上一轮扫描结果 JSON：
{previous_text}

硬性要求：
- 必须输出完整结构：project、scan_lines、creative_points、final_report_markdown。
- 如果 scan_lines 中 candidates_count 大于 0，必须从候选中挑选 2 到 6 个真正独立的新创意点写入 creative_points。
- 新创意点不能是已有创意点的同义改写，必须更细、更偏实现、更偏迁移价值。
- 每个新创意点必须包含 title、innovation_type、innovation_layer、score、traditional_approach、new_approach、description、plain_explanation、application_scenarios、evidence、moveable_domains、discovery_reason。
- 如果你判断所有候选都已经被已有创意点覆盖，creative_points 才能为空；此时 final_report_markdown 必须逐条说明哪些候选被哪个已有创意点覆盖，不能只写“没有新增”。
- 所有字符串中的双引号必须转义，所有换行必须写成 \\n。
- JSON 必须能被 Python json.loads 直接解析。
"""


def build_demo_result(
    repo_path: str,
    analysis_depth: str,
    mode: str = "full",
    existing_points: list[dict] | None = None,
) -> dict:
    name = Path(repo_path).name or "示例项目"
    demo_title = "把 Git 项目转化为创意资产"
    demo_plain = "它像是在读一个项目时不只看代码写得好不好，而是把项目里聪明的想法挑出来，整理成以后别人也能学、能用的小经验。"
    demo_reason = ""
    if mode == "incremental":
        count = len(existing_points or [])
        demo_title = f"第 {count + 1} 个补充创意：从遗漏细节里继续挖价值"
        demo_plain = "它像第二次翻一本已经读过的书，这次不再标记大家都能看到的重点，而是专门找页边小字和隐藏用法。这样能把第一轮漏掉的细节补出来。"
        demo_reason = "演示模式下生成的增量创意点，用来验证追加识别流程。"
    return {
        "project": {
            "name": name,
            "summary": "这是未启用 Claude Code 时生成的演示结果，用于验证任务流程和页面展示。",
            "main_languages": ["Python", "JavaScript"],
            "frameworks": ["FastAPI", "Vue"],
        },
        "scan_lines": [
            {
                "name": "README 亮点",
                "status": "completed",
                "files_scanned": ["README.md"],
                "candidates_count": 1,
                "message": "发现项目把源码分析结果转化为可复用创意资产。",
            },
            {
                "name": "自造概念词",
                "status": "completed",
                "files_scanned": ["docs/"],
                "candidates_count": 1,
                "message": "发现“创意蒸馏”“扫描线”等概念词。",
            },
            {
                "name": "CHANGELOG 重大决策",
                "status": "skipped",
                "files_scanned": [],
                "candidates_count": 0,
                "message": "演示模式未读取 CHANGELOG。",
            },
            {
                "name": "架构/设计文档",
                "status": "completed",
                "files_scanned": ["docs/架构设计.md"],
                "candidates_count": 1,
                "message": "发现任务过程与创意结果分离保存的设计。",
            },
            {
                "name": "安全/运维巧思",
                "status": "completed",
                "files_scanned": [".env.example", "docker-compose.yml"],
                "candidates_count": 1,
                "message": "通过环境变量隔离 Claude Key。",
            },
            {
                "name": "代码中的非常规实现",
                "status": "completed",
                "files_scanned": ["backend/app/worker.py"],
                "candidates_count": 1,
                "message": "用最小后台任务实现长流程分析。",
            },
        ],
        "creative_points": [
            {
                "title": demo_title,
                "innovation_type": "重新定义问题",
                "innovation_layer": "方法层",
                "score": 8.2,
                "traditional_approach": "传统代码分析更关注依赖、质量和缺陷，输出通常是一份技术报告。",
                "new_approach": "本项目把代码库视为可蒸馏的创意来源，强调传统做法、创新差异、源码证据和迁移价值。",
                "description": "它不是只判断项目用了什么技术，而是识别项目想问题的方式，并把这些方式保存为可复用知识。",
                "plain_explanation": demo_plain,
                "discovery_reason": demo_reason,
                "evidence": [
                    {"file": "skills/git-creative-discovery/SKILL.md", "line_start": 1, "line_end": 80, "quote": "6 条扫描线和 7 类创意信号"}
                ],
                "moveable_domains": [
                    {"domain": "企业研发 > 技术复盘", "example": "把内部项目沉淀为可复用工程方法"},
                    {"domain": "开源运营 > 项目解读", "example": "快速提炼开源项目的传播亮点和技术价值"}
                ],
            }
        ],
        "final_report_markdown": f"# {name} 创意蒸馏报告\n\n当前为演示模式，分析深度：{analysis_depth}。\n\n## 核心创意\n\n把 Git 项目转化为创意资产。",
    }
