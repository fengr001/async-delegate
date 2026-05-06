#!/usr/bin/env python3
"""
async_delegate.py v3 — Async Hermes sub-agent delegation with multi-task + debate support.

Single task (backward compatible):
    python3 async_delegate.py "prompt" --model minimax-m2.7

Multi-task (batch mode):
    python3 async_delegate.py --tasks-file /tmp/tasks.json

Debate mode (sequential multi-round):
    python3 async_delegate.py --debate-file /tmp/debate.json

tasks.json format:
    [
      {"id": "task1", "prompt": "...", "toolsets": "terminal,file", "model": "minimax-m2.7"},
      {"id": "task2", "prompt": "...", "toolsets": "terminal,file", "model": "minimax-m2.7"}
    ]

debate.json format:
    [
      {"role": "正方", "identity": "架构审查官", "prompt": "评估方案A的可行性..."},
      {"role": "反方", "identity": "风险审计官", "prompt": "分析方案B的风险...", "reads": ["正方"]},
      {"role": "综合", "identity": "综合裁判官", "prompt": "综合双方结论，给出最终建议", "reads": ["正方", "反方"]}
    ]
"""

import argparse
import json
import os
import subprocess
import sys
import time
import tempfile
from pathlib import Path

# ── Fix hermes-agent path so hermes_cli can be imported in any Python environment ──
_AGENT_ROOT = str(Path.home() / "hermes-agent")
if _AGENT_ROOT not in sys.path:
    sys.path.insert(0, _AGENT_ROOT)


def _find_hermes_python():
    """Find the Python interpreter that has hermes_cli available."""
    candidates = [
        "/home/jionm5/hermes-agent/.venv/bin/python3",
        "/home/jionm5/hermes-agent/hermes-env/bin/python3",
    ]
    for python in candidates:
        if Path(python).exists():
            try:
                subprocess.run([python, "-c", "import hermes_cli"],
                               capture_output=True, timeout=5, check=False)
                return python
            except Exception:
                pass
    return sys.executable  # fallback


def _log(msg: str):
    print(f"[async_delegate] {msg}", file=sys.stderr, flush=True)


def _sanitize_output(text: str) -> str:
    """Strip problematic characters for cross-model compatibility.
    
    Removes: control chars (except \\n\\t), zero-width chars, BOM, surrogates.
    This prevents MiniMax-specific output from crashing DeepSeek V4 and vice versa.
    """
    import re
    # Remove BOM
    text = text.replace('\ufeff', '')
    # Remove zero-width and invisible chars
    text = re.sub(r'[\u200b\u200c\u200d\u2060\u2061\u2062\u2063\u2064\ufeff]', '', text)
    # Remove control chars except \\n (0x0a), \\r (0x0d), \\t (0x09)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    # Remove lone surrogates (invalid in UTF-8)
    text = re.sub(r'[\ud800-\udfff]', '', text)
    return text.strip()


def _resolve_default_model() -> str:
    """Read the main model from Hermes config as default for sub-agents.

    Falls back to minimax-m2.7 if config is unavailable.
    """
    try:
        from hermes_cli.config import load_config
        cfg = load_config()
        model = cfg.get("model", {}).get("default", "minimax-m2.7")
        return model or "minimax-m2.7"
    except Exception:
        return "minimax-m2.7"


def _load_env() -> dict:
    """Read ~/.hermes/.env directly without depending on hermes_cli."""
    env_path = Path.home() / ".hermes" / ".env"
    env = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _spawn_worker(task: dict, workspace: str, index: int,
                   subprocess_timeout: int = 1800, max_iterations: int = 200) -> dict:
    """Spawn a single sub-agent as a subprocess and return its result."""
    task_id = task.get("id", f"task_{index}")
    prompt = task.get("prompt", "")
    model = task.get("model") or _resolve_default_model()
    toolsets = task.get("toolsets", "")
    sysmsg = task.get("sysmsg", "")

    # Write prompt to temp file to avoid shell escaping issues
    prompt_file = tempfile.mktemp(suffix=f"_{task_id}.txt", prefix="async_task_")
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(prompt)

    _log(f"Worker {task_id}: model={model} toolsets={toolsets} "
         f"subprocess_timeout={subprocess_timeout}s max_iterations={max_iterations}")

    # Build command — use hermes venv python so hermes_cli is importable
    python_bin = _find_hermes_python()
    cmd = [
        python_bin, __file__,
        "--prompt-file", prompt_file,
        "--model", model,
        "--workspace", workspace,
        "--subprocess-timeout", str(subprocess_timeout),
        "--max-iterations", str(max_iterations),
    ]
    if toolsets:
        cmd.extend(["--toolsets", toolsets])
    if sysmsg:
        cmd.extend(["--sysmsg", sysmsg])
    # Mark as worker mode so it doesn't re-enter multi-task mode
    cmd.append("--worker")

    t0 = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=subprocess_timeout,
            cwd=workspace,
            env=os.environ.copy(),
        )
        duration = round(time.monotonic() - t0, 1)

        # Parse last line of stdout as JSON result
        stdout_lines = result.stdout.strip().split("\n")
        last_line = stdout_lines[-1] if stdout_lines else ""
        try:
            output = json.loads(last_line) if last_line else {}
        except json.JSONDecodeError:
            output = {"status": "error", "error": f"Invalid JSON output: {last_line[:200]}"}

        # Merge in metadata
        output["task_id"] = task_id
        output["duration_s"] = duration
        output["model"] = model
        if not output.get("answer"):
            output["answer"] = result.stdout.strip()[-500:] if result.stdout else "(no output)"

        # Include stderr for debugging
        if result.stderr:
            output["stderr"] = result.stderr.strip()[-500:]

    except subprocess.TimeoutExpired:
        output = {
            "task_id": task_id,
            "status": "timeout",
            "error": f"Worker {task_id} timed out after 900s",
            "duration_s": 900,
        }
    except Exception as e:
        output = {
            "task_id": task_id,
            "status": "error",
            "error": str(e),
        }
    finally:
        # Cleanup temp file
        try:
            os.unlink(prompt_file)
        except OSError:
            pass

    return output


def run_single(args):
    """Original single-task mode (backward compatible)."""
    # Resolve prompt source
    if args.prompt_file:
        with open(os.path.expanduser(args.prompt_file), "r", encoding="utf-8") as fh:
            args.prompt = fh.read()
    elif not args.prompt:
        print(json.dumps({"status": "error",
                          "error": "Either prompt or --prompt-file is required"}))
        sys.exit(1)

    if not args.prompt.strip():
        print(json.dumps({"status": "error", "error": "Empty prompt"}))
        sys.exit(1)

    workspace = os.path.abspath(args.workspace) if args.workspace else os.path.expanduser("/home/jionm5/workspace")
    os.makedirs(workspace, exist_ok=True)

    # Collect toolsets — initialize first, then apply args override, then fallback to defaults
    toolsets = []
    if args.toolsets:
        toolsets = [t.strip() for t in args.toolsets.split(",") if t.strip()]
    # Default toolsets — never leave subagent without tools
    if not toolsets:
        toolsets = ["terminal", "file"]

    # Resolve the model provider
    from hermes_cli.config import load_config
    from hermes_cli.runtime_provider import resolve_runtime_provider

    cfg = load_config()
    model_name = args.model or _resolve_default_model()
    provider_name = None
    base_url = None

    # Check if model is in "provider/model" format (e.g. "deepseek/minimax-m2.7")
    if "/" in model_name:
        parts = model_name.split("/", 1)
        provider_name = parts[0]
        model_name = parts[1]
    else:
        # Use the main model provider from config as default
        provider_name = cfg.get("model", {}).get("provider", "deepseek")

    # Resolve runtime credentials for the determined provider
    rt = resolve_runtime_provider(requested=provider_name)
    api_key = rt.get("api_key")
    base_url = rt.get("base_url", "")

    if not api_key:
        print(json.dumps({"status": "error",
                          "error": f"No API key found for provider '{provider_name}'"}))
        sys.exit(1)

    _log(f"Using model={model_name} provider={provider_name} toolsets={toolsets}")
    _log(f"Workspace: {workspace}")

    # Build system message
    sysmsg = args.sysmsg or ""
    workspace_tag = f"[Workspace: {workspace}]\n"
    workspace_system = (
        f"Active workspace: {workspace}\n"
        "Every user message is prefixed with [Workspace: ...] indicating the working directory. "
        "This tag is the single authoritative source of the active workspace."
    )
    
    # CRITICAL: Force tool usage — prevents "plan-only" output
    tool_usage_directive = (
        "\n\n【重要】你必须实际操作文件来完成任务，不要只输出计划。\n"
        "你有完整的工具集可用（terminal/file/write_file等），请直接执行，不要描述你将怎么做。\n"
        "完成实际修改后再用工具验证结果。\n"
    )
    
    if sysmsg:
        system_message = f"{sysmsg}\n\n{workspace_system}{tool_usage_directive}"
    else:
        system_message = f"{workspace_system}{tool_usage_directive}"

    # ── Nested delegation directive ──
    if args.nested:
        nested_directive = (
            "\n\n【嵌套委托】你有能力派出自己的子 agent。"
            "当你遇到可以并行或独立的子任务时，可以：\n"
            "1. 将子任务的 prompt 写入临时文件（write_file）\n"
            "2. 调用下方命令派出子 agent：\n"
            "   python3 ~/.hermes/skills/async-delegate/scripts/async_delegate.py "
            f"--prompt-file <文件路径> --model {_resolve_default_model()} "
            "--subprocess-timeout 600 --max-iterations 80\n"
            "3. 收集子 agent 的 stdout 输出并整合到你自己的最终输出中\n"
            "注意：子 agent 没有对话记忆，prompt 要自包含。"
            "不要派链式依赖（A→B→C），只派独立并行任务。\n"
        )
        system_message += nested_directive

    # ── Caveman mode directive ──
    if args.caveman:
        caveman_directive = (
            "\n\n【原始人模式】说重点，省话。每个回复必须精简。"
            "步骤用箭头简写(X→Y)。省冠词(一个/这个/那个)、语气词(哈/呢/吧)。"
            "只输出实际改动、代码和验证结果。不要解释，不要预热，不要总结。"
            "技术术语保持准确。代码块不变。错误原文引用。\n"
        )
        system_message += caveman_directive

    # ── Standard output format directive (cross-model compatibility) ──
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

    user_message = f"{workspace_tag}{args.prompt}"

    # Run the agent
    from run_agent import AIAgent

    _log("Creating agent and running conversation...")
    t0 = time.monotonic()

    agent = AIAgent(
        model=model_name,
        provider=provider_name,
        base_url=base_url,
        api_key=api_key,
        platform="webui",
        quiet_mode=True,
        enabled_toolsets=toolsets,
        max_iterations=args.max_iterations,
    )

    result = agent.run_conversation(
        user_message=user_message,
        system_message=system_message,
        conversation_history=[],
    )

    duration = round(time.monotonic() - t0, 1)
    raw_answer = result.get("final_response") or "(no answer produced)"
    # ── Sanitize output for cross-model compatibility ──
    answer = _sanitize_output(raw_answer)
    completed = result.get("completed", True)

    _log(f"Completed in {duration}s")

    output = {
        "status": "done" if completed else "partial",
        "answer": answer,
        "duration_s": duration,
        "model": args.model or _resolve_default_model(),
    }
    print(json.dumps(output))

    # ── Write result file if requested ──
    if args.result_file:
        result_path = os.path.abspath(args.result_file)
        try:
            with open(result_path, "w", encoding="utf-8") as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
            _log(f"Result written to {result_path}")
        except Exception as e:
            _log(f"Failed to write result file {result_path}: {e}")


def run_debate(debate_file: str, workspace: str,
               subprocess_timeout: int = 1800, max_iterations: int = 200):
    """
    Sequential multi-agent debate with reading cross-injection.

    Each round:
      1. Inject the conclusions of agents listed in its "reads" field
      2. Spawn a single worker with the augmented prompt
      3. Store its conclusion for subsequent rounds
      4. Print combined results at the end
    """
    with open(os.path.expanduser(debate_file), "r", encoding="utf-8") as f:
        rounds = json.load(f)

    if not isinstance(rounds, list):
        print(json.dumps({"status": "error", "error": "debate-file must contain a JSON array"}))
        sys.exit(1)

    # conclusions: role -> {"identity": "...", "conclusion": "..."}
    conclusions: dict = {}

    for i, round_def in enumerate(rounds):
        role = round_def.get("role", f"round_{i}")
        identity = round_def.get("identity", role)
        base_prompt = round_def.get("prompt", "")
        reads: list = round_def.get("reads", [])

        _log(f"Debate round [{i}] {role} ({identity}): reading {reads}")

        # Build context injection from prior conclusions
        context_lines = []
        for prior_role in reads:
            if prior_role in conclusions:
                c = conclusions[prior_role]
                context_lines.append(
                    f"\n\n=== 【{c['identity']} 的结论】（{c['role']}）===\n{c['conclusion']}"
                )

        if context_lines:
            context_block = "\n".join(context_lines)
            # Inject context before the agent's own task
            full_prompt = (
                f"{context_block}\n\n"
                f"=== 你的任务 ===\n"
                f"{base_prompt}"
            )
        else:
            full_prompt = base_prompt

        # Run single agent with injected prompt
        task = {
            "id": f"debate_{role}",
            "prompt": full_prompt,
            "model": round_def.get("model") or _resolve_default_model(),
            "toolsets": round_def.get("toolsets", "terminal,file"),
            "sysmsg": f"你是「{identity}」。{round_def.get('sysmsg', '')}",
        }

        result = _spawn_worker(task, workspace, i,
                               subprocess_timeout=subprocess_timeout,
                               max_iterations=max_iterations)
        task_status = result.get("status", "error")

        if result.get("status") == "done":
            conclusion_text = result.get("answer", "(no answer)")
        elif result.get("status") == "error":
            conclusion_text = f"[错误] {result.get('error', 'unknown')} | stderr: {result.get('stderr', '')}"
        else:
            conclusion_text = f"[{task_status}] {result.get('answer', '')}"

        conclusions[role] = {
            "role": role,
            "identity": identity,
            "conclusion": conclusion_text,
            "status": task_status,
            "duration_s": result.get("duration_s", 0),
        }

        _log(f"  → {role} done ({result.get('duration_s', 0)}s, status={task_status})")

    # Print all conclusions as JSON
    output = {
        "status": "done",
        "debate": True,
        "rounds": list(conclusions.values()),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def run_multi(tasks_file: str, workspace: str,
              subprocess_timeout: int = 1800, max_iterations: int = 200):
    """Multi-task mode: load tasks from JSON, spawn workers, collect results."""
    with open(os.path.expanduser(tasks_file), "r", encoding="utf-8") as f:
        tasks = json.load(f)

    if not isinstance(tasks, list):
        print(json.dumps({"status": "error", "error": "tasks-file must contain a JSON array"}))
        sys.exit(1)

    _log(f"Multi-task mode: {len(tasks)} tasks to dispatch")
    for i, task in enumerate(tasks):
        task_id = task.get("id", f"task_{i}")
        model = task.get("model") or _resolve_default_model()
        toolsets = task.get("toolsets", "")
        _log(f"  [{i}] {task_id}: model={model} toolsets={toolsets}")

    # Spawn all workers in parallel
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from functools import partial
    worker_fn = partial(_spawn_worker,
                        subprocess_timeout=subprocess_timeout,
                        max_iterations=max_iterations)
    results = {}
    with ThreadPoolExecutor(max_workers=min(len(tasks), 5)) as executor:
        future_map = {
            executor.submit(worker_fn, task, workspace, i): task.get("id", f"task_{i}")
            for i, task in enumerate(tasks)
        }
        for future in as_completed(future_map):
            task_id = future_map[future]
            try:
                result = future.result()
            except Exception as e:
                result = {"task_id": task_id, "status": "error", "error": str(e)}
            results[task_id] = result

    # Build combined output
    all_done = all(r.get("status") == "done" for r in results.values())
    combined = {
        "status": "done" if all_done else "partial",
        "multi": True,
        "task_count": len(tasks),
        "results": results,
        "summary": {
            "done": sum(1 for r in results.values() if r.get("status") == "done"),
            "error": sum(1 for r in results.values() if r.get("status") == "error"),
            "timeout": sum(1 for r in results.values() if r.get("status") == "timeout"),
        },
    }
    print(json.dumps(combined))


def main():
    # ── Load .env into environment FIRST so all sub-processes inherit API keys ──
    # Always load, regardless of mode (dispatcher OR worker subprocess needs it)
    for k, v in _load_env().items():
        os.environ.setdefault(k, v)

    parser = argparse.ArgumentParser(description="Async Hermes sub-agent delegation")
    parser.add_argument("prompt", nargs="?", default=None,
                        help="The task prompt for the sub-agent")
    parser.add_argument("--prompt-file", default=None,
                        help="Read prompt from file")
    parser.add_argument("--tasks-file", default=None,
                        help="JSON file with array of task definitions (multi-task mode)")
    parser.add_argument("--model", default=None,
                        help="Model for sub-agent (default: reads from Hermes config)")
    parser.add_argument("--workspace", default=None,
                        help="Working directory")
    parser.add_argument("--toolsets", default=None,
                        help="Comma-separated toolset names")
    parser.add_argument("--sysmsg", default=None,
                        help="Optional system message prefix")
    parser.add_argument("--subprocess-timeout", type=int, default=1800,
                        help="Subprocess timeout in seconds (default: 1800 = 30 min)")
    parser.add_argument("--max-iterations", type=int, default=200,
                        help="Max tool-calling iterations for subagent (default: 200)")
    parser.add_argument("--result-file", default=None,
                        help="Write structured output JSON to this file path (for single-task mode)")
    parser.add_argument("--nested", action="store_true",
                        help="Enable nested delegation: sub-agent can spawn its own sub-agents via async_delegate.py")
    parser.add_argument("--caveman", action="store_true",
                        help="Caveman mode: sub-agent responds terse, no fluff")
    parser.add_argument("--worker", action="store_true",
                        help=argparse.SUPPRESS)  # Internal: marks subprocess worker
    parser.add_argument("--debate-file", default=None,
                        help="JSON file with debate rounds (sequential multi-agent)")
    args = parser.parse_args()

    workspace = os.path.abspath(args.workspace) if args.workspace else os.path.expanduser("/home/jionm5/workspace")
    os.makedirs(workspace, exist_ok=True)

    # Multi-task mode
    if args.tasks_file and not args.worker:
        run_multi(args.tasks_file, workspace,
                  subprocess_timeout=args.subprocess_timeout,
                  max_iterations=args.max_iterations)
        return

    # Debate mode
    if args.debate_file and not args.worker:
        run_debate(args.debate_file, workspace,
                   subprocess_timeout=args.subprocess_timeout,
                   max_iterations=args.max_iterations)
        return

    # Single-task mode (original behavior)
    run_single(args)


if __name__ == "__main__":
    main()
