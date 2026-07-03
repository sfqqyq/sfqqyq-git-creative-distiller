import asyncio
import json
from datetime import datetime
from pathlib import Path
from threading import Thread

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import login, logout, require_login
from app.database import SessionLocal, get_db, init_db
from app.models import AnalysisReport, AnalysisStep, AnalysisTask, CreativePoint, Project
from app.scenario_quality import unique_real_scenarios
from app.schemas import LoginRequest, LoginResponse, TaskCreateRequest, TaskCreateResponse, TaskIncrementalRequest, TaskListItem
from app.worker import run_task


app = FastAPI(title="Git 创意蒸馏器")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()
    close_orphan_tasks()


def close_orphan_tasks() -> None:
    """服务重启会中断后台线程，把遗留 running/pending 任务改成可重试状态。"""

    with SessionLocal() as db:
        tasks = db.query(AnalysisTask).filter(AnalysisTask.status.in_(["pending", "running"])).all()
        if not tasks:
            return
        now = datetime.now()
        message = "服务重启后，后台执行线程已中断，请重新发起增量识别。"
        for task in tasks:
            task.status = "failed"
            task.current_step = "任务已中断"
            task.error_message = message
            task.finished_at = now
            steps = db.query(AnalysisStep).filter(
                AnalysisStep.task_id == task.id,
                AnalysisStep.status.in_(["pending", "running"]),
            ).all()
            for step in steps:
                step.status = "failed" if step.status == "running" else "skipped"
                step.message = message
                step.finished_at = now
        db.commit()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/auth/login", response_model=LoginResponse)
def auth_login(payload: LoginRequest, response: Response) -> dict:
    return login(response, payload.username.strip(), payload.password)


@app.post("/api/auth/logout")
def auth_logout(response: Response) -> dict:
    return logout(response)


@app.get("/api/auth/me", response_model=LoginResponse)
def auth_me(username: str = Depends(require_login)) -> dict:
    return {"username": username}


@app.post("/api/tasks", response_model=TaskCreateResponse)
def create_task(
    payload: TaskCreateRequest,
    db: Session = Depends(get_db),
    _username: str = Depends(require_login),
) -> TaskCreateResponse:
    source = payload.source.strip()
    if not source:
        raise HTTPException(status_code=400, detail="项目地址不能为空")

    source_type = detect_source_type(source)
    project = Project(name=guess_project_name(source), source=source, source_type=source_type)
    db.add(project)
    db.commit()
    db.refresh(project)

    task = AnalysisTask(project_id=project.id)
    db.add(task)
    db.commit()
    db.refresh(task)

    thread = Thread(target=run_task, args=(task.id, payload.analysis_depth), daemon=True)
    thread.start()

    return TaskCreateResponse(task_id=task.id, project_id=project.id)


@app.get("/api/tasks", response_model=list[TaskListItem])
def list_tasks(
    db: Session = Depends(get_db),
    _username: str = Depends(require_login),
) -> list[TaskListItem]:
    tasks = db.query(AnalysisTask).order_by(AnalysisTask.id.desc()).limit(50).all()
    result = []
    for task in tasks:
        project = db.get(Project, task.project_id)
        creative_count = db.query(CreativePoint).filter(CreativePoint.task_id == task.id).count()
        result.append(TaskListItem(
            id=task.id,
            project_name=project.name if project else "未知项目",
            source=project.source if project else "",
            status=task.status,
            current_step=task.current_step,
            creative_count=creative_count,
            created_at=task.created_at.isoformat(timespec="seconds"),
            started_at=task.started_at.isoformat(timespec="seconds") if task.started_at else "",
            finished_at=task.finished_at.isoformat(timespec="seconds") if task.finished_at else "",
            duration_seconds=task_duration_seconds(task),
        ))
    return result


@app.get("/api/tasks/{task_id}")
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    _username: str = Depends(require_login),
) -> dict:
    task = db.get(AnalysisTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    project = db.get(Project, task.project_id)
    steps = db.query(AnalysisStep).filter(AnalysisStep.task_id == task.id).order_by(AnalysisStep.id.asc()).all()
    points = db.query(CreativePoint).filter(CreativePoint.task_id == task.id).order_by(
        CreativePoint.source_round.desc(),
        CreativePoint.score.desc(),
    ).all()

    return {
        "task": task_to_dict(task),
        "project": project_to_dict(project),
        "steps": [step_to_dict(item) for item in steps],
        "creative_points": [point_to_dict(item) for item in points],
    }


@app.get("/api/tasks/{task_id}/report")
def get_report(
    task_id: int,
    db: Session = Depends(get_db),
    _username: str = Depends(require_login),
) -> dict:
    report = db.query(AnalysisReport).filter(AnalysisReport.task_id == task_id).order_by(AnalysisReport.id.desc()).first()
    if report is None:
        raise HTTPException(status_code=404, detail="报告尚未生成")
    return {
        "summary": report.summary,
        "markdown": report.markdown,
        "result": json.loads(report.result_json),
        "created_at": report.created_at.isoformat(timespec="seconds"),
    }


@app.post("/api/tasks/{task_id}/incremental", response_model=TaskCreateResponse)
def create_incremental_task(
    task_id: int,
    payload: TaskIncrementalRequest,
    db: Session = Depends(get_db),
    _username: str = Depends(require_login),
) -> TaskCreateResponse:
    task = db.get(AnalysisTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status in {"pending", "running"}:
        raise HTTPException(status_code=409, detail="任务正在执行，不能启动增量识别")
    project = db.get(Project, task.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    task.status = "pending"
    task.current_step = "等待增量识别"
    task.error_message = ""
    task.finished_at = None
    db.commit()

    thread = Thread(target=run_task, args=(task.id, payload.analysis_depth, "incremental"), daemon=True)
    thread.start()
    return TaskCreateResponse(task_id=task.id, project_id=project.id)


@app.delete("/api/tasks/{task_id}")
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    _username: str = Depends(require_login),
) -> dict:
    task = db.get(AnalysisTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status in {"pending", "running"}:
        raise HTTPException(status_code=409, detail="任务正在执行，暂不能删除")

    project_id = task.project_id
    other_task_count = db.query(AnalysisTask).filter(
        AnalysisTask.project_id == project_id,
        AnalysisTask.id != task.id,
    ).count()
    db.query(AnalysisReport).filter(AnalysisReport.task_id == task.id).delete()
    db.query(CreativePoint).filter(CreativePoint.task_id == task.id).delete()
    db.query(AnalysisStep).filter(AnalysisStep.task_id == task.id).delete()
    db.delete(task)

    if other_task_count == 0:
        project = db.get(Project, project_id)
        if project is not None:
            db.delete(project)

    db.commit()
    return {"status": "deleted"}


@app.delete("/api/creative-points/{point_id}")
def delete_creative_point(
    point_id: int,
    db: Session = Depends(get_db),
    _username: str = Depends(require_login),
) -> dict:
    point = db.get(CreativePoint, point_id)
    if point is None:
        raise HTTPException(status_code=404, detail="创意点不存在")
    task = db.get(AnalysisTask, point.task_id)
    if task is not None and task.status in {"pending", "running"}:
        raise HTTPException(status_code=409, detail="任务正在执行，暂时不能删除创意点")

    db.delete(point)
    db.commit()
    return {"status": "deleted"}


@app.get("/api/tasks/{task_id}/events")
async def task_events(task_id: int, _username: str = Depends(require_login)):
    async def event_stream():
        last_payload = ""
        while True:
            with SessionLocal() as db:
                task = db.get(AnalysisTask, task_id)
                if task is None:
                    yield "event: error\ndata: {\"message\":\"任务不存在\"}\n\n"
                    break
                payload = json.dumps({"task": task_to_dict(task)}, ensure_ascii=False)
                if payload != last_payload:
                    yield f"data: {payload}\n\n"
                    last_payload = payload
                if task.status in {"completed", "failed"}:
                    break
            await asyncio.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def detect_source_type(source: str) -> str:
    if source.startswith(("http://", "https://", "git@")):
        return "git"
    return "local"


def guess_project_name(source: str) -> str:
    normalized = source.rstrip("/")
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    return Path(normalized).name or "未命名项目"


def task_to_dict(task: AnalysisTask) -> dict:
    return {
        "id": task.id,
        "status": task.status,
        "current_step": task.current_step,
        "error_message": task.error_message,
        "created_at": task.created_at.isoformat(timespec="seconds"),
        "started_at": task.started_at.isoformat(timespec="seconds") if task.started_at else "",
        "finished_at": task.finished_at.isoformat(timespec="seconds") if task.finished_at else "",
        "duration_seconds": task_duration_seconds(task),
    }


def task_duration_seconds(task: AnalysisTask) -> int:
    start_time = task.started_at or task.created_at
    end_time = task.finished_at or datetime.now()
    seconds = int((end_time - start_time).total_seconds())
    return max(seconds, 0)


def project_to_dict(project: Project | None) -> dict:
    if project is None:
        return {}
    return {
        "id": project.id,
        "name": project.name,
        "source": project.source,
        "source_type": project.source_type,
        "local_path": project.local_path,
        "created_at": project.created_at.isoformat(timespec="seconds"),
    }


def step_to_dict(step: AnalysisStep) -> dict:
    return {
        "id": step.id,
        "name": step.name,
        "status": step.status,
        "message": step.message,
        "files_scanned": json.loads(step.files_scanned),
        "candidates_count": step.candidates_count,
    }


def point_to_dict(point: CreativePoint) -> dict:
    moveable_domains = json.loads(point.moveable_domains_json)
    application_scenarios = unique_real_scenarios(json.loads(point.application_scenarios_json))
    if len(application_scenarios) < 3:
        application_scenarios = build_application_scenarios(point, moveable_domains)
    return {
        "id": point.id,
        "title": point.title,
        "innovation_type": point.innovation_type,
        "innovation_layer": point.innovation_layer,
        "score": point.score,
        "traditional_approach": point.traditional_approach,
        "new_approach": point.new_approach,
        "description": point.description,
        "plain_explanation": point.plain_explanation,
        "evidence": json.loads(point.evidence_json),
        "moveable_domains": moveable_domains,
        "application_scenarios": application_scenarios,
        "source_round": point.source_round,
        "discovery_reason": point.discovery_reason,
        "created_at": point.created_at.isoformat(timespec="seconds"),
    }


def build_application_scenarios(point: CreativePoint, moveable_domains: list[dict]) -> list[dict]:
    scenarios = []
    for item in moveable_domains:
        if not isinstance(item, dict):
            continue
        scenarios.append({
            "name": str(item.get("domain") or "可迁移场景").strip(),
            "description": str(item.get("example") or "可以把这个思路迁移到类似业务流程中。").strip(),
        })
    return unique_real_scenarios(scenarios)[:5]
