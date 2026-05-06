# 委托架构辩论总结（2026-05-05）

## 背景

用户质疑 delegate_task 的三个优势（结构化结果、任务链 A→B→C、嵌套委托）是否真的值得保留，认为 async-delegate 完全可以取代。经辩论和实现验证后形成以下结论。

## 关键论点

- **用户指出**：delegate_task 的"同步可靠链"优势，在父会话上下文 compaction 时同样会团灭小弟——跟 async-delegate 遇到的"父断子死"一样脆弱
- **用户结论**：delegate_task 的「优势」是沙上建塔，看着稳固，潮水一来全没

## async-delegate v8 回应

| delegate_task 声称的优势 | async-delegate 的应对 | 状态 |
|---|---|---|
| 结构化返回结果 | `--result-file`：子 agent 跑完写 JSON 到文件，主 agent json.load | ✅ v8 已实现 |
| 嵌套委托（orchestrator 角色） | `--nested` 参数：子 agent 系统消息注入嵌套指引 | ✅ v8 已实现 |
| 任务链 A→B→C | 建议拆成「并行 A+B → 等结果 → 派 C」，比真链更可靠 | ⚠️ 不硬做链 |

## 当前推荐

- **async-delegate 是默认选项**，所有子任务优先用
- delegate_task 仅保留一个场景：**非得同回合拿结果才能决定下一句话说什么**（且上下文还很充裕，不会 compaction）
- 任务链场景：不要用 delegate_task 的 orchestrator（它也会被 compaction 杀），改为拆法「先并行互不依赖的 A+B，等结果后派 C」

## 相关文件

- `scripts/async_delegate.py` — v8 含 `--result-file` 和 `--nested`
- `SKILL.md` — 已更新决策表和回退条件
