# 后端说明

后端负责接收分析任务、保存任务过程、调用 Claude Code Skill，并通过 SSE 向前端推送任务状态。

## 本地启动

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

