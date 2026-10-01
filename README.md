# GitHub Opportunity Mining Agent

面向有开发想法、但缺少需求判断依据的独立开发者，将 GitHub Issue 整理为用户痛点、已有应对方式和带来源的机会假设，帮助开发选题。

这是可以本地运行的研究型 MVP。GitHub 反馈支持痛点研究；机会卡中的解决方案与商业价值仍需用户访谈验证。

## 产品流程

一句话研究方向 → Agent 生成研究理解与默认检索边界 → 用户确认/补充约束 → 检索与来源筛选 → 采集 Issue 和评论 → 痛点提取与聚类 → 证据检查 → 机会卡或停止原因。

以上为 `review` 模式。当前程序默认 `automatic` 模式，会自动执行边界与来源选择；自动选择不算人工审核。简历中的确认交互请用下方 review 命令演示。

## 项目贡献与对应实现

| 产品工作 | 实现与证据 |
| --- | --- |
| 设计从需求到机会卡的研究流程 | [流程编排](src/graph.py)、[机会卡生成](src/nodes/opportunity_generator.py)、[报告输出](src/nodes/reporter.py) |
| 减少前置填写：先给出研究理解和默认边界，再补充约束 | [需求理解](src/services/query_intake.py)、[确认与恢复入口](skills/github-opportunity-research/references/review-and-results.md) |
| 降低无关来源与薄弱证据干扰 | [领域相关性和成熟度](src/services/source_quality.py)、[来源筛选](src/services/github_discovery.py)、[信号评分](src/nodes/signal_scorer.py) |
| 将结果质量拆成可审核指标 | [人工评估标准](docs/evaluation/human_review_rubric_v0.1.md)、[评估现状](docs/evaluation/STATUS.md) |

详细说明：[简历与证据对应](docs/RESUME_ALIGNMENT.md)。

## 快速运行

本次整理使用 Python 3.13。项目依赖 LangGraph、Pydantic 和 OpenAI 兼容接口。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest -q
```

### 1. 离线流程演示（无需密钥）

```powershell
python -m src.runner --run-id portfolio_demo --input data/issues.json --mode mock --run-mode auto
```

查看 `outputs/runs/portfolio_demo/report_zh.md` 和 `opportunity_cards.json`。该演示使用保存的数据和 mock 模型，证明流程可运行，不代表实时检索质量。

### 2. 真实研究与用户确认

复制 `.env.example` 为 `.env`，填入自己的模型 API key 和 GitHub token。模型服务可能产生费用。

```powershell
Copy-Item .env.example .env
python skills/github-opportunity-research/scripts/research.py --project . doctor
python skills/github-opportunity-research/scripts/research.py --project . start --run-id portfolio_review --query "我想找笔记工具的机会，重点关注跨设备同步。" --mode real --interaction-mode review
```

程序会保存研究理解与默认边界并暂停。检查 `outputs/runs/portfolio_review/query_intake_review.json`，确认后将 `approval.approved` 设为 `true`，按需补充 `important_keywords` 和 `exclude_keywords`，再运行：

```powershell
python skills/github-opportunity-research/scripts/research.py --project . resume --run-id portfolio_review
```

来源审核及后续恢复见[操作说明](skills/github-opportunity-research/references/review-and-results.md)。新研究请使用新的 run ID。要体验自动模式，将启动命令的 `--interaction-mode review` 换为 `--interaction-mode automatic`。

### 3. 查看产品展示

浏览器打开 [prototype/index.html](prototype/index.html)。这是已保存案例的交互回放，未接入实时后端；编辑输入不会重新生成案例。详见[案例来源](prototype/README.md)。

## 评估与限制

- 已设计覆盖笔记工具、客服、RAG、浏览器 Agent 的 20 条需求评估方案，分 12 条开发、8 条验收。
- 已找到的评估导航记录覆盖 3 道开发题的 8 次历史运行；重复运行不等于不同题目完成，且存在待审核标签。
- 当前发布证据不足以宣称“完成 20 条实测”或“Top-5 Issue 相关率提升至 100%”。来源仓库相关性与 Issue 相关性不是同一指标。
- 单元测试检验程序行为，不能替代真实需求评估。离线样例与历史案例也不能证明当前跨领域效果。
- 检索可能偏题，旧 Issue 需要核对解决状态；零卡或停止结果应保留，不能解释为市场没有需求。

## 目录

`src/` 运行主链 · `tests/` 回归测试 · `data/` 离线与评估样例 · `skills/` 研究入口 · `prototype/` 历史回放 · `docs/` 产品贡献和评估边界。

发布删减范围及本地验证结果见 [RELEASE_NOTES](docs/RELEASE_NOTES.md)。
