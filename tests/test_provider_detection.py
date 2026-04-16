"""Tests for provider auto-detection and lazy imports."""

import importlib
import pytest
from unittest.mock import MagicMock, patch

class TestProviderDetection:
    """Tests for detect_provider() and create_runtime() wiring."""

    def test_detect_provider_prefers_explicit_env_config(self, monkeypatch):
        """AGENTIC_PROVIDER / AGENTIC_MODEL override CLI and API auto-detection."""
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/claude" if name == "claude" else None)
        monkeypatch.setenv("AGENTIC_PROVIDER", "openai")
        monkeypatch.setenv("AGENTIC_MODEL", "gpt-5.1-mini")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_GENERATIVE_AI_API_KEY", raising=False)

        from agentic import providers
        importlib.reload(providers)

        assert providers.detect_provider() == ("openai", "gpt-5.1-mini")

    def test_detect_provider_uses_config_default_model_when_model_missing(self, monkeypatch):
        """AGENTIC_PROVIDER alone falls back to the registry default model."""
        monkeypatch.setattr("shutil.which", lambda name: None)
        monkeypatch.setenv("AGENTIC_PROVIDER", "anthropic")
        monkeypatch.delenv("AGENTIC_MODEL", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_GENERATIVE_AI_API_KEY", raising=False)

        from agentic import providers
        importlib.reload(providers)

        assert providers.detect_provider() == ("anthropic", "claude-sonnet-4-6")

    def test_detect_provider_accepts_google_generative_ai_api_key(self, monkeypatch):
        """Gemini API auto-detection accepts Google's alternate env var name."""
        monkeypatch.setattr("shutil.which", lambda name: None)
        monkeypatch.delenv("AGENTIC_PROVIDER", raising=False)
        monkeypatch.delenv("AGENTIC_MODEL", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.setenv("GOOGLE_GENERATIVE_AI_API_KEY", "fallback-key")

        from agentic import providers
        importlib.reload(providers)

        assert providers.detect_provider() == ("gemini", "gemini-2.5-flash")

    def test_check_providers_marks_env_selected_provider_default(self, monkeypatch):
        """check_providers() marks the configured provider as the auto-selected default."""
        monkeypatch.setattr("shutil.which", lambda name: None)
        monkeypatch.setenv("AGENTIC_PROVIDER", "gemini")
        monkeypatch.delenv("AGENTIC_MODEL", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_GENERATIVE_AI_API_KEY", raising=False)

        from agentic import providers
        importlib.reload(providers)

        statuses = providers.check_providers()
        assert statuses["gemini"]["default"] is True
        assert statuses["gemini"]["model"] == "gemini-2.5-flash"


    def test_detect_provider_cli_fallback_order(self, monkeypatch):
        """CLI providers are tried in order: claude → codex → gemini."""
        monkeypatch.delenv("AGENTIC_PROVIDER", raising=False)
        monkeypatch.delenv("AGENTIC_MODEL", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_GENERATIVE_AI_API_KEY", raising=False)
        monkeypatch.delenv("CLAUDECODE", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_ENTRYPOINT", raising=False)
        monkeypatch.delenv("CODEX_CLI", raising=False)
        monkeypatch.delenv("CODEX_SANDBOX_TYPE", raising=False)

        # Only codex CLI available
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/codex" if name == "codex" else None)

        from agentic import providers
        importlib.reload(providers)

        assert providers.detect_provider() == ("codex", None)

    def test_detect_provider_api_key_fallback(self, monkeypatch):
        """API keys are tried in order: Anthropic → OpenAI → Gemini."""
        monkeypatch.setattr("shutil.which", lambda name: None)
        monkeypatch.delenv("AGENTIC_PROVIDER", raising=False)
        monkeypatch.delenv("AGENTIC_MODEL", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_GENERATIVE_AI_API_KEY", raising=False)
        monkeypatch.delenv("CLAUDECODE", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_ENTRYPOINT", raising=False)
        monkeypatch.delenv("CODEX_CLI", raising=False)
        monkeypatch.delenv("CODEX_SANDBOX_TYPE", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        from agentic import providers
        importlib.reload(providers)

        assert providers.detect_provider() == ("openai", "gpt-4.1")

    def test_detect_provider_no_provider_raises(self, monkeypatch):
        """RuntimeError when no provider is available."""
        monkeypatch.setattr("shutil.which", lambda name: None)
        monkeypatch.delenv("AGENTIC_PROVIDER", raising=False)
        monkeypatch.delenv("AGENTIC_MODEL", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_GENERATIVE_AI_API_KEY", raising=False)
        monkeypatch.delenv("CLAUDECODE", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_ENTRYPOINT", raising=False)
        monkeypatch.delenv("CODEX_CLI", raising=False)
        monkeypatch.delenv("CODEX_SANDBOX_TYPE", raising=False)

        from agentic import providers
        importlib.reload(providers)

        with pytest.raises(RuntimeError, match="No LLM provider found"):
            providers.detect_provider()

    def test_detect_caller_env_claude_code(self, monkeypatch):
        """_detect_caller_env detects Claude Code environment."""
        monkeypatch.setenv("CLAUDECODE", "1")
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/claude" if name == "claude" else None)

        from agentic import providers
        importlib.reload(providers)

        result = providers._detect_caller_env()
        assert result == ("claude-code", "sonnet")

    def test_detect_caller_env_codex(self, monkeypatch):
        """_detect_caller_env detects Codex CLI environment."""
        monkeypatch.delenv("CLAUDECODE", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_ENTRYPOINT", raising=False)
        monkeypatch.setenv("CODEX_CLI", "1")
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/codex" if name == "codex" else None)

        from agentic import providers
        importlib.reload(providers)

        result = providers._detect_caller_env()
        assert result == ("codex", None)

    def test_create_runtime_unknown_provider_raises(self):
        """create_runtime with unknown provider raises ValueError."""
        from agentic import providers
        with pytest.raises(ValueError, match="Unknown provider"):
            providers.create_runtime(provider="nonexistent")

    def test_check_providers_no_default_when_none_available(self, monkeypatch):
        """check_providers() has no 'default' key when nothing is available."""
        monkeypatch.setattr("shutil.which", lambda name: None)
        monkeypatch.delenv("AGENTIC_PROVIDER", raising=False)
        monkeypatch.delenv("AGENTIC_MODEL", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_GENERATIVE_AI_API_KEY", raising=False)
        monkeypatch.delenv("CLAUDECODE", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_ENTRYPOINT", raising=False)
        monkeypatch.delenv("CODEX_CLI", raising=False)
        monkeypatch.delenv("CODEX_SANDBOX_TYPE", raising=False)

        from agentic import providers
        importlib.reload(providers)

        statuses = providers.check_providers()
        # No provider should be marked as default
        for name, info in statuses.items():
            assert "default" not in info

    def test_check_providers_all_entries_present(self, monkeypatch):
        """check_providers() returns entries for all 6 known providers."""
        monkeypatch.setattr("shutil.which", lambda name: None)
        monkeypatch.delenv("AGENTIC_PROVIDER", raising=False)
        monkeypatch.delenv("AGENTIC_MODEL", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_GENERATIVE_AI_API_KEY", raising=False)

        from agentic import providers
        importlib.reload(providers)

        statuses = providers.check_providers()
        expected = {"claude-code", "codex", "gemini-cli", "anthropic", "openai", "gemini"}
        assert set(statuses.keys()) == expected
        for info in statuses.values():
            assert "available" in info
            assert "method" in info
            assert "model" in info


class TestProviderLazyImport:
    """Test that providers/__init__.py lazy-loads correctly."""

    def test_unknown_attribute_raises(self):
        """Accessing unknown attribute raises AttributeError."""
        from agentic import providers
        with pytest.raises(AttributeError, match="no attribute"):
            _ = providers.NonExistentRuntime

    def test_all_exports(self):
        """__all__ lists all providers."""
        from agentic import providers
        assert "AnthropicRuntime" in providers.__all__
        assert "OpenAIRuntime" in providers.__all__
        assert "GeminiRuntime" in providers.__all__
        assert "ClaudeCodeRuntime" in providers.__all__
        assert "CodexRuntime" in providers.__all__
        assert "GeminiCLIRuntime" in providers.__all__
