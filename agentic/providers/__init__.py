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

Auto-detection:
    from agentic.providers import detect_provider, create_runtime

    provider, model = detect_provider()     # auto-detect best available
    rt = create_runtime()                   # create runtime with auto-detection
    rt = create_runtime(provider="anthropic", model="claude-sonnet-4-20250514")
"""

import os
import shutil


# -- Provider registry -------------------------------------------------------

# Maps provider name -> (class_name, module_path, default_model)
PROVIDERS = {
    "claude-code":  ("ClaudeCodeRuntime",  "agentic.providers.claude_code",  "sonnet"),
    "codex":        ("CodexRuntime",       "agentic.providers.codex",        "o4-mini"),
    "gemini-cli":   ("GeminiCLIRuntime",   "agentic.providers.gemini_cli",   "gemini-2.5-flash"),
    "anthropic":    ("AnthropicRuntime",    "agentic.providers.anthropic",    "claude-sonnet-4-6"),
    "openai":       ("OpenAIRuntime",       "agentic.providers.openai",       "gpt-4.1"),
    "gemini":       ("GeminiRuntime",       "agentic.providers.gemini",       "gemini-2.5-flash"),
}


def detect_provider() -> tuple[str, str]:
    """Auto-detect the best available LLM provider.

    Detection priority (CLI-first, then API keys):
      1. Claude Code CLI  (`claude` in PATH)       — subscription, no per-token cost
      2. Codex CLI         (`codex` in PATH)        — uses codex auth
      3. Gemini CLI        (`gemini` in PATH)       — uses Google account
      4. Anthropic API     (ANTHROPIC_API_KEY set)  — pay per token
      5. OpenAI API        (OPENAI_API_KEY set)     — pay per token
      6. Gemini API        (GOOGLE_API_KEY or GOOGLE_GENERATIVE_AI_API_KEY set)
                                                   — pay per token

    Returns:
        (provider_name, default_model) — e.g. ("claude-code", "sonnet")

    Raises:
        RuntimeError if no provider is found.
    """
    # CLI providers (no API key needed)
    if shutil.which("claude"):
        return "claude-code", "sonnet"
    if shutil.which("codex"):
        return "codex", "o4-mini"
    if shutil.which("gemini"):
        return "gemini-cli", "gemini-2.5-flash"

    # API providers (need keys)
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic", "claude-sonnet-4-6"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai", "gpt-4.1"
    if os.environ.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_GENERATIVE_AI_API_KEY"):
        return "gemini", "gemini-2.5-flash"

    raise RuntimeError(
        "No LLM provider found. Set up one of the following:\n"
        "\n"
        "  CLI providers (no API key needed):\n"
        "    1. Claude Code CLI:  npm install -g @anthropic-ai/claude-code && claude login\n"
        "    2. Codex CLI:        npm install -g @openai/codex && codex auth\n"
        "    3. Gemini CLI:       npm install -g @google/gemini-cli\n"
        "\n"
        "  API providers (set environment variable):\n"
        "    4. Anthropic:  export ANTHROPIC_API_KEY=sk-ant-...\n"
        "    5. OpenAI:     export OPENAI_API_KEY=sk-...\n"
        "    6. Gemini:     export GOOGLE_API_KEY=...\n"
        "                    (or GOOGLE_GENERATIVE_AI_API_KEY=...)\n"
    )


def create_runtime(provider: str = None, model: str = None, **kwargs):
    """Create a Runtime instance with auto-detection or explicit provider.

    Args:
        provider:  Provider name (e.g. "anthropic", "claude-code", "openai").
                   If None, auto-detects the best available provider.
        model:     Model name override.
        **kwargs:  Forwarded to the provider Runtime constructor.

    Returns:
        A Runtime instance ready to use.
    """
    import importlib

    if provider:
        if provider not in PROVIDERS:
            available = ", ".join(sorted(PROVIDERS.keys()))
            raise ValueError(
                f"Unknown provider: {provider!r}. Available: {available}"
            )
        class_name, module_path, default_model = PROVIDERS[provider]
    else:
        detected, default_model = detect_provider()
        class_name, module_path, _ = PROVIDERS[detected]
        provider = detected

    use_model = model or default_model

    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name)
    return cls(model=use_model, **kwargs)


# -- Lazy imports for direct class access ------------------------------------

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


__all__ = [
    "PROVIDERS",
    "detect_provider",
    "create_runtime",
    "AnthropicRuntime",
    "OpenAIRuntime",
    "GeminiRuntime",
    "ClaudeCodeRuntime",
    "CodexRuntime",
    "GeminiCLIRuntime",
]
