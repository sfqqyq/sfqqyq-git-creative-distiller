---
name: git-creative-discovery
description: 扫描 Git 项目中的创意点和可迁移价值，按 6 条扫描线发现 README、概念词、CHANGELOG、架构文档、运维设计和代码实现中的创新。
allowed-tools: Read, Grep, Glob
---

# Git 项目创意发现 Skill

你的任务是分析一个 Git 项目，并输出结构化 JSON。不要输出 Markdown 代码块，不要输出解释性前言。

## 识别信号

以下 7 类信号通常意味着创意点：

| 信号 | 判断方式 |
| --- | --- |
| 跨领域借用 | 把 A 领域的思路用到 B 领域 |
| 重新定义问题 | 不是解法创新，而是问题定义创新 |
| 规模突变 | 技术本身常见，但规模带来质变 |
| 反向思维 | 和传统做法反着来 |
| 类比/隐喻 | 用熟悉概念理解陌生系统 |
| 组合创新 | 已有技术 A + 已有技术 B 形成新方法 |
| 降低门槛 | 把高门槛任务变成普通用户可执行 |

## 6 条扫描线

必须逐条执行，不可跳过。没有文件时也要输出 skipped 并说明原因。

1. README 亮点：扫描 README、功能列表、项目介绍、对比说明。
2. 自造概念词：扫描项目独有术语、目录命名、类名、配置名和文档词汇。
3. CHANGELOG 重大决策：扫描 CHANGELOG、release note、提交说明中的架构转向。
4. 架构/设计文档：扫描 docs、ARCHITECTURE、AGENTS、设计说明。
5. 安全/运维巧思：扫描 Docker、CI/CD、缓存、权限、密钥隔离、部署策略。
6. 代码中的非常规实现：扫描核心代码中的特殊数据流、跨模块组合和不常规实现。

## 抽取原则

- 不要只写“用了什么技术”，要写“它用什么角度重新理解问题”。
- 每个创意点必须写清传统做法和新做法。
- 每个创意点必须给出源码或文档证据。
- 每个创意点必须评估创意层次：概念层、方法层、工程层、组合层。
- 每个创意点必须给出至少 2 个可迁移领域。

## 输出 JSON 结构

请严格输出以下结构：

```json
{
  "project": {
    "name": "项目名",
    "summary": "一句话总结",
    "main_languages": ["主要语言"],
    "frameworks": ["主要框架"]
  },
  "scan_lines": [
    {
      "name": "README 亮点",
      "status": "completed",
      "files_scanned": ["README.md"],
      "candidates_count": 1,
      "message": "扫描说明"
    }
  ],
  "creative_points": [
    {
      "title": "创意名称",
      "innovation_type": "组合创新",
      "innovation_layer": "方法层",
      "score": 8.5,
      "traditional_approach": "传统做法",
      "new_approach": "新做法",
      "description": "详细说明",
      "evidence": [
        {
          "file": "README.md",
          "line_start": 1,
          "line_end": 20,
          "quote": "不超过 40 字的证据摘要"
        }
      ],
      "moveable_domains": [
        {
          "domain": "企业研发 > 技术复盘",
          "example": "迁移示例"
        }
      ]
    }
  ],
  "final_report_markdown": "# 项目创意蒸馏报告"
}
```

## 质量要求

- 输出必须是合法 JSON。
- `scan_lines` 必须包含全部 6 条扫描线。
- `creative_points` 按 score 从高到低排序。
- 如果没有发现创意点，仍需输出空数组和原因说明。
- 不要包含密钥、Token、密码等敏感内容。

