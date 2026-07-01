import json
import os
import subprocess
from pathlib import Path

from app.config import get_settings


def run_creative_skill(repo_path: str, analysis_depth: str) -> dict:
    """调用 Claude Code。未启用时返回演示结果，保证开源项目可直接体验。"""

    settings = get_settings()
    if not settings.enable_claude:
        return build_demo_result(repo_path, analysis_depth)

    prompt = build_prompt(repo_path, analysis_depth, settings.skill_file_path)
    env = os.environ.copy()
    if settings.anthropic_api_key:
        env["ANTHROPIC_API_KEY"] = settings.anthropic_api_key

    completed = subprocess.run(
        [settings.claude_command, "-p", prompt],
        cwd=repo_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=1800,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("Claude Code 调用失败，请检查认证、命令路径和项目访问权限")

    return parse_claude_json(completed.stdout)


def build_prompt(repo_path: str, analysis_depth: str, skill_path: Path) -> str:
    skill_text = skill_path.read_text(encoding="utf-8") if skill_path.exists() else ""
    return f"""
你是 Git 项目创意蒸馏器，请严格按照下面的 Skill 方法分析当前项目。

项目路径：{repo_path}
分析深度：{analysis_depth}

请只输出一个合法 JSON，不要输出 Markdown 包裹符号。

{skill_text}
"""


def parse_claude_json(text: str) -> dict:
    content = text.strip()
    if content.startswith("```"):
        lines = [line for line in content.splitlines() if not line.strip().startswith("```")]
        content = "\n".join(lines)
    return json.loads(content)


def build_demo_result(repo_path: str, analysis_depth: str) -> dict:
    name = Path(repo_path).name or "示例项目"
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
                "title": "把 Git 项目转化为创意资产",
                "innovation_type": "重新定义问题",
                "innovation_layer": "方法层",
                "score": 8.2,
                "traditional_approach": "传统代码分析更关注依赖、质量和缺陷，输出通常是一份技术报告。",
                "new_approach": "本项目把代码库视为可蒸馏的创意来源，强调传统做法、创新差异、源码证据和迁移价值。",
                "description": "它不是只判断项目用了什么技术，而是识别项目想问题的方式，并把这些方式保存为可复用知识。",
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

