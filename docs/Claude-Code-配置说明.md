# Claude Code 配置说明

## 安装

```bash
npm install -g @anthropic-ai/claude-code@latest
claude --version
```

## 认证

推荐使用环境变量配置，不要把密钥写入代码。

```env
ENABLE_CLAUDE=true
ANTHROPIC_API_KEY=你的密钥
CLAUDE_COMMAND=claude
```

## 演示模式

如果 `ENABLE_CLAUDE=false`，后端会返回演示分析结果。这样可以先验证 Web 页面、数据库和任务流程。

