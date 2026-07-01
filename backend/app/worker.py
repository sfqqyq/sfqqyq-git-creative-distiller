import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.claude_runner import run_creative_skill
from app.config import get_settings
from app.database import SessionLocal
from app.models import AnalysisReport, AnalysisStep, AnalysisTask, CreativePoint, Project


SCAN_LINE_NAMES = [
    "README 亮点",
    "自造概念词",
    "CHANGELOG 重大决策",
    "架构/设计文档",
    "安全/运维巧思",
    "代码中的非常规实现",
]


def run_task(task_id: int, analysis_depth: str) -> None:
    db = SessionLocal()
    try:
        task = db.get(AnalysisTask, task_id)
        if task is None:
            return
        project = db.get(Project, task.project_id)
        if project is None:
            return

        task.status = "running"
        task.started_at = datetime.now()
        task.current_step = "准备项目"
        db.commit()

        repo_path = prepare_repo(project, db)
        create_scan_steps(task.id, db)
        mark_step(db, task.id, "README 亮点", "running", "开始调用 Claude Code Skill")

        result = run_creative_skill(str(repo_path), analysis_depth)
        save_result(db, task, result)

        task.status = "completed"
        task.current_step = "分析完成"
        task.finished_at = datetime.now()
        db.commit()
    except Exception as exc:
        task = db.get(AnalysisTask, task_id)
        if task is not None:
            task.status = "failed"
            task.current_step = "分析失败"
            task.error_message = str(exc)
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

    target = settings.workspace_path / f"project-{project.id}"
    if target.exists():
        shutil.rmtree(target)

    completed = subprocess.run(
        ["git", "clone", "--depth", "1", project.source, str(target)],
        text=True,
        capture_output=True,
        timeout=600,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("Git 仓库克隆失败，请检查地址和访问权限")

    project.local_path = str(target)
    db.commit()
    return target


def create_scan_steps(task_id: int, db: Session) -> None:
    for name in SCAN_LINE_NAMES:
        db.add(AnalysisStep(task_id=task_id, name=name, status="pending"))
    db.commit()


def mark_step(db: Session, task_id: int, name: str, status: str, message: str) -> None:
    step = db.query(AnalysisStep).filter(AnalysisStep.task_id == task_id, AnalysisStep.name == name).first()
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


def save_result(db: Session, task: AnalysisTask, result: dict) -> None:
    for item in result.get("scan_lines", []):
        step = db.query(AnalysisStep).filter(
            AnalysisStep.task_id == task.id,
            AnalysisStep.name == item.get("name", ""),
        ).first()
        if step is None:
            continue
        step.status = item.get("status", "completed")
        step.message = item.get("message", "")
        step.files_scanned = json.dumps(item.get("files_scanned", []), ensure_ascii=False)
        step.candidates_count = int(item.get("candidates_count", 0))
        step.started_at = step.started_at or datetime.now()
        step.finished_at = datetime.now()

    for point in result.get("creative_points", []):
        db.add(CreativePoint(
            task_id=task.id,
            title=point.get("title", "未命名创意"),
            innovation_type=point.get("innovation_type", "未知"),
            innovation_layer=point.get("innovation_layer", "未知"),
            score=float(point.get("score", 0)),
            traditional_approach=point.get("traditional_approach", ""),
            new_approach=point.get("new_approach", ""),
            description=point.get("description", ""),
            evidence_json=json.dumps(point.get("evidence", []), ensure_ascii=False),
            moveable_domains_json=json.dumps(point.get("moveable_domains", []), ensure_ascii=False),
        ))

    project_summary = result.get("project", {}).get("summary", "")
    db.add(AnalysisReport(
        task_id=task.id,
        summary=project_summary,
        result_json=json.dumps(result, ensure_ascii=False),
        markdown=result.get("final_report_markdown", ""),
    ))
    db.commit()

