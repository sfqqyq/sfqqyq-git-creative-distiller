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

## DeepSeek 接入 Claude Code

如果使用 DeepSeek 的 Claude Code 兼容接入，按下面配置：

```env
ENABLE_CLAUDE=true
CLAUDE_COMMAND=claude
ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
ANTHROPIC_AUTH_TOKEN=你的 DeepSeek API Key
ANTHROPIC_MODEL=deepseek-v4-pro[1m]
ANTHROPIC_DEFAULT_OPUS_MODEL=deepseek-v4-pro[1m]
ANTHROPIC_DEFAULT_SONNET_MODEL=deepseek-v4-pro[1m]
ANTHROPIC_DEFAULT_HAIKU_MODEL=deepseek-v4-flash
CLAUDE_CODE_SUBAGENT_MODEL=deepseek-v4-flash
CLAUDE_CODE_EFFORT_LEVEL=max
```

## 演示模式

如果 `ENABLE_CLAUDE=false`，后端会返回演示分析结果。这样可以先验证 Web 页面、数据库和任务流程。
