# ERP 并行 Dispatch 案例（2026-05-05）

## 背景
老大要求测试 ERP 订单功能并修复两个小尾巴：
1. TabManager 取消按钮不重置底栏
2. total_cny 数据库一直 0.00

## 纠正前的行为（被老大批评）
先自己查根因（read_file/terminal查DB）再写 prompt → 老大说「每次都说派小弟去 最后还是自己上手」

## 纠正后的行为（老大表扬）
直接写 prompt 派小弟，0 秒自己查。

## 两路并行 Dispatch

### 任务 A：matt-grill-me → 前端建构师（修 TabManager 底栏）
- **模型**: minimax-m2.7
- **参数**: `--subprocess-timeout 600 --max-iterations 80`
- **文件**: `/tmp/async_fix_tabmanager.txt` (~2300字)
- **改动**: tab-manager.js — 取消按钮 handler 从 closeTab 改为 openUrl(详情URL)
- **耗时**: ~300秒
- **结果**: ✅ 取消后底栏正确显示编辑/删除

### 任务 B：架构审查官（修 total_cny 数据库 0.00）
- **模型**: minimax-m2.7
- **参数**: `--subprocess-timeout 600 --max-iterations 80`
- **文件**: `/tmp/async_fix_totalcny.txt` (~1900字)
- **改动**: OrderController.php — store() + update() 加 $order->refresh()
- **耗时**: ~316秒
- **结果**: ✅ total_cny 从 0.0000 → 3000.00

### 并行 Dispatch 代码
```python
# 任务 A（写 prompt → dispatch → 不等）
write_file("/tmp/async_fix_tabmanager.txt", prompt_a)
terminal(
    command="python3 ~/.hermes/skills/async-delegate/scripts/async_delegate.py"
            " --prompt-file /tmp/async_fix_tabmanager.txt"
            " --model minimax-m2.7"
            " --toolsets terminal,file"
            " --workspace /mnt/d/laragon/www/erp_project"
            " --subprocess-timeout 600 --max-iterations 80",
    background=True,
    notify_on_complete=True,
    timeout=600,
)

# 任务 B（直接第二个 dispatch，不等 A 完成）
write_file("/tmp/async_fix_totalcny.txt", prompt_b)
terminal(..., background=True, ...)
```

### 关键点
- 两个 prompt 各 <2500 字（MiniMax 128k 安全）
- 改不同文件（tab-manager.js vs OrderController.php）→ 可并行
- 秒回「派出去啦~」后继续和老大聊天
- 老大说「这回就对了 聪明」
