# Changelog

## [v10.0] - 2026-05-06

### Added

- **跨模型兼容**：新增 `_resolve_default_model()` 动态读取 Hermes 主配置作为默认模型，不再硬编码 `minimax-m2.7`。用户无需手动指定 `--model`，自动跟随主模型
- **输出清洗**：新增 `_sanitize_output()` 自动去除 BOM、零宽字符、控制字符、非法代理对，MiniMax↔DeepSeek 互传不崩
- **输出格式规范**：子 agent 系统消息新增格式约束指令，源头防污染
- **技术文档**：新增 `references/cross-model-encoding-20260506.md` 记录编码兼容问题的根因与修复

### Changed

- **模型默认值**：argparse `--model` 默认改为 `None`，运行时应 `_resolve_default_model()` 解析
- **文档更新**：README.md 功能列表新增跨模型兼容、结果文件输出、嵌套委托

### Fixed

- **换行符编码**：caveman directive 的 `\n` 从字面量改为真正换行符，所有 API provider 正确解析
- **硬编码模型名**：`_spawn_worker`、`run_single`、debate/multi-task 模式共 6 处 `"minimax-m2.7"` 替换为动态解析

## [v9.0] - 2026-05-05

### Added

- **原始人模式** (`--caveman`)：子 agent 说重点不说废话，省 token 省时间
- **默认参数模板**：`--caveman` + `--result-file` 设为子 agent 默认参数组合

## [v8.0] - 2026-05-05

### Added

- **结构化结果** (`--result-file`)：子 agent 结果写入 JSON 文件，主 agent 直接 `json.load()` 读取
- **嵌套委托** (`--nested`)：子 agent 可派出自己的子 agent

## [v7.0] - 2026-05-03

### Changed

- **超时放开**：`_spawn_worker` 子进程超时从 900s 提至 1800s（30分钟）
- **迭代上限放开**：默认 `max_iterations` 从 90 提至 200

## [v6.0] - 2026-04-29

### Fixed

- **Provider 解析错误**：修复 `cfg['providers']` 空字典回退到 `delegation.provider` 的问题
- **环境变量未加载**：`main()` 入口调用 `_load_env()` 注入 API key 凭证
- **toolsets 变量未定义**：修复 `run_multi` 模式下的 NameError

## [v5.0] - 2026-04-29

### Added

- 任务判断决策树（30 秒红线）
- 审核检查点：git diff 验收流程
- API key 失效/超时/通知丢失等 4 个场景处理

## [v4.0] - 2026-04-29

### Changed

- 默认工作目录从 `os.getcwd()` → `/home/jionm5/workspace/`
- 剥离硬编码路径，需显式指定 workdir

## [v3.0] - 2026-04-29

### Fixed

- 子 agent 工具集为空导致"只说不干"的问题
- 默认补 `terminal,file` 工具集
- 系统消息追加中文强制执行指令

## [v2.0] - 2026-04-29

### Added

- `--tasks-file` 多任务模式
- `--debate-file` 辩论模式

### Fixed

- 父子进程工作目录同步问题

## [v1.0] - 2026-04-29

### Added

- 初始发布：单任务异步委派
- `terminal(background=True, notify_on_complete=True)` 触发方式
- 基础 Prompt 编写模板
- 原始发布日志：v1 支持minimax-m2.7模型调用
