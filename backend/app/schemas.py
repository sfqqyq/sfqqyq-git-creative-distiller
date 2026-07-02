from pydantic import BaseModel, Field


class TaskCreateRequest(BaseModel):
    source: str = Field(min_length=2, max_length=1000)
    analysis_depth: str = Field(default="standard", max_length=30)


class TaskCreateResponse(BaseModel):
    task_id: int
    project_id: int


class TaskIncrementalRequest(BaseModel):
    analysis_depth: str = Field(default="deep", max_length=30)


class TaskListItem(BaseModel):
    id: int
    project_name: str
    source: str
    status: str
    current_step: str
    creative_count: int
    created_at: str
    started_at: str
    finished_at: str
    duration_seconds: int
