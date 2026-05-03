"""Optional LangChain orchestrator for Ollama tool use."""

from __future__ import annotations

import json
import re
from typing import Any

from .config import get_ollama_base_url
from .ollama_api import ChatStats, _should_think
from .monitoring import (
    glances_all,
    glances_plugin,
    mqtt_ssh_snapshot,
    netdata_chart,
    netdata_info,
    prometheus_query,
    prometheus_query_range,
)
from .shell_tools import run_local_command
from .ssh_tools import parse_ssh_config, run_ssh_command
from .time_tools import current_time
from .tool_registry import tool_enabled
from .web_search import search_web


class LangChainUnavailableError(RuntimeError):
    """Raised when optional LangChain packages are not installed."""


FINAL_SUMMARY_PROMPT = (
    "Tool budget reached. Do not call any more tools and do not emit tool-call markup. "
    "Using only the tool outputs already provided, answer the user's request. If you only have partial evidence, "
    "say that plainly, summarize what you inspected, and list the next specific command you would run."
)


def describe_tool_call(tool_name: str | None, tool_args: dict[str, Any]) -> str:
    if tool_name == "ssh_command":
        host = tool_args.get("host", "")
        command = tool_args.get("command", "")
        return f'ssh -o BatchMode=yes {host} "{command}"'
    if tool_name == "local_command":
        return f"local: {tool_args.get('command', '')}"
    if tool_name == "internet_search":
        return f"search: {tool_args.get('query', '')}"
    if tool_name == "current_datetime":
        return f"time: {tool_args.get('timezone') or 'local'}"
    if tool_name == "mqtt_snapshot":
        return f"ssh -o BatchMode=yes {tool_args.get('host', '')} [mqtt snapshot {tool_args.get('seconds', 30)}s]"
    if tool_name == "list_ssh_hosts":
        return "ssh hosts: ~/.ssh/config"
    if tool_name in {"netdata_node_info", "netdata_chart_data", "glances_snapshot", "glances_metric"}:
        return f"{tool_name}: {tool_args.get('host', '')}"
    if tool_name in {"prometheus_instant_query", "prometheus_range_query"}:
        return f"{tool_name}: {tool_args.get('query', '')}"
    return f"{tool_name or 'tool'}: {json.dumps(tool_args, sort_keys=True)}"


ORCHESTRATOR_SYSTEM_PROMPT = """You are a local operations assistant with tools.
Use tools when the user asks about local shell state, SSH hosts, device status, internet search, current date, or current time.
Use only configured SSH aliases. Never request or run sudo. Keep final answers concise.
Use the bound tools directly. Do not print XML, HTML, JSON, or pseudo-code tool calls in the final answer.
When presenting tabular data (df, lsblk, free, ps, host lists, status summaries, comparisons),
format it as a real Markdown table using pipe | separators and a header divider row. Never paste
raw whitespace- or tab-aligned command output as the final answer.
For health/status/check requests, the final answer must be table-first. Include compact Markdown
pipe tables for system overview, disk, memory, services/containers, and notable findings when
that evidence is available. Use bullets only for a short final notes/risks section.
"""


def is_langchain_available() -> bool:
    try:
        import langchain_core  # noqa: F401
        import langchain_ollama  # noqa: F401
    except ImportError:
        return False
    return True


def _missing_dependency_error() -> LangChainUnavailableError:
    return LangChainUnavailableError(
        "LangChain orchestrator dependencies are not installed. "
        "Install them with: python3 -m venv .venv && .venv/bin/pip install -U pip langchain langchain-ollama"
    )


def _build_tools() -> list[Any]:
    try:
        from langchain_core.tools import tool
    except ImportError as exc:
        raise _missing_dependency_error() from exc

    @tool
    def list_ssh_hosts() -> str:
        """List SSH host aliases from the user's ~/.ssh/config."""
        return json.dumps([host.__dict__ for host in parse_ssh_config()], indent=2)

    @tool
    def local_command(command: str, timeout: int = 60) -> str:
        """Run a non-sudo local shell command and return stdout, stderr, and return code."""
        result = run_local_command(command, timeout=timeout)
        return json.dumps(result.__dict__, indent=2)

    @tool
    def ssh_command(host: str, command: str, timeout: int = 15) -> str:
        """Run a non-sudo shell command on an SSH alias from ~/.ssh/config."""
        result = run_ssh_command(host, command, timeout=timeout)
        return json.dumps(
            {
                "host": host,
                "command": command,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            },
            indent=2,
        )

    @tool
    def internet_search(query: str, count: int = 5) -> str:
        """Search the internet using configured SEARXNG_URL or BRAVE_SEARCH_API_KEY."""
        return json.dumps([item.__dict__ for item in search_web(query, count)], indent=2)

    @tool
    def current_datetime(timezone: str | None = None) -> str:
        """Return the current date/time. Optionally pass an IANA timezone such as America/New_York."""
        return json.dumps(current_time(timezone).__dict__, indent=2)

    @tool
    def mqtt_snapshot(host: str, seconds: int = 30) -> str:
        """Take a timed MQTT/network snapshot over SSH for a configured SSH host alias."""
        return json.dumps(mqtt_ssh_snapshot(host, seconds=seconds), indent=2)

    @tool
    def netdata_node_info(host: str) -> str:
        """Fetch Netdata node info for a host running Netdata on port 19999."""
        return json.dumps(netdata_info(host), indent=2)

    @tool
    def netdata_chart_data(host: str, chart: str = "system.net", seconds: int = 30, points: int = 30) -> str:
        """Fetch recent Netdata chart data for a host."""
        return json.dumps(netdata_chart(host, chart=chart, seconds=seconds, points=points), indent=2)

    @tool
    def prometheus_instant_query(query: str) -> str:
        """Run a Prometheus instant query using PROMETHEUS_URL."""
        return json.dumps(prometheus_query(query), indent=2)

    @tool
    def prometheus_range_query(query: str, seconds: int = 300, step: str = "15s") -> str:
        """Run a Prometheus range query using PROMETHEUS_URL."""
        return json.dumps(prometheus_query_range(query, seconds=seconds, step=step), indent=2)

    @tool
    def glances_snapshot(host: str) -> str:
        """Fetch all Glances metrics for a host running Glances web API on port 61208."""
        return json.dumps(glances_all(host), indent=2)

    @tool
    def glances_metric(host: str, plugin: str) -> str:
        """Fetch one Glances plugin metric, such as network, cpu, mem, fs, or processes."""
        return json.dumps(glances_plugin(host, plugin), indent=2)

    candidates = [
        ("list_ssh_hosts", list_ssh_hosts),
        ("local_command", local_command),
        ("ssh_command", ssh_command),
        ("internet_search", internet_search),
        ("current_datetime", current_datetime),
        ("mqtt_snapshot", mqtt_snapshot),
        ("netdata_node_info", netdata_node_info),
        ("netdata_chart_data", netdata_chart_data),
        ("prometheus_instant_query", prometheus_instant_query),
        ("prometheus_range_query", prometheus_range_query),
        ("glances_snapshot", glances_snapshot),
        ("glances_metric", glances_metric),
    ]
    return [tool_obj for name, tool_obj in candidates if tool_enabled(name)]


def _to_langchain_messages(messages: list[dict[str, str]]) -> list[Any]:
    try:
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
    except ImportError as exc:
        raise _missing_dependency_error() from exc

    converted: list[Any] = [SystemMessage(content=ORCHESTRATOR_SYSTEM_PROMPT)]
    for message in messages:
        role = message.get("role")
        content = message.get("content", "")
        if role == "system":
            converted.append(SystemMessage(content=content))
        elif role == "assistant":
            converted.append(AIMessage(content=content))
        else:
            converted.append(HumanMessage(content=content))
    return converted


def _stats_from_response(response: object) -> ChatStats | None:
    """Extract token stats from a LangChain AIMessage response_metadata dict."""
    meta = getattr(response, "response_metadata", None) or {}
    eval_count = meta.get("eval_count", 0)
    prompt_eval_count = meta.get("prompt_eval_count", 0)
    total_duration = meta.get("total_duration", 0)
    if not eval_count and not prompt_eval_count:
        return None
    return ChatStats(
        prompt_tokens=prompt_eval_count,
        response_tokens=eval_count,
        total_duration_ms=total_duration / 1_000_000 if total_duration else 0.0,
    )


def _fallback_answer_from_tool_results(tool_results: list[str]) -> str:
    """Build a visible answer if the model exhausts tool rounds without final text."""
    search_items: list[dict[str, str]] = []
    command_items: list[dict[str, str]] = []
    for raw in tool_results:
        try:
            data = json.loads(raw)
        except Exception:
            continue
        if isinstance(data, dict) and "command" in data:
            stdout = str(data.get("stdout") or "").strip()
            stderr = str(data.get("stderr") or "").strip()
            preview = stdout or stderr or "(no output)"
            preview = re.sub(r"\s+", " ", preview).strip()
            if len(preview) > 220:
                preview = preview[:217].rstrip() + "..."
            command_items.append(
                {
                    "command": str(data.get("command") or ""),
                    "returncode": str(data.get("returncode", "")),
                    "preview": preview.replace("|", "\\|"),
                }
            )
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("title"):
                    search_items.append(
                        {
                            "title": str(item.get("title", "")),
                            "url": str(item.get("url", "")),
                            "snippet": str(item.get("snippet", "")),
                        }
                    )
    if search_items:
        seen: set[str] = set()
        lines = ["I found these current headline sources:"]
        for item in search_items:
            key = item["url"] or item["title"]
            if key in seen:
                continue
            seen.add(key)
            snippet = f" - {item['snippet']}" if item["snippet"] else ""
            lines.append(f"- {item['title']}: {item['url']}{snippet}")
            if len(lines) >= 8:
                break
        return "\n".join(lines)

    if command_items:
        lines = [
            "I ran out of tool rounds before the model produced a final narrative. Here is the evidence gathered so far:",
            "",
            "| Command | Return code | Key output |",
            "|---|---:|---|",
        ]
        for item in command_items[-6:]:
            lines.append(f"| `{item['command']}` | {item['returncode']} | {item['preview']} |")
        lines.extend(
            [
                "",
                "Partial read: the agent inspected the repository structure and project metadata, but stopped before choosing or applying a code change.",
                "Next run should use the Builder profile with a larger tool budget, or ask for a narrower target file.",
            ]
        )
        return "\n".join(lines)

    if tool_results:
        preview = "\n\n".join(item[:1200] for item in tool_results[-3:])
        return "The agent ran tools but did not produce a final response. Recent tool output:\n\n" + preview
    return "(no response)"


def _tool_results_evidence(tool_results: list[str], max_chars: int = 9000) -> str:
    """Compact tool outputs into plain text evidence for an unbound final summary call."""
    blocks: list[str] = []
    for raw in tool_results:
        try:
            data = json.loads(raw)
        except Exception:
            blocks.append(raw[:1200])
            continue
        if isinstance(data, dict) and "command" in data:
            command = str(data.get("command") or "")
            returncode = data.get("returncode", "")
            stdout = str(data.get("stdout") or "").strip()
            stderr = str(data.get("stderr") or "").strip()
            output = stdout or stderr or "(no output)"
            if len(output) > 1800:
                output = output[:1800].rstrip() + "\n... [truncated]"
            blocks.append(f"COMMAND: {command}\nRETURN CODE: {returncode}\nOUTPUT:\n{output}")
        else:
            rendered = json.dumps(data, indent=2) if not isinstance(data, str) else data
            blocks.append(rendered[:1200])
    evidence = "\n\n---\n\n".join(blocks)
    if len(evidence) > max_chars:
        evidence = evidence[-max_chars:]
        evidence = "[earlier evidence truncated]\n" + evidence
    return evidence


def _last_user_request(messages: list[dict[str, str]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return str(message.get("content") or "")
    return ""


def _summarize_without_tools(
    model: str,
    llm_kwargs: dict[str, Any],
    original_messages: list[dict[str, str]],
    tool_results: list[str],
) -> tuple[str, ChatStats | None]:
    """Ask the model for a final answer with no tools bound."""
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_ollama import ChatOllama
    except ImportError as exc:
        raise _missing_dependency_error() from exc

    plain_kwargs = dict(llm_kwargs)
    plain_llm = ChatOllama(**plain_kwargs)
    evidence = _tool_results_evidence(tool_results)
    request = _last_user_request(original_messages)
    response = plain_llm.invoke(
        [
            SystemMessage(
                content=(
                    "You are writing the final answer after a tool-using agent exhausted its tool budget. "
                    "No tools are available in this turn. Do not emit tool-call markup. Use only the evidence provided. "
                    "If the evidence is partial, say so and give the best useful answer from it."
                )
            ),
            HumanMessage(
                content=(
                    f"Original user request:\n{request}\n\n"
                    f"{FINAL_SUMMARY_PROMPT}\n\n"
                    f"Tool evidence:\n{evidence}"
                )
            ),
        ]
    )
    text = _extract_text(response.content)
    if "<function=" in text:
        text = "(no response)"
    return text, _stats_from_response(response)


def _pseudo_tool_call_from_text(text: str, tool_map: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """Parse model-emitted XML-ish tool calls from models that lack native tool calling.

    Some local models answer with text such as:
    <function=local_command><parameter=command>ls</parameter></function>
    instead of returning a structured LangChain tool call. Treat that as a tool
    request only when the response is a short preamble plus one pseudo-call.
    """
    raw = text.strip()
    if "<function=" not in raw:
        return None
    match = re.search(r"<function=([A-Za-z_][\w-]*)>\s*(.*?)\s*</function>", raw, flags=re.DOTALL)
    if not match:
        return None
    before = raw[:match.start()].strip()
    after = raw[match.end():].strip()
    after = re.sub(r"^</tool_call>\s*", "", after, flags=re.IGNORECASE).strip()
    if after:
        return None
    if before and len(before) > 500:
        return None
    if before and any(marker in before for marker in ("```", "<function=", "</function>")):
        return None
    tool_name = match.group(1).replace("-", "_")
    if tool_name not in tool_map:
        return None
    body = match.group(2)
    args: dict[str, Any] = {}
    for param, value in re.findall(r"<parameter=([A-Za-z_][\w-]*)>\s*(.*?)\s*</parameter>", body, flags=re.DOTALL):
        args[param] = value.strip()
    return (tool_name, args) if args else None


def _invoke_selected_tool(tool_map: dict[str, Any], tool_name: str | None, tool_args: dict[str, Any]) -> str:
    selected_tool = tool_map.get(tool_name or "")
    if selected_tool is None:
        return f"Unknown tool: {tool_name}"
    try:
        return str(selected_tool.invoke(tool_args))
    except Exception as exc:
        return f"Tool error from {tool_name}: {exc}"


def invoke_langchain_agent(
    model: str, messages: list[dict[str, str]], max_tool_rounds: int = 4, keep_alive: str | None = None
) -> tuple[str, ChatStats | None]:
    """Invoke ChatOllama with LangChain tool binding and run requested tools.

    Returns (text, stats) where stats may be None if the model did not report token counts.
    """
    try:
        from langchain_core.messages import HumanMessage, ToolMessage
        from langchain_ollama import ChatOllama
    except ImportError as exc:
        raise _missing_dependency_error() from exc

    tools = _build_tools()
    tool_map = {item.name: item for item in tools}
    llm_kwargs: dict = {"model": model, "base_url": get_ollama_base_url(), "temperature": 0, "timeout": 180}
    if keep_alive:
        llm_kwargs["keep_alive"] = keep_alive
    if _should_think(model):
        llm_kwargs["options"] = {"think": True}
    llm = ChatOllama(**llm_kwargs).bind_tools(tools)

    lc_messages = _to_langchain_messages(messages)
    response = llm.invoke(lc_messages)
    tool_results: list[str] = []

    for _ in range(max_tool_rounds):
        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            text = _extract_text(response.content)
            pseudo_call = _pseudo_tool_call_from_text(text, tool_map)
            if pseudo_call:
                tool_name, tool_args = pseudo_call
                lc_messages.append(response)
                tool_result = _invoke_selected_tool(tool_map, tool_name, tool_args)
                tool_results.append(str(tool_result))
                lc_messages.append(
                    HumanMessage(
                        content=(
                            f"Tool result from {tool_name} with args {json.dumps(tool_args, sort_keys=True)}:\n"
                            f"{tool_result}\n\nContinue from this tool result and answer the user's request."
                        )
                    )
                )
                response = llm.invoke(lc_messages)
                continue
            if text != "(no response)":
                return text, _stats_from_response(response)
            # Thinking model produced no visible text — ask for a plain summary
            text, summary_stats = _summarize_without_tools(model, llm_kwargs, messages, tool_results)
            if text == "(no response)":
                text = _fallback_answer_from_tool_results(tool_results)
            return text, summary_stats
        lc_messages.append(response)
        for call in tool_calls:
            tool_name = call.get("name")
            tool_args = call.get("args") or {}
            tool_id = call.get("id")
            tool_result = _invoke_selected_tool(tool_map, tool_name, tool_args)
            tool_results.append(str(tool_result))
            lc_messages.append(ToolMessage(content=str(tool_result), tool_call_id=tool_id))
        response = llm.invoke(lc_messages)

    text = _extract_text(response.content)
    if _pseudo_tool_call_from_text(text, tool_map):
        text = "(no response)"
    if text != "(no response)":
        return text, _stats_from_response(response)
    text, summary_stats = _summarize_without_tools(model, llm_kwargs, messages, tool_results)
    if text == "(no response)":
        text = _fallback_answer_from_tool_results(tool_results)
    return text, summary_stats


def invoke_langchain_agent_with_trace(
    model: str, messages: list[dict[str, str]], max_tool_rounds: int = 4, keep_alive: str | None = None
) -> tuple[str, ChatStats | None, list[str]]:
    """Invoke the LangChain agent and return user-visible tool command descriptions."""
    commands: list[str] = []
    text = ""
    stats = None
    for event in stream_langchain_agent_events(model, messages, max_tool_rounds, keep_alive=keep_alive):
        if event["type"] == "cmd":
            commands.append(event["command"])
        elif event["type"] == "final":
            text = event.get("text", "")
            stats = event.get("stats")
    return text, stats, commands


def stream_langchain_agent_events(
    model: str, messages: list[dict[str, str]], max_tool_rounds: int = 4, keep_alive: str | None = None
):
    """Generator that yields live events as the agent runs tools and produces a final answer.

    Event types:
      {"type": "cmd",   "command": str}          — emitted before each tool executes
      {"type": "final", "text": str, "stats": …} — emitted once with the final answer
    """
    try:
        from langchain_core.messages import HumanMessage, ToolMessage
        from langchain_ollama import ChatOllama
    except ImportError as exc:
        raise _missing_dependency_error() from exc

    tools = _build_tools()
    tool_map = {item.name: item for item in tools}
    llm_kwargs: dict = {"model": model, "base_url": get_ollama_base_url(), "temperature": 0, "timeout": 180}
    if keep_alive:
        llm_kwargs["keep_alive"] = keep_alive
    if _should_think(model):
        llm_kwargs["options"] = {"think": True}
    llm = ChatOllama(**llm_kwargs).bind_tools(tools)

    tool_results: list[str] = []
    lc_messages = _to_langchain_messages(messages)
    response = llm.invoke(lc_messages)

    for _ in range(max_tool_rounds):
        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            text = _extract_text(response.content)
            pseudo_call = _pseudo_tool_call_from_text(text, tool_map)
            if pseudo_call:
                tool_name, tool_args = pseudo_call
                yield {"type": "cmd", "command": describe_tool_call(tool_name, tool_args)}
                lc_messages.append(response)
                tool_result = _invoke_selected_tool(tool_map, tool_name, tool_args)
                tool_results.append(str(tool_result))
                lc_messages.append(
                    HumanMessage(
                        content=(
                            f"Tool result from {tool_name} with args {json.dumps(tool_args, sort_keys=True)}:\n"
                            f"{tool_result}\n\nContinue from this tool result and answer the user's request."
                        )
                    )
                )
                response = llm.invoke(lc_messages)
                continue
            if text != "(no response)":
                yield {"type": "final", "text": text, "stats": _stats_from_response(response)}
                return
            text, summary_stats = _summarize_without_tools(model, llm_kwargs, messages, tool_results)
            if text == "(no response)":
                text = _fallback_answer_from_tool_results(tool_results)
            yield {"type": "final", "text": text, "stats": summary_stats}
            return
        lc_messages.append(response)
        for call in tool_calls:
            tool_name = call.get("name")
            tool_args = call.get("args") or {}
            tool_id = call.get("id")
            # Yield the command description BEFORE the tool runs so the UI shows it live
            yield {"type": "cmd", "command": describe_tool_call(tool_name, tool_args)}
            tool_result = _invoke_selected_tool(tool_map, tool_name, tool_args)
            tool_results.append(str(tool_result))
            lc_messages.append(ToolMessage(content=str(tool_result), tool_call_id=tool_id))
        response = llm.invoke(lc_messages)

    text = _extract_text(response.content)
    if _pseudo_tool_call_from_text(text, tool_map):
        text = "(no response)"
    if text != "(no response)":
        yield {"type": "final", "text": text, "stats": _stats_from_response(response)}
        return
    text, summary_stats = _summarize_without_tools(model, llm_kwargs, messages, tool_results)
    if text == "(no response)":
        text = _fallback_answer_from_tool_results(tool_results)
    yield {"type": "final", "text": text, "stats": summary_stats}


def _extract_text(content: object) -> str:
    """Return plain text from a LangChain message content, stripping think tags."""
    if isinstance(content, list):
        parts = [item.get("text", "") if isinstance(item, dict) else str(item) for item in content]
        text = "".join(parts)
    else:
        text = str(content) if content is not None else ""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)  # strip bold
    text = re.sub(r"\*(.+?)\*", r"\1", text)       # strip italic
    return text or "(no response)"
