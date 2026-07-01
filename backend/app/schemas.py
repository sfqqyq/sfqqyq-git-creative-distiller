from pydantic import BaseModel, Field


class TaskCreateRequest(BaseModel):
    source: str = Field(min_length=2, max_length=1000)
    analysis_depth: str = Field(default="standard", max_length=30)


class TaskCreateResponse(BaseModel):
    task_id: int
    project_id: int


class TaskListItem(BaseModel):
    id: int
    project_name: str
    source: str
    status: str
    current_step: str
    creative_count: int
    created_at: str


