# 🎭 Hermes async-delegate — 「小影」

> 代号「小影」—— 后台影子分身，**不阻塞主对话**

## 这是什么？

`async-delegate` 是 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 的一个技能包，用来实现**真正的异步子任务委派**。

简单说就是：**用户跟小雪聊着天，小雪派小弟去后台干活，互不耽误。**

## 动机

Hermes Agent 内置的 `delegate_task` 会阻塞主对话——用户问个问题，助手派了个任务出去，然后就只能干等着。这在需要并行处理多个任务，或者任务耗时长（改代码、查资料、批量操作）时，体验很差。

「小影」解决的就是这个问题：**说派就派，秒回用户，后台跑完了再汇报。**

## 核心能力

| 能力 | 说明 |
|------|------|
| ⚡ **不阻塞** | dispatch 后立刻回复用户，对话继续 |
| 🔄 **并行派发** | 一次派多个小弟同时干不同的活 |
| 🧹 **跨模型兼容** | 自动读取 Hermes 主模型配置，输出自动清洗，MiniMax↔DeepSeek 互传不崩 |
| 📁 **结果文件输出** | `--result-file` 结构化结果写入 JSON 文件 |
| 🪆 **嵌套委派** | `--nested` 小弟还可以派自己的小弟 |
| 🦴 **原始人模式** | `--caveman` 短 prompt、省 token、快速迭代（依赖 Hermes `matt-caveman` 技能） |

## 工作流

```
用户说"派小弟去" 
  → 秒写 prompt（<2500字）
  → terminal(background=True, notify_on_complete=True)
  → 秒回"派出去啦~"
  → 继续跟用户聊别的
  → 后台跑完自动通知结果
```

## 第一原则：说派就派，绝不上手

这是这个技能最重要的设计哲学——

> ❌ 不要自己先读代码查根因再派
> ❌ 不要自己先跑 terminal 验证再派
> ❌ 不要口头答应派，然后自己默默把活干了
>
> ✅ 看到 trigger → 秒写 prompt → dispatch → 秒回

用户一眼就能看出你是真派了小弟，还是自己闷头搞了半天才想起派人。**这在小雪的用户面前，是完全不一样的体验。**

## 用例场景

- 🛠️ **改代码**：用户报 bug，派小弟去查代码 + 修 bug，自己继续跟用户聊
- 📊 **批量操作**：同时派多个小弟处理不同文件
- 🔍 **查资料**：派小弟去翻文档、搜数据，回来汇报
- 🧪 **测试验证**：派小弟跑测试，自己继续设计下一个功能

## 文件结构

```
async-delegate/
├── SKILL.md               # 技能主文档（触发词、规则、调用模板）
├── scripts/
│   └── async_delegate.py  # Python 调度脚本（v10）
├── references/
│   ├── delegation-architecture-debate-20260505.md
│   ├── erp-parallel-dispatch-20260505.md
│   ├── sub-agent-js-quality-patterns.md
│   └── subagent-frontend-js-pitfalls-20260505.md
└── test-prompts.json      # 测试用例
```

## 技术细节

- **触发方式**：`terminal(background=True, notify_on_complete=True)`
- **默认模型**：自动跟随 Hermes 主配置（当前为 `deepseek-v4-flash`），无需手动指定 `--model`
- **超时控制**：短任务 600s / 80 次迭代，长任务可调
- **并行上限**：不同文件/任务可同时派发
- **输出清洗**：自动去除控制字符、零宽字符、BOM，确保跨模型兼容

---

> 「每次都说派小弟去，最后还是自己上手」—— 这句吐槽就是小影诞生的原点。
>
> 从此以后，小雪说派就派。
