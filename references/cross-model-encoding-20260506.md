# 跨模型编码兼容问题（2026-05-06）

## 问题现象

子 agent 用 MiniMax 跑完后，输出中包含特殊的 Unicode 字符（零宽字符、控制字符等），当主 agent（使用 DeepSeek V4）读取 result 文件时，DeepSeek 因编码不符合规范而崩溃，整个会话不可用。

## 根因

MiniMax 的流式输出和 JSON 序列化过程中，可能产生：
- **零宽字符**：U+200B（零宽空格）、U+200C/U+200D（零宽连接符/非连接符）—— MiniMax 在格式化输出时自动插入
- **BOM**：U+FEFF —— 某些 provider 在流式输出的开头注入
- **控制字符**：0x00-0x08 等 —— 转义处理不彻底残留
- **模型专属标记**：不同的 LLM 可能在输出中添加自己的思考痕迹或标记符号

DeepSeek V4 的输入解析器对 JSON 字符串中的异常字符比较敏感，读到非法序列直接报错中断。

## 修复方案

### 第1层 — 系统消息约束（源头防）

在 async_delegate.py 的 `run_single()` 函数中，所有子 agent 的系统消息末尾追加「输出格式规范」指令：

```python
standard_format_directive = (
    "\n\n【输出格式规范】你的最终输出必须符合以下标准：\n"
    "1. 纯 UTF-8 编码，无 BOM (U+FEFF)，无控制字符（仅保留换行和制表符）\n"
    "2. 无零宽字符 (U+200B U+200C U+200D U+FEFF 等)，无模型专属标记符号\n"
    "3. 所有字符串内容标准 JSON 转义，确保可以被 json.load() 直接解析\n"
    "4. 不输出思考过程、推理痕迹、或任何标记语言包装\n"
    "5. 中文内容保持普通汉字，不使用异体字或特殊 Unicode 组合\n"
    "违反以上规范会导致下游系统崩溃，务必遵守。\n"
)
system_message += standard_format_directive
```

### 第2层 — 代码级清洗（兜底）

在将 `answer` 写入 result 文件前，调用 `_sanitize_output()` 暴力过滤：

```python
def _sanitize_output(text: str) -> str:
    import re
    # Remove BOM
    text = text.replace('\ufeff', '')
    # Remove zero-width and invisible chars
    text = re.sub(r'[\u200b\u200c\u200d\u2060\u2061\u2062\u2063\u2064\ufeff]', '', text)
    # Remove control chars except \n (0x0a), \r (0x0d), \t (0x09)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    # Remove lone surrogates (invalid in UTF-8)
    text = re.sub(r'[\ud800-\udfff]', '', text)
    return text.strip()
```

## 附带的修复

caveman directive 中的 `\n` 之前用的是 `"\\n"`（Python 字面量 → 字符串值 `\n` = 2字符：反斜杠+n），JSON 序列化后变成 `\\n`，API 收到的是字面文本 `\n` 而非真正的换行符。已改为 `"\n"`（Python 字面量 → 真正的换行符 0x0a）。

## 验证方法

```bash
# 派个小弟产生输出
echo '测试：写一段包含特殊字符的文本到 /tmp/encoding_test.txt' > /tmp/test_enc.txt
python3 ~/.hermes/skills/async-delegate/scripts/async_delegate.py \
  --prompt-file /tmp/test_enc.txt \
  --model minimax-m2.7 \
  --caveman \
  --result-file /tmp/test_result.json

# 检查 answer 是否干净
python3 -c "
import json
with open('/tmp/test_result.json') as f:
    r = json.load(f)
ans = r['answer']
# 检查是否有零宽字符
import re
zw = re.findall(r'[\u200b\u200c\u200d\ufeff]', ans)
print(f'零宽字符: {len(zw)}个')
# 检查控制字符
import unicodedata
controls = [c for c in ans if unicodedata.category(c).startswith('C') and c not in '\n\r\t']
print(f'控制字符: {len(controls)}个')
print(f'answer 长度: {len(ans)}字')
"
```

## 关键教训

- MiniMax 和 DeepSeek V4 对 Unicode 字符的容错程度不同：MiniMax 能消化某些特殊字符（或自己生成了但自己不在意），DeepSeek V4 遇到就崩
- 跨模型通信时，输出必须「取最小公倍数」——只保留所有模型都能安全解析的字符
- 两条防线（系统消息约束 + 代码清洗）比一条更可靠——模型不一定完全遵守输出格式指令
