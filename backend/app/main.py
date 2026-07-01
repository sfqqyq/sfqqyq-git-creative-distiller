import asyncio
import json
from pathlib import Path
from threading import Thread

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db, init_db
from app.models import AnalysisReport, AnalysisStep, AnalysisTask, CreativePoint, Project
from app.schemas import TaskCreateRequest, TaskCreateResponse, TaskListItem
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


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/tasks", response_model=TaskCreateResponse)
def create_task(payload: TaskCreateRequest, db: Session = Depends(get_db)) -> TaskCreateResponse:
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
def list_tasks(db: Session = Depends(get_db)) -> list[TaskListItem]:
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
        ))
    return result


@app.get("/api/tasks/{task_id}")
def get_task(task_id: int, db: Session = Depends(get_db)) -> dict:
    task = db.get(AnalysisTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    project = db.get(Project, task.project_id)
    steps = db.query(AnalysisStep).filter(AnalysisStep.task_id == task.id).order_by(AnalysisStep.id.asc()).all()
    points = db.query(CreativePoint).filter(CreativePoint.task_id == task.id).order_by(CreativePoint.score.desc()).all()

    return {
        "task": task_to_dict(task),
        "project": project_to_dict(project),
        "steps": [step_to_dict(item) for item in steps],
        "creative_points": [point_to_dict(item) for item in points],
    }


@app.get("/api/tasks/{task_id}/report")
def get_report(task_id: int, db: Session = Depends(get_db)) -> dict:
    report = db.query(AnalysisReport).filter(AnalysisReport.task_id == task_id).first()
    if report is None:
        raise HTTPException(status_code=404, detail="报告尚未生成")
    return {
        "summary": report.summary,
        "markdown": report.markdown,
        "result": json.loads(report.result_json),
        "created_at": report.created_at.isoformat(timespec="seconds"),
    }


@app.get("/api/tasks/{task_id}/events")
async def task_events(task_id: int):
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
    }


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
    return {
        "id": point.id,
        "title": point.title,
        "innovation_type": point.innovation_type,
        "innovation_layer": point.innovation_layer,
        "score": point.score,
        "traditional_approach": point.traditional_approach,
        "new_approach": point.new_approach,
        "description": point.description,
        "evidence": json.loads(point.evidence_json),
        "moveable_domains": json.loads(point.moveable_domains_json),
    }
