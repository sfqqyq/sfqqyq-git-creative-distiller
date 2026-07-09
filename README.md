# sfqqyq-git-creative-distiller

Git 创意蒸馏器：输入一个 Git 仓库地址或本地项目路径，调用 Claude Code Skill 扫描项目文档、源码和工程结构，发现项目里的创意点、创新方法和可迁移价值。

## 核心能力

- 输入 Git 仓库地址或本地项目路径创建分析任务
- 按 6 条扫描线展示分析进度
- 保存创意点、源码证据、可迁移领域和最终报告
- 可为单个创意点调用 MiniMax 文生图生成释义图，并保存到本地
- 支持 Claude Code 真实分析，也支持未配置 Claude 时的演示结果
- 默认使用 SQLite，方便开源项目快速启动

## 技术栈

- 后端：FastAPI、SQLAlchemy、SQLite
- 前端：Vue 3、Vite、Element Plus
- 任务进度：SSE
- AI 分析：Claude Code + 自定义 Skill

## 快速启动

后端：

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy ..\.env.example ..\.env
uvicorn app.main:app --reload
```

前端：

```bash
cd frontend
npm install
npm run dev
```

访问：

```text
http://127.0.0.1:5173
```

## Claude Code 配置

服务器或本机需要安装 Claude Code，并配置认证。

```bash
npm install -g @anthropic-ai/claude-code@latest
```

`.env` 中打开真实调用：

```env
ENABLE_CLAUDE=true
ANTHROPIC_API_KEY=你的密钥
CLAUDE_COMMAND=claude
```

不要把真实 `.env` 提交到 Git。

## MiniMax 释义图配置

`.env` 中填写 MiniMax Key 后，页面里的每个创意点都可以手动生成释义图。生成结果会先下载到本地 `storage/images`，前端通过 `/generated-images/` 访问。

```env
MINIMAX_API_KEY=你的 MiniMax Key
MINIMAX_API_BASE_URL=https://api.minimaxi.com/v1
MINIMAX_IMAGE_MODEL=image-01
MINIMAX_IMAGE_ASPECT_RATIO=16:9
```
