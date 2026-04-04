"""
agentic.providers — Built-in Runtime implementations for popular LLM providers.

Each provider is an optional dependency. Import will give a clear error
if the required SDK is not installed.

Available providers:
    AnthropicRuntime    — Anthropic Claude API (text + image, prompt caching)
    OpenAIRuntime       — OpenAI GPT API (text + image, response_format)
    GeminiRuntime       — Google Gemini API (text + image)
    ClaudeCodeRuntime   — Claude Code CLI (no API key, uses subscription)
    CodexRuntime        — OpenAI Codex CLI (no API key in harness, uses codex auth)
    GeminiCLIRuntime    — Gemini CLI (no API key, uses Google account)

Usage:
    from agentic.providers import AnthropicRuntime
    rt = AnthropicRuntime(api_key="sk-...", model="claude-sonnet-4-20250514")

    from agentic.providers import OpenAIRuntime
    rt = OpenAIRuntime(api_key="sk-...", model="gpt-4o")

    from agentic.providers import GeminiRuntime
    rt = GeminiRuntime(api_key="...", model="gemini-2.5-flash")

    from agentic.providers import CodexRuntime
    rt = CodexRuntime(model="o4-mini")
"""


def __getattr__(name):
    """Lazy imports — only load a provider when accessed."""
    if name == "AnthropicRuntime":
        from agentic.providers.anthropic import AnthropicRuntime
        return AnthropicRuntime
    if name == "OpenAIRuntime":
        from agentic.providers.openai import OpenAIRuntime
        return OpenAIRuntime
    if name == "GeminiRuntime":
        from agentic.providers.gemini import GeminiRuntime
        return GeminiRuntime
    if name == "ClaudeCodeRuntime":
        from agentic.providers.claude_code import ClaudeCodeRuntime
        return ClaudeCodeRuntime
    if name == "CodexRuntime":
        from agentic.providers.codex import CodexRuntime
        return CodexRuntime
    if name == "GeminiCLIRuntime":
        from agentic.providers.gemini_cli import GeminiCLIRuntime
        return GeminiCLIRuntime
    raise AttributeError(f"module 'agentic.providers' has no attribute {name!r}")


__all__ = ["AnthropicRuntime", "OpenAIRuntime", "GeminiRuntime", "ClaudeCodeRuntime", "CodexRuntime", "GeminiCLIRuntime"]
