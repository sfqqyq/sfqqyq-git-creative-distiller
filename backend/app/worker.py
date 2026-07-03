import json
import re
import shutil
import subprocess
from hashlib import sha1
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.claude_runner import run_creative_skill
from app.config import get_settings
from app.database import SessionLocal
from app.models import AnalysisReport, AnalysisStep, AnalysisTask, CreativePoint, Project
from app.scenario_quality import normalize_scenarios, unique_real_scenarios


SCAN_LINE_NAMES = [
    "README 亮点",
    "自造概念词",
    "CHANGELOG 重大决策",
    "架构/设计文档",
    "安全/运维巧思",
    "代码中的非常规实现",
]


def run_task(task_id: int, analysis_depth: str, mode: str = "full") -> None:
    db = SessionLocal()
    try:
        task = db.get(AnalysisTask, task_id)
        if task is None:
            return
        project = db.get(Project, task.project_id)
        if project is None:
            return

        round_index = next_round_index(db, task.id) if mode == "incremental" else 1

        task.status = "running"
        task.started_at = datetime.now()
        task.finished_at = None
        task.error_message = ""
        task.current_step = "增量识别准备" if mode == "incremental" else "准备项目"
        create_scan_steps(task.id, db, round_index, mode)
        db.commit()

        first_step = step_name("README 亮点", round_index, mode)
        mark_step(db, task.id, first_step, "running", "正在准备项目：复用仓库缓存或读取本地路径")
        repo_path = prepare_repo(project, db)
        mark_step(db, task.id, first_step, "running", "开始调用 Claude Code Skill")

        result = run_creative_skill(
            str(repo_path),
            analysis_depth,
            mode=mode,
            existing_points=existing_points(db, task.id) if mode == "incremental" else [],
        )
        save_result(db, task, result, round_index, mode)

        task.status = "completed"
        task.current_step = "增量识别完成" if mode == "incremental" else "分析完成"
        task.finished_at = datetime.now()
        db.commit()
    except Exception as exc:
        task = db.get(AnalysisTask, task_id)
        if task is not None:
            error_message = str(exc)
            mark_failed_steps(db, task.id, error_message)
            task.status = "failed"
            task.current_step = "分析失败"
            task.error_message = error_message
            task.finished_at = datetime.now()
            db.commit()
    finally:
        db.close()


def prepare_repo(project: Project, db: Session) -> Path:
    settings = get_settings()
    settings.workspace_path.mkdir(parents=True, exist_ok=True)

    if project.source_type == "local":
        path = Path(project.source).resolve()
        if not path.exists():
            raise RuntimeError("本地项目路径不存在")
        project.local_path = str(path)
        db.commit()
        return path

    clone_url = normalize_git_source(project.source, settings.github_clone_proxy)
    target = cached_repo_path(settings.workspace_path, project.source)
    if (target / ".git").exists():
        update_cached_repo(target, clone_url)
    else:
        remove_broken_cache(settings.workspace_path, target)
        clone_repo(clone_url, target)

    project.local_path = str(target)
    db.commit()
    return target


def cached_repo_path(workspace_path: Path, source: str) -> Path:
    normalized = normalize_git_source(source).removeprefix("https://").removeprefix("http://")
    readable = re.sub(r"[^a-zA-Z0-9._-]+", "_", normalized).strip("._-")[:80] or "repo"
    digest = sha1(normalized.encode("utf-8")).hexdigest()[:12]
    return workspace_path / f"{readable}-{digest}"


def clone_repo(clone_url: str, target: Path) -> None:
    completed = run_git_command(["git", "clone", "--depth", "1", clone_url, str(target)], timeout=600)
    if completed.returncode != 0:
        raise RuntimeError(f"Git 仓库克隆失败，请检查地址和访问权限：{git_error_detail(completed)}")


def update_cached_repo(target: Path, clone_url: str) -> None:
    run_git_command(["git", "-C", str(target), "remote", "set-url", "origin", clone_url], timeout=60)
    fetch_result = run_git_command(["git", "-C", str(target), "fetch", "--depth", "1", "--prune", "origin"], timeout=600)
    if fetch_result.returncode != 0:
        raise RuntimeError(f"Git 仓库更新失败，请检查地址和访问权限：{git_error_detail(fetch_result)}")

    branch_result = run_git_command(["git", "-C", str(target), "rev-parse", "--abbrev-ref", "HEAD"], timeout=60)
    branch = (branch_result.stdout or "").strip()
    if not branch or branch == "HEAD":
        branch = default_remote_branch(target)

    reset_result = run_git_command(["git", "-C", str(target), "reset", "--hard", f"origin/{branch}"], timeout=120)
    if reset_result.returncode != 0:
        raise RuntimeError(f"Git 仓库缓存更新失败：{git_error_detail(reset_result)}")


def default_remote_branch(target: Path) -> str:
    result = run_git_command(["git", "-C", str(target), "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], timeout=60)
    value = (result.stdout or "").strip()
    if value.startswith("origin/"):
        return value.removeprefix("origin/")
    return "main"


def run_git_command(command: list[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def remove_broken_cache(workspace_path: Path, target: Path) -> None:
    if not target.exists():
        return
    workspace = workspace_path.resolve()
    resolved_target = target.resolve()
    if workspace != resolved_target and workspace in resolved_target.parents:
        shutil.rmtree(resolved_target)
        return
    raise RuntimeError("仓库缓存路径异常，已停止清理以避免误删文件")


def git_error_detail(completed: subprocess.CompletedProcess) -> str:
    detail = (completed.stderr or completed.stdout or "").strip()
    if len(detail) > 500:
        return detail[-500:]
    return detail or "没有返回详细错误"


def normalize_git_source(source: str, github_clone_proxy: str = "") -> str:
    normalized = source
    if source.startswith("git@github.com:") and source.endswith(".git"):
        repo = source.removeprefix("git@github.com:")
        normalized = f"https://github.com/{repo}"

    if normalized.startswith("https://github.com/") and github_clone_proxy.strip():
        return f"{github_clone_proxy.rstrip('/')}/{normalized}"
    return normalized


def next_round_index(db: Session, task_id: int) -> int:
    points = db.query(CreativePoint).filter(CreativePoint.task_id == task_id).all()
    rounds = [point.source_round for point in points]
    step_names = db.query(AnalysisStep.name).filter(AnalysisStep.task_id == task_id).all()
    for item in step_names:
        match = re.search(r"第(\d+)轮增量", item[0])
        if match:
            rounds.append(int(match.group(1)))
    if not rounds:
        return 1
    return max(rounds) + 1


def step_name(name: str, round_index: int, mode: str) -> str:
    if mode == "incremental":
        return f"第{round_index}轮增量 · {name}"
    return name


def existing_points(db: Session, task_id: int) -> list[dict]:
    points = db.query(CreativePoint).filter(CreativePoint.task_id == task_id).order_by(CreativePoint.score.desc()).all()
    return [
        {
            "title": point.title,
            "innovation_type": point.innovation_type,
            "innovation_layer": point.innovation_layer,
            "traditional_approach": point.traditional_approach,
            "new_approach": point.new_approach,
            "plain_explanation": point.plain_explanation,
        }
        for point in points
    ]


def create_scan_steps(task_id: int, db: Session, round_index: int = 1, mode: str = "full") -> None:
    exists_count = db.query(AnalysisStep).filter(AnalysisStep.task_id == task_id).count()
    if exists_count:
        if mode != "incremental":
            return
    for name in SCAN_LINE_NAMES:
        db.add(AnalysisStep(task_id=task_id, name=step_name(name, round_index, mode), status="pending"))
    db.commit()


def mark_step(db: Session, task_id: int, name: str, status: str, message: str) -> None:
    step = db.query(AnalysisStep).filter(
        AnalysisStep.task_id == task_id,
        AnalysisStep.name == name,
    ).order_by(AnalysisStep.id.desc()).first()
    if step is None:
        return
    step.status = status
    step.message = message
    if status == "running":
        step.started_at = datetime.now()
    if status in {"completed", "skipped", "failed"}:
        step.finished_at = datetime.now()
    task = db.get(AnalysisTask, task_id)
    if task is not None:
        task.current_step = name
    db.commit()


def mark_failed_steps(db: Session, task_id: int, message: str) -> None:
    steps = db.query(AnalysisStep).filter(AnalysisStep.task_id == task_id).all()
    for step in steps:
        if step.status == "running":
            step.status = "failed"
            step.message = message
            step.finished_at = datetime.now()
        elif step.status == "pending":
            step.status = "skipped"
            step.message = "任务已失败，未执行"
            step.finished_at = datetime.now()
    db.commit()


def save_result(db: Session, task: AnalysisTask, result: dict, round_index: int = 1, mode: str = "full") -> None:
    for item in result.get("scan_lines", []):
        step = find_scan_step(db, task.id, item.get("name", ""), round_index, mode)
        if step is None:
            continue
        step.status = item.get("status", "completed")
        step.message = item.get("message", "")
        step.files_scanned = json.dumps(item.get("files_scanned", []), ensure_ascii=False)
        step.candidates_count = int(item.get("candidates_count", 0))
        step.started_at = step.started_at or datetime.now()
        step.finished_at = datetime.now()

    existing_titles = {
        item.title.strip().lower()
        for item in db.query(CreativePoint).filter(CreativePoint.task_id == task.id).all()
    }
    for point in result.get("creative_points", []):
        title = point.get("title", "未命名创意")
        if mode == "incremental" and title.strip().lower() in existing_titles:
            continue
        description = point.get("description", "")
        moveable_domains = point.get("moveable_domains", [])
        db.add(CreativePoint(
            task_id=task.id,
            title=title,
            innovation_type=point.get("innovation_type", "未知"),
            innovation_layer=point.get("innovation_layer", "未知"),
            score=float(point.get("score", 0)),
            traditional_approach=point.get("traditional_approach", ""),
            new_approach=point.get("new_approach", ""),
            description=description,
            plain_explanation=point.get("plain_explanation", "") or build_plain_explanation(point, description),
            evidence_json=json.dumps(point.get("evidence", []), ensure_ascii=False),
            moveable_domains_json=json.dumps(moveable_domains, ensure_ascii=False),
            application_scenarios_json=json.dumps(
                build_application_scenarios(point, moveable_domains),
                ensure_ascii=False,
            ),
            source_round=round_index,
            discovery_reason=point.get("discovery_reason", ""),
        ))
        existing_titles.add(title.strip().lower())

    close_unfinished_scan_steps(db, task.id, round_index, mode)
    project_summary = result.get("project", {}).get("summary", "")
    markdown = result.get("final_report_markdown", "") or build_fallback_report(result, mode)
    db.add(AnalysisReport(
        task_id=task.id,
        summary=project_summary,
        result_json=json.dumps(result, ensure_ascii=False),
        markdown=markdown,
    ))
    db.commit()


def find_scan_step(db: Session, task_id: int, scan_name: str, round_index: int, mode: str) -> AnalysisStep | None:
    target = compact_step_name(step_name(scan_name, round_index, mode))
    steps = db.query(AnalysisStep).filter(AnalysisStep.task_id == task_id).order_by(AnalysisStep.id.desc()).all()
    for step in steps:
        if compact_step_name(step.name) == target:
            return step
    return None


def compact_step_name(name: str) -> str:
    return re.sub(r"\s+", "", name or "")


def close_unfinished_scan_steps(db: Session, task_id: int, round_index: int, mode: str) -> None:
    steps = db.query(AnalysisStep).filter(AnalysisStep.task_id == task_id).all()
    prefix = compact_step_name(f"第{round_index}轮增量") if mode == "incremental" else ""
    for step in steps:
        if mode == "incremental" and not compact_step_name(step.name).startswith(prefix):
            continue
        if step.status in {"pending", "running"}:
            step.status = "skipped"
            step.message = "本轮结果未返回该扫描线，已自动收尾。"
            step.finished_at = datetime.now()


def build_fallback_report(result: dict, mode: str) -> str:
    project = result.get("project", {})
    name = project.get("name", "项目")
    points = result.get("creative_points", [])
    if mode == "incremental" and not points:
        conclusion = "本轮增量识别没有返回新的创意点，系统已保留原有结果。"
    else:
        conclusion = f"本轮识别返回 {len(points)} 个创意点。"
    return f"# {name} 创意蒸馏报告\n\n{conclusion}"


def build_plain_explanation(point: dict, description: str) -> str:
    title = str(point.get("title") or "这个创意").strip()
    traditional = str(point.get("traditional_approach") or "").strip()
    new_approach = str(point.get("new_approach") or "").strip()
    text = f"{title} {traditional} {new_approach} {description}"

    if any(keyword in text for keyword in ["去重", "重复", "合并", "MinHash", "union-find"]):
        return f"{title}像是在整理一堆重复客户名单。以前要么全靠人肉眼比对，要么一上来就用很重的办法逐条判断；它先把明显不像的排除，再一轮轮确认像不像，最后只把真的是同一个的合起来。这样既省时间，也不容易把相似但不同的东西误合并。"
    if any(keyword in text for keyword in ["安全", "SSRF", "注入", "权限", "密钥", "Token"]):
        return f"{title}像是在系统门口加了几道安检。以前请求进来后才发现可能带着风险，现在先查来源、大小和内容边界，不合规的直接挡住。这样能让 AI 帮忙写代码时少踩安全坑，团队也更敢把工具接到真实项目里。"
    if any(keyword in text for keyword in ["缓存", "增量", "更新", "索引"]):
        return f"{title}像是只给变动过的抽屉重新贴标签。以前每次都把整柜文件翻一遍，慢还浪费机器；现在记住上次处理到哪里，只补新的、改变的部分。结果就是越用越省力，项目大了也不容易卡住。"
    if any(keyword in text for keyword in ["协议", "RTP", "H.264", "FMp4", "播放", "音频", "视频"]):
        return f"{title}像是把一箱散装零件按说明书直接拼成能用的机器。以前要先转很多中间格式，既慢又容易丢细节；它尽量按原始规则直接对上播放或封装需要的东西。这样实时处理更顺，机器压力也更小。"

    return f"{title}像是把一件容易绕晕人的事拆成几步让系统自己判断。以前常常要靠人反复试、反复猜；现在先过滤掉不靠谱的选择，再把真正值得看的留下来。这样少走弯路，也更容易把经验搬到别的项目里。"


def build_application_scenarios(point: dict, moveable_domains: list[dict]) -> list[dict]:
    scenarios = normalize_scenarios(point.get("application_scenarios", []))
    for item in moveable_domains:
        if not isinstance(item, dict):
            continue
        scenarios.append({
            "name": str(item.get("domain") or "可迁移场景").strip(),
            "description": str(item.get("example") or "可以把这个思路迁移到类似业务流程中。").strip(),
        })
    return unique_real_scenarios(scenarios)[:5]
