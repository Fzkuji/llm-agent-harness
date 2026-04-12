"""
Tests for built-in provider Runtimes (Anthropic, OpenAI, Gemini).

All tests use mocked SDKs — no real API calls are made.
"""

import base64
import importlib
import json
import os
import subprocess
import types
import pytest
from unittest.mock import MagicMock, patch, mock_open

from agentic import agentic_function
from agentic.runtime import Runtime


# ══════════════════════════════════════════════════════════════
# AnthropicRuntime tests
# ══════════════════════════════════════════════════════════════

class TestAnthropicRuntime:
    """Tests for AnthropicRuntime with mocked anthropic SDK."""

    @pytest.fixture(autouse=True)
    def setup_mock(self, monkeypatch):
        """Mock the anthropic module before importing AnthropicRuntime."""
        self.mock_anthropic = MagicMock()

        # Mock response
        mock_content_block = MagicMock()
        mock_content_block.text = "mock reply"
        mock_response = MagicMock()
        mock_response.content = [mock_content_block]
        self.mock_client = MagicMock()
        self.mock_client.messages.create.return_value = mock_response
        self.mock_anthropic.Anthropic.return_value = self.mock_client

        # Patch the import
        import sys
        self._original = sys.modules.get("anthropic")
        sys.modules["anthropic"] = self.mock_anthropic
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        # Force reimport
        import importlib
        if "agentic.providers.anthropic" in sys.modules:
            del sys.modules["agentic.providers.anthropic"]

        yield

        # Restore
        if self._original is not None:
            sys.modules["anthropic"] = self._original
        elif "anthropic" in sys.modules:
            del sys.modules["anthropic"]
        if "agentic.providers.anthropic" in sys.modules:
            del sys.modules["agentic.providers.anthropic"]

    def _make_runtime(self, **kwargs):
        from agentic.providers.anthropic import AnthropicRuntime
        return AnthropicRuntime(api_key="test-key", **kwargs)

    def test_text_block_conversion(self):
        """Text blocks are converted to Anthropic format."""
        rt = self._make_runtime()
        rt._call(
            [{"type": "text", "text": "hello"}],
            model="claude-sonnet-4-20250514",
        )
        call_kwargs = self.mock_client.messages.create.call_args[1]
        content = call_kwargs["messages"][0]["content"]
        assert content[0]["type"] == "text"
        assert content[0]["text"] == "hello"

    def test_cache_control_injected_on_last_block(self):
        """cache_control is added to the last content block."""
        rt = self._make_runtime()
        rt._call(
            [
                {"type": "text", "text": "first"},
                {"type": "text", "text": "second"},
            ],
            model="claude-sonnet-4-20250514",
        )
        call_kwargs = self.mock_client.messages.create.call_args[1]
        content = call_kwargs["messages"][0]["content"]
        assert "cache_control" not in content[0]
        assert content[1]["cache_control"] == {"type": "ephemeral"}

    def test_cache_control_passthrough(self):
        """User-provided cache_control on text blocks is preserved."""
        rt = self._make_runtime()
        rt._call(
            [{"type": "text", "text": "cached", "cache_control": {"type": "ephemeral"}}],
            model="claude-sonnet-4-20250514",
        )
        call_kwargs = self.mock_client.messages.create.call_args[1]
        # The block should have cache_control (from both user and auto-injection)
        content = call_kwargs["messages"][0]["content"]
        assert content[0]["cache_control"] == {"type": "ephemeral"}

    def test_image_from_base64(self):
        """Image block with data is converted to base64 source."""
        rt = self._make_runtime()
        rt._call(
            [{"type": "image", "data": "abc123", "media_type": "image/jpeg"}],
            model="claude-sonnet-4-20250514",
        )
        call_kwargs = self.mock_client.messages.create.call_args[1]
        content = call_kwargs["messages"][0]["content"]
        assert content[0]["type"] == "image"
        assert content[0]["source"]["type"] == "base64"
        assert content[0]["source"]["data"] == "abc123"
        assert content[0]["source"]["media_type"] == "image/jpeg"

    def test_image_from_url(self):
        """Image block with url is converted to URL source."""
        rt = self._make_runtime()
        rt._call(
            [{"type": "image", "url": "https://example.com/img.png"}],
            model="claude-sonnet-4-20250514",
        )
        call_kwargs = self.mock_client.messages.create.call_args[1]
        content = call_kwargs["messages"][0]["content"]
        assert content[0]["type"] == "image"
        assert content[0]["source"]["type"] == "url"

    def test_image_from_file(self, tmp_path):
        """Image block with path reads and base64-encodes the file."""
        img_path = tmp_path / "test.png"
        img_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 10)

        rt = self._make_runtime()
        rt._call(
            [{"type": "image", "path": str(img_path)}],
            model="claude-sonnet-4-20250514",
        )
        call_kwargs = self.mock_client.messages.create.call_args[1]
        content = call_kwargs["messages"][0]["content"]
        assert content[0]["type"] == "image"
        assert content[0]["source"]["type"] == "base64"
        # Should be valid base64
        decoded = base64.b64decode(content[0]["source"]["data"])
        assert decoded[:4] == b"\x89PNG"

    def test_system_prompt_with_cache(self):
        """System prompt with cache_system=True adds cache_control."""
        rt = self._make_runtime(system="You are a helper.", cache_system=True)
        rt._call(
            [{"type": "text", "text": "hello"}],
            model="claude-sonnet-4-20250514",
        )
        call_kwargs = self.mock_client.messages.create.call_args[1]
        system = call_kwargs["system"]
        assert isinstance(system, list)
        assert system[0]["cache_control"] == {"type": "ephemeral"}

    def test_system_prompt_without_cache(self):
        """System prompt with cache_system=False passes string directly."""
        rt = self._make_runtime(system="You are a helper.", cache_system=False)
        rt._call(
            [{"type": "text", "text": "hello"}],
            model="claude-sonnet-4-20250514",
        )
        call_kwargs = self.mock_client.messages.create.call_args[1]
        assert call_kwargs["system"] == "You are a helper."

    def test_unknown_block_with_text_fallback(self):
        """Unknown block types with 'text' key fall back to text."""
        rt = self._make_runtime()
        rt._call(
            [{"type": "custom", "text": "fallback text"}],
            model="claude-sonnet-4-20250514",
        )
        call_kwargs = self.mock_client.messages.create.call_args[1]
        content = call_kwargs["messages"][0]["content"]
        assert content[0]["type"] == "text"
        assert content[0]["text"] == "fallback text"

    def test_unknown_block_without_text_skipped(self):
        """Unknown block types without 'text' key are skipped."""
        rt = self._make_runtime()
        rt._call(
            [
                {"type": "text", "text": "keep"},
                {"type": "custom_no_text", "data": "skip"},
            ],
            model="claude-sonnet-4-20250514",
        )
        call_kwargs = self.mock_client.messages.create.call_args[1]
        content = call_kwargs["messages"][0]["content"]
        # Only the text block should be present
        assert len(content) == 1
        assert content[0]["text"] == "keep"

    def test_api_error_propagates(self):
        """Anthropic API errors propagate through exec() retry."""
        self.mock_client.messages.create.side_effect = Exception("API rate limit")
        rt = self._make_runtime()

        @agentic_function
        def failing():
            """Test."""
            return rt.exec(content=[{"type": "text", "text": "test"}])

        with pytest.raises(RuntimeError, match="failed after"):
            failing()

    def test_no_api_key_raises(self, monkeypatch):
        """Missing API key raises ValueError."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        from agentic.providers.anthropic import AnthropicRuntime
        with pytest.raises(ValueError, match="API key"):
            AnthropicRuntime(api_key=None)

    def test_model_default_and_override(self):
        """Default model is used, and per-call override works."""
        rt = self._make_runtime(model="claude-haiku")
        rt._call([{"type": "text", "text": "hi"}])
        call_kwargs = self.mock_client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-haiku"

        rt._call([{"type": "text", "text": "hi"}], model="claude-opus")
        call_kwargs = self.mock_client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-opus"

    def test_file_pdf_from_base64(self):
        """File block with data is converted to Anthropic document type."""
        rt = self._make_runtime()
        rt._call(
            [{"type": "file", "data": "abc123", "mime_type": "application/pdf"}],
            model="claude-sonnet-4-20250514",
        )
        call_kwargs = self.mock_client.messages.create.call_args[1]
        content = call_kwargs["messages"][0]["content"]
        assert content[0]["type"] == "document"
        assert content[0]["source"]["type"] == "base64"
        assert content[0]["source"]["data"] == "abc123"
        assert content[0]["source"]["media_type"] == "application/pdf"

    def test_file_pdf_from_path(self, tmp_path):
        """File block with path reads and base64-encodes the PDF."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4" + b"\x00" * 10)

        rt = self._make_runtime()
        rt._call(
            [{"type": "file", "path": str(pdf_path)}],
            model="claude-sonnet-4-20250514",
        )
        call_kwargs = self.mock_client.messages.create.call_args[1]
        content = call_kwargs["messages"][0]["content"]
        assert content[0]["type"] == "document"
        assert content[0]["source"]["type"] == "base64"
        assert content[0]["source"]["media_type"] == "application/pdf"

    def test_audio_block_warns(self):
        """Audio blocks emit a warning and are skipped."""
        rt = self._make_runtime()
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            rt._call(
                [
                    {"type": "text", "text": "hello"},
                    {"type": "audio", "path": "test.wav"},
                ],
                model="claude-sonnet-4-20250514",
            )
            audio_warnings = [x for x in w if "audio" in str(x.message).lower()]
            assert len(audio_warnings) == 1
        call_kwargs = self.mock_client.messages.create.call_args[1]
        content = call_kwargs["messages"][0]["content"]
        assert len(content) == 1
        assert content[0]["type"] == "text"

    def test_video_block_warns(self):
        """Video blocks emit a warning and are skipped."""
        rt = self._make_runtime()
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            rt._call(
                [
                    {"type": "text", "text": "hello"},
                    {"type": "video", "path": "test.mp4"},
                ],
                model="claude-sonnet-4-20250514",
            )
            video_warnings = [x for x in w if "video" in str(x.message).lower()]
            assert len(video_warnings) == 1
        call_kwargs = self.mock_client.messages.create.call_args[1]
        content = call_kwargs["messages"][0]["content"]
        assert len(content) == 1
        assert content[0]["type"] == "text"


# ══════════════════════════════════════════════════════════════
# OpenAIRuntime tests
# ══════════════════════════════════════════════════════════════

class TestOpenAIRuntime:
    """Tests for OpenAIRuntime with mocked openai SDK."""

    @pytest.fixture(autouse=True)
    def setup_mock(self, monkeypatch):
        """Mock the openai module."""
        self.mock_openai = MagicMock()

        # Mock response
        mock_message = MagicMock()
        mock_message.content = "mock reply"
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        self.mock_client = MagicMock()
        self.mock_client.chat.completions.create.return_value = mock_response
        self.mock_openai.OpenAI.return_value = self.mock_client

        import sys
        self._original = sys.modules.get("openai")
        sys.modules["openai"] = self.mock_openai
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        if "agentic.providers.openai" in sys.modules:
            del sys.modules["agentic.providers.openai"]

        yield

        if self._original is not None:
            sys.modules["openai"] = self._original
        elif "openai" in sys.modules:
            del sys.modules["openai"]
        if "agentic.providers.openai" in sys.modules:
            del sys.modules["agentic.providers.openai"]

    def _make_runtime(self, **kwargs):
        from agentic.providers.openai import OpenAIRuntime
        return OpenAIRuntime(api_key="test-key", **kwargs)

    def test_text_block_conversion(self):
        """Text blocks are converted to OpenAI format."""
        rt = self._make_runtime()
        rt._call([{"type": "text", "text": "hello"}])
        call_kwargs = self.mock_client.chat.completions.create.call_args[1]
        user_msg = call_kwargs["messages"][-1]
        assert user_msg["content"][0] == {"type": "text", "text": "hello"}

    def test_image_from_url(self):
        """Image block with url → image_url format."""
        rt = self._make_runtime()
        rt._call([{"type": "image", "url": "https://example.com/img.png"}])
        call_kwargs = self.mock_client.chat.completions.create.call_args[1]
        content = call_kwargs["messages"][-1]["content"]
        assert content[0]["type"] == "image_url"
        assert content[0]["image_url"]["url"] == "https://example.com/img.png"

    def test_image_from_base64(self):
        """Image block with data → data URL format."""
        rt = self._make_runtime()
        rt._call([{"type": "image", "data": "abc123", "media_type": "image/jpeg"}])
        call_kwargs = self.mock_client.chat.completions.create.call_args[1]
        content = call_kwargs["messages"][-1]["content"]
        assert content[0]["type"] == "image_url"
        assert "data:image/jpeg;base64,abc123" in content[0]["image_url"]["url"]

    def test_image_from_file(self, tmp_path):
        """Image block with path → read + base64 encode."""
        img_path = tmp_path / "test.jpg"
        img_path.write_bytes(b"\xff\xd8\xff" + b"\x00" * 10)

        rt = self._make_runtime()
        rt._call([{"type": "image", "path": str(img_path)}])
        call_kwargs = self.mock_client.chat.completions.create.call_args[1]
        content = call_kwargs["messages"][-1]["content"]
        assert content[0]["type"] == "image_url"
        assert "data:image/jpeg;base64," in content[0]["image_url"]["url"]

    def test_system_prompt(self):
        """System prompt is sent as a system message."""
        rt = self._make_runtime(system="You are helpful.")
        rt._call([{"type": "text", "text": "hello"}])
        call_kwargs = self.mock_client.chat.completions.create.call_args[1]
        messages = call_kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are helpful."

    def test_response_format_passed(self):
        """response_format is passed through to the API."""
        rt = self._make_runtime()
        schema = {"type": "json_object"}
        rt._call([{"type": "text", "text": "test"}], response_format=schema)
        call_kwargs = self.mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["response_format"] == schema

    def test_temperature(self):
        """Temperature is passed when set."""
        rt = self._make_runtime(temperature=0.5)
        rt._call([{"type": "text", "text": "test"}])
        call_kwargs = self.mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["temperature"] == 0.5

    def test_no_temperature_by_default(self):
        """Temperature is not passed when not set."""
        rt = self._make_runtime()
        rt._call([{"type": "text", "text": "test"}])
        call_kwargs = self.mock_client.chat.completions.create.call_args[1]
        assert "temperature" not in call_kwargs

    def test_base_url(self):
        """base_url is passed to OpenAI client."""
        rt = self._make_runtime(base_url="https://custom.api.com")
        # Verify OpenAI was called with base_url
        call_args = self.mock_openai.OpenAI.call_args
        assert call_args[1].get("base_url") == "https://custom.api.com"

    def test_no_api_key_raises(self, monkeypatch):
        """Missing API key raises ValueError."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from agentic.providers.openai import OpenAIRuntime
        with pytest.raises(ValueError, match="API key"):
            OpenAIRuntime(api_key=None)

    def test_model_default_and_override(self):
        """Default model and per-call override."""
        rt = self._make_runtime(model="gpt-4o-mini")
        rt._call([{"type": "text", "text": "hi"}])
        call_kwargs = self.mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "gpt-4o-mini"

        rt._call([{"type": "text", "text": "hi"}], model="gpt-4o")
        call_kwargs = self.mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "gpt-4o"

    def test_api_error_propagates(self):
        """API errors propagate through exec()."""
        self.mock_client.chat.completions.create.side_effect = Exception("quota exceeded")
        rt = self._make_runtime()

        @agentic_function
        def failing():
            """Test."""
            return rt.exec(content=[{"type": "text", "text": "test"}])

        with pytest.raises(RuntimeError, match="failed after"):
            failing()

    def test_audio_from_base64(self):
        """Audio block with data → input_audio format."""
        rt = self._make_runtime()
        rt._call([{"type": "audio", "data": "audiodata123", "format": "wav"}])
        call_kwargs = self.mock_client.chat.completions.create.call_args[1]
        content = call_kwargs["messages"][-1]["content"]
        assert content[0]["type"] == "input_audio"
        assert content[0]["input_audio"]["data"] == "audiodata123"
        assert content[0]["input_audio"]["format"] == "wav"

    def test_audio_from_file(self, tmp_path):
        """Audio block with path → read + base64 + input_audio."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"RIFF" + b"\x00" * 10)

        rt = self._make_runtime()
        rt._call([{"type": "audio", "path": str(audio_path)}])
        call_kwargs = self.mock_client.chat.completions.create.call_args[1]
        content = call_kwargs["messages"][-1]["content"]
        assert content[0]["type"] == "input_audio"
        assert content[0]["input_audio"]["format"] == "wav"

    def test_audio_mp3_format(self, tmp_path):
        """Audio with .mp3 extension uses mp3 format."""
        audio_path = tmp_path / "test.mp3"
        audio_path.write_bytes(b"\xff\xfb" + b"\x00" * 10)

        rt = self._make_runtime()
        rt._call([{"type": "audio", "path": str(audio_path)}])
        call_kwargs = self.mock_client.chat.completions.create.call_args[1]
        content = call_kwargs["messages"][-1]["content"]
        assert content[0]["input_audio"]["format"] == "mp3"

    def test_file_pdf_from_base64(self):
        """File block with data → OpenAI file format."""
        rt = self._make_runtime()
        rt._call([{"type": "file", "data": "pdfdata123", "mime_type": "application/pdf"}])
        call_kwargs = self.mock_client.chat.completions.create.call_args[1]
        content = call_kwargs["messages"][-1]["content"]
        assert content[0]["type"] == "file"
        assert "data:application/pdf;base64,pdfdata123" in content[0]["file"]["file_data"]

    def test_file_pdf_from_path(self, tmp_path):
        """File block with path → read + base64 + file format."""
        pdf_path = tmp_path / "doc.pdf"
        pdf_path.write_bytes(b"%PDF-1.4" + b"\x00" * 10)

        rt = self._make_runtime()
        rt._call([{"type": "file", "path": str(pdf_path)}])
        call_kwargs = self.mock_client.chat.completions.create.call_args[1]
        content = call_kwargs["messages"][-1]["content"]
        assert content[0]["type"] == "file"
        assert content[0]["file"]["filename"] == "doc.pdf"
        assert "data:application/pdf;base64," in content[0]["file"]["file_data"]

    def test_video_block_warns(self):
        """Video blocks emit a warning and are skipped."""
        rt = self._make_runtime()
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            rt._call(
                [
                    {"type": "text", "text": "hello"},
                    {"type": "video", "path": "test.mp4"},
                ],
            )
            video_warnings = [x for x in w if "video" in str(x.message).lower()]
            assert len(video_warnings) == 1
        call_kwargs = self.mock_client.chat.completions.create.call_args[1]
        content = call_kwargs["messages"][-1]["content"]
        assert len(content) == 1
        assert content[0]["type"] == "text"


# ══════════════════════════════════════════════════════════════
# GeminiRuntime tests
# ══════════════════════════════════════════════════════════════

class TestGeminiRuntime:
    """Tests for GeminiRuntime with mocked google-genai SDK."""

    @pytest.fixture(autouse=True)
    def setup_mock(self, monkeypatch):
        """Mock the google.genai module."""
        # Create mock module structure: google.genai and google.genai.types
        self.mock_types = MagicMock()
        self.mock_genai = MagicMock()
        self.mock_genai.types = self.mock_types
        self.mock_google = MagicMock()
        self.mock_google.genai = self.mock_genai

        # Mock response
        mock_response = MagicMock()
        mock_response.text = "mock reply"
        self.mock_client = MagicMock()
        self.mock_client.models.generate_content.return_value = mock_response
        self.mock_genai.Client.return_value = self.mock_client

        # Mock types.Part
        self.mock_types.Part.from_text.side_effect = lambda text: {"_mock": "text", "text": text}
        self.mock_types.Part.from_bytes.side_effect = lambda data, mime_type: {"_mock": "bytes", "mime_type": mime_type}
        self.mock_types.GenerateContentConfig.return_value = MagicMock()

        import sys
        self._originals = {}
        for mod in ["google", "google.genai", "google.genai.types"]:
            self._originals[mod] = sys.modules.get(mod)

        sys.modules["google"] = self.mock_google
        sys.modules["google.genai"] = self.mock_genai
        sys.modules["google.genai.types"] = self.mock_types

        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

        if "agentic.providers.gemini" in sys.modules:
            del sys.modules["agentic.providers.gemini"]

        yield

        for mod, orig in self._originals.items():
            if orig is not None:
                sys.modules[mod] = orig
            elif mod in sys.modules:
                del sys.modules[mod]
        if "agentic.providers.gemini" in sys.modules:
            del sys.modules["agentic.providers.gemini"]

    def _make_runtime(self, **kwargs):
        from agentic.providers.gemini import GeminiRuntime
        return GeminiRuntime(api_key="test-key", **kwargs)

    def test_text_block_conversion(self):
        """Text blocks → types.Part.from_text()."""
        rt = self._make_runtime()
        rt._call([{"type": "text", "text": "hello"}])
        self.mock_types.Part.from_text.assert_called_with(text="hello")

    def test_image_from_base64(self):
        """Image with data → types.Part.from_bytes()."""
        rt = self._make_runtime()
        rt._call([{"type": "image", "data": base64.b64encode(b"imgdata").decode(), "media_type": "image/png"}])
        self.mock_types.Part.from_bytes.assert_called_once()
        call_kwargs = self.mock_types.Part.from_bytes.call_args[1]
        assert call_kwargs["mime_type"] == "image/png"

    def test_image_from_file(self, tmp_path):
        """Image with path → read file + from_bytes()."""
        img_path = tmp_path / "test.png"
        img_path.write_bytes(b"\x89PNG" + b"\x00" * 10)

        rt = self._make_runtime()
        rt._call([{"type": "image", "path": str(img_path)}])
        self.mock_types.Part.from_bytes.assert_called_once()

    def test_system_instruction(self):
        """System instruction is set on config."""
        rt = self._make_runtime(system_instruction="Be helpful.")
        rt._call([{"type": "text", "text": "hello"}])
        config = self.mock_client.models.generate_content.call_args[1]["config"]
        assert config.system_instruction == "Be helpful."

    def test_response_format_json(self):
        """response_format with schema sets response_mime_type."""
        rt = self._make_runtime()
        schema = {"schema": {"type": "object"}}
        rt._call([{"type": "text", "text": "test"}], response_format=schema)
        config_call = self.mock_types.GenerateContentConfig.call_args[1]
        assert config_call["response_mime_type"] == "application/json"
        assert config_call["response_schema"] == {"type": "object"}

    def test_response_format_plain_schema(self):
        """Plain schema dicts are also forwarded as Gemini response_schema."""
        rt = self._make_runtime()
        schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
        rt._call([{"type": "text", "text": "test"}], response_format=schema)
        config_call = self.mock_types.GenerateContentConfig.call_args[1]
        assert config_call["response_mime_type"] == "application/json"
        assert config_call["response_schema"] == schema

    def test_fallback_env_var_google_generative_ai_api_key(self, monkeypatch):
        """GOOGLE_GENERATIVE_AI_API_KEY is accepted for Gemini API compatibility."""
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.setenv("GOOGLE_GENERATIVE_AI_API_KEY", "fallback-key")
        from agentic.providers.gemini import GeminiRuntime

        rt = GeminiRuntime(api_key=None)
        assert rt.client == self.mock_client
        self.mock_genai.Client.assert_called_with(api_key="fallback-key")

    def test_no_api_key_raises(self, monkeypatch):
        """Missing API key raises ValueError."""
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_GENERATIVE_AI_API_KEY", raising=False)
        from agentic.providers.gemini import GeminiRuntime
        with pytest.raises(ValueError, match="API key"):
            GeminiRuntime(api_key=None)

    def test_model_default_and_override(self):
        """Default model and per-call override."""
        rt = self._make_runtime(model="gemini-2.5-flash")
        rt._call([{"type": "text", "text": "hi"}])
        call_kwargs = self.mock_client.models.generate_content.call_args[1]
        assert call_kwargs["model"] == "gemini-2.5-flash"

        rt._call([{"type": "text", "text": "hi"}], model="gemini-2.5-pro")
        call_kwargs = self.mock_client.models.generate_content.call_args[1]
        assert call_kwargs["model"] == "gemini-2.5-pro"

    def test_api_error_propagates(self):
        """API errors propagate through exec()."""
        self.mock_client.models.generate_content.side_effect = Exception("quota exceeded")
        rt = self._make_runtime()

        @agentic_function
        def failing():
            """Test."""
            return rt.exec(content=[{"type": "text", "text": "test"}])

        with pytest.raises(RuntimeError, match="failed after"):
            failing()

    def test_temperature(self):
        """Temperature is passed to config."""
        rt = self._make_runtime(temperature=0.7)
        rt._call([{"type": "text", "text": "hi"}])
        config_call = self.mock_types.GenerateContentConfig.call_args[1]
        assert config_call["temperature"] == 0.7

    def test_audio_from_base64(self):
        """Audio with data → types.Part.from_bytes() with audio mime."""
        rt = self._make_runtime()
        rt._call([{"type": "audio", "data": base64.b64encode(b"audiodata").decode(), "media_type": "audio/wav"}])
        self.mock_types.Part.from_bytes.assert_called_once()
        call_kwargs = self.mock_types.Part.from_bytes.call_args[1]
        assert call_kwargs["mime_type"] == "audio/wav"

    def test_audio_from_file(self, tmp_path):
        """Audio with path → read file + from_bytes()."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"RIFF" + b"\x00" * 10)

        rt = self._make_runtime()
        rt._call([{"type": "audio", "path": str(audio_path)}])
        self.mock_types.Part.from_bytes.assert_called_once()
        call_kwargs = self.mock_types.Part.from_bytes.call_args[1]
        assert "audio" in call_kwargs["mime_type"]

    def test_video_from_base64(self):
        """Video with data → types.Part.from_bytes() with video mime."""
        rt = self._make_runtime()
        rt._call([{"type": "video", "data": base64.b64encode(b"videodata").decode(), "media_type": "video/mp4"}])
        self.mock_types.Part.from_bytes.assert_called_once()
        call_kwargs = self.mock_types.Part.from_bytes.call_args[1]
        assert call_kwargs["mime_type"] == "video/mp4"

    def test_video_from_file(self, tmp_path):
        """Video with path → read file + from_bytes()."""
        video_path = tmp_path / "test.mp4"
        video_path.write_bytes(b"\x00\x00\x00\x1cftyp" + b"\x00" * 10)

        rt = self._make_runtime()
        rt._call([{"type": "video", "path": str(video_path)}])
        self.mock_types.Part.from_bytes.assert_called_once()
        call_kwargs = self.mock_types.Part.from_bytes.call_args[1]
        assert "video" in call_kwargs["mime_type"]

    def test_file_pdf_from_base64(self):
        """File/PDF with data → types.Part.from_bytes() with pdf mime."""
        rt = self._make_runtime()
        rt._call([{"type": "file", "data": base64.b64encode(b"pdfdata").decode(), "mime_type": "application/pdf"}])
        self.mock_types.Part.from_bytes.assert_called_once()
        call_kwargs = self.mock_types.Part.from_bytes.call_args[1]
        assert call_kwargs["mime_type"] == "application/pdf"

    def test_file_pdf_from_path(self, tmp_path):
        """File/PDF with path → read file + from_bytes()."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4" + b"\x00" * 10)

        rt = self._make_runtime()
        rt._call([{"type": "file", "path": str(pdf_path)}])
        self.mock_types.Part.from_bytes.assert_called_once()
        call_kwargs = self.mock_types.Part.from_bytes.call_args[1]
        assert call_kwargs["mime_type"] == "application/pdf"


# ══════════════════════════════════════════════════════════════
# Provider lazy import tests
# ══════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════
# CodexRuntime tests
# ══════════════════════════════════════════════════════════════

class TestCodexRuntime:
    """Tests for CodexRuntime with mocked subprocess."""

    @pytest.fixture(autouse=True)
    def setup_mock(self, monkeypatch, tmp_path):
        """Mock shutil.which and subprocess.run."""
        self.tmp_path = tmp_path
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/codex" if name == "codex" else None)

        # Default mock: write output to -o file, return success
        def mock_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = "mock codex reply"
            result.stderr = ""
            # Find -o flag and write output
            for i, arg in enumerate(cmd):
                if arg == "-o" and i + 1 < len(cmd):
                    with open(cmd[i + 1], "w") as f:
                        f.write("mock codex reply")
                    break
            return result

        self._mock_run = MagicMock(side_effect=mock_run)
        monkeypatch.setattr("subprocess.run", self._mock_run)

        yield

    def _make_runtime(self, **kwargs):
        from agentic.providers.codex import CodexRuntime
        return CodexRuntime(cli_path="/usr/bin/codex", **kwargs)

    def test_text_only_call(self):
        """Text-only content produces correct codex exec command."""
        rt = self._make_runtime()
        result = rt._call([{"type": "text", "text": "hello"}])
        assert result == "mock codex reply"
        cmd = self._mock_run.call_args[0][0]
        assert cmd[0] == "/usr/bin/codex"
        assert "exec" in cmd
        assert "-a" in cmd
        assert cmd[cmd.index("-a") + 1] == "never"
        assert "--full-auto" in cmd
        assert "--skip-git-repo-check" in cmd
        # Prompt passed via stdin, "-" is the stdin marker
        assert cmd[-1] == "-"
        prompt_input = self._mock_run.call_args[1].get("input", "")
        assert prompt_input == "hello"

    def test_model_flag(self):
        """Model is passed via --model flag."""
        rt = self._make_runtime(model="o3")
        rt._call([{"type": "text", "text": "hi"}], model="o3")
        cmd = self._mock_run.call_args[0][0]
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "o3"

    def test_image_from_file(self, tmp_path):
        """Image with path is passed via -i flag."""
        img_path = tmp_path / "test.png"
        img_path.write_bytes(b"\x89PNG" + b"\x00" * 10)

        rt = self._make_runtime()
        rt._call([{"type": "image", "path": str(img_path)}])
        cmd = self._mock_run.call_args[0][0]
        assert "-i" in cmd
        idx = cmd.index("-i")
        assert cmd[idx + 1] == str(img_path)

    def test_image_from_base64(self):
        """Image with base64 data is written to temp file and passed via -i."""
        import base64 as b64
        data = b64.b64encode(b"\x89PNG\x00" * 3).decode()
        rt = self._make_runtime()
        rt._call([{"type": "image", "data": data, "media_type": "image/png"}])
        cmd = self._mock_run.call_args[0][0]
        assert "-i" in cmd
        idx = cmd.index("-i")
        # Should be a temp file path
        assert "codex_img_" in cmd[idx + 1]

    def test_image_url_fallback_to_text(self):
        """Image with URL adds text note since codex CLI doesn't support URLs."""
        rt = self._make_runtime()
        rt._call([{"type": "image", "url": "https://example.com/img.png"}])
        cmd = self._mock_run.call_args[0][0]
        # No -i flag for URL
        assert "-i" not in cmd
        # URL should appear in prompt text (passed via stdin)
        prompt_input = self._mock_run.call_args[1].get("input", "")
        assert "https://example.com/img.png" in prompt_input

    def test_session_resume(self):
        """Second call uses 'resume' subcommand."""
        rt = self._make_runtime(session_id="test-session")
        rt._call([{"type": "text", "text": "first"}])
        cmd1 = self._mock_run.call_args[0][0]
        assert "resume" not in cmd1

        rt._call([{"type": "text", "text": "second"}])
        cmd2 = self._mock_run.call_args[0][0]
        assert "resume" in cmd2
        assert "test-session" in cmd2

    def test_auto_session_captures_thread_id_and_resumes(self):
        """Auto sessions resume only after Codex reports a real thread id."""
        replies = iter([
            '{"type":"thread.started","thread_id":"thread-123"}',
            '{"type":"thread.resumed","thread_id":"thread-123"}',
        ])

        def run_with_thread_id(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = next(replies)
            result.stderr = ""
            for i, arg in enumerate(cmd):
                if arg == "-o" and i + 1 < len(cmd):
                    with open(cmd[i + 1], "w") as f:
                        f.write("mock codex reply")
                    break
            return result

        self._mock_run.side_effect = run_with_thread_id
        rt = self._make_runtime()

        assert rt.has_session is False
        assert rt._session_id is None

        rt._call([{"type": "text", "text": "first"}])
        assert rt.has_session is True
        assert rt._session_id == "thread-123"
        cmd1 = self._mock_run.call_args[0][0]
        assert "resume" not in cmd1

        rt._call([{"type": "text", "text": "second"}])
        cmd2 = self._mock_run.call_args[0][0]
        assert "resume" in cmd2
        assert "thread-123" in cmd2

    def test_auto_session_without_thread_id_stays_stateless(self):
        """If Codex does not report a thread id, later calls should not resume."""
        rt = self._make_runtime()

        assert rt.has_session is False
        assert rt._session_id is None

        rt._call([{"type": "text", "text": "first"}])
        rt._call([{"type": "text", "text": "second"}])
        cmd = self._mock_run.call_args[0][0]
        assert "resume" not in cmd
        assert rt._session_id is None

    def test_stateless_mode(self):
        """session_id=None never uses resume."""
        rt = self._make_runtime(session_id=None)
        rt._call([{"type": "text", "text": "first"}])
        rt._call([{"type": "text", "text": "second"}])
        cmd = self._mock_run.call_args[0][0]
        assert "resume" not in cmd

    def test_workdir_flag(self):
        """workdir is passed via --cd flag."""
        rt = self._make_runtime(workdir="/tmp/myproject")
        rt._call([{"type": "text", "text": "hi"}])
        cmd = self._mock_run.call_args[0][0]
        idx = cmd.index("--cd")
        assert cmd[idx + 1] == "/tmp/myproject"

    def test_search_flag(self):
        """search=True adds the root-level --search flag."""
        rt = self._make_runtime(search=True)
        rt._call([{"type": "text", "text": "weather"}])
        cmd = self._mock_run.call_args[0][0]
        assert "--search" in cmd
        assert cmd.index("--search") < cmd.index("exec")

    def test_custom_approval_policy(self):
        """Custom approval policy is passed as a root-level flag."""
        rt = self._make_runtime(approval_policy="on-request")
        rt._call([{"type": "text", "text": "hi"}])
        cmd = self._mock_run.call_args[0][0]
        idx = cmd.index("-a")
        assert cmd[idx + 1] == "on-request"

    def test_response_format_appended(self):
        """response_format is appended to prompt text."""
        rt = self._make_runtime()
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        rt._call([{"type": "text", "text": "test"}], response_format=schema)
        # Prompt is passed via stdin
        prompt_input = self._mock_run.call_args[1].get("input", "")
        assert "JSON" in prompt_input

    def test_cli_not_found(self, monkeypatch):
        """Missing CLI raises FileNotFoundError."""
        monkeypatch.setattr("shutil.which", lambda name: None)
        from agentic.providers.codex import CodexRuntime
        with pytest.raises(FileNotFoundError, match="Codex CLI not found"):
            CodexRuntime(cli_path=None)

    def test_cli_error_propagates(self):
        """CLI errors are raised as RuntimeError."""
        def failing_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 1
            result.stderr = "something went wrong"
            result.stdout = ""
            return result

        self._mock_run.side_effect = failing_run
        rt = self._make_runtime()

        with pytest.raises(RuntimeError, match="Codex CLI error"):
            rt._call([{"type": "text", "text": "test"}])

    def test_auth_error(self):
        """Auth errors raise ConnectionError."""
        def auth_fail(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 1
            result.stderr = "Invalid API key"
            result.stdout = ""
            return result

        self._mock_run.side_effect = auth_fail
        rt = self._make_runtime()

        with pytest.raises(ConnectionError, match="authentication"):
            rt._call([{"type": "text", "text": "test"}])

    def test_timeout(self):
        """Timeout raises TimeoutError."""
        self._mock_run.side_effect = subprocess.TimeoutExpired(cmd="codex", timeout=10)
        rt = self._make_runtime(timeout=10)

        with pytest.raises(TimeoutError, match="timed out"):
            rt._call([{"type": "text", "text": "test"}])

    def test_reset(self):
        """reset() creates new session and resets turn count."""
        def run_with_thread_id(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = '{"type":"thread.started","thread_id":"thread-reset"}'
            result.stderr = ""
            for i, arg in enumerate(cmd):
                if arg == "-o" and i + 1 < len(cmd):
                    with open(cmd[i + 1], "w") as f:
                        f.write("mock codex reply")
                    break
            return result

        self._mock_run.side_effect = run_with_thread_id
        rt = self._make_runtime()
        rt._call([{"type": "text", "text": "first"}])
        old_session = rt._session_id
        rt.reset()
        assert old_session == "thread-reset"
        assert rt._session_id is None
        assert rt._turn_count == 0
        assert rt.has_session is False

    def test_sandbox_mode(self):
        """Custom sandbox mode without full_auto."""
        rt = self._make_runtime(full_auto=False, sandbox="read-only")
        rt._call([{"type": "text", "text": "hi"}])
        cmd = self._mock_run.call_args[0][0]
        assert "--full-auto" not in cmd
        idx = cmd.index("--sandbox")
        assert cmd[idx + 1] == "read-only"

    def test_audio_block_warns(self):
        """Audio blocks emit a warning and are skipped."""
        rt = self._make_runtime()
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            rt._call([{"type": "text", "text": "hi"}, {"type": "audio", "path": "test.wav"}])
            audio_warnings = [x for x in w if "audio" in str(x.message).lower()]
            assert len(audio_warnings) == 1

    def test_video_block_warns(self):
        """Video blocks emit a warning and are skipped."""
        rt = self._make_runtime()
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            rt._call([{"type": "text", "text": "hi"}, {"type": "video", "path": "test.mp4"}])
            video_warnings = [x for x in w if "video" in str(x.message).lower()]
            assert len(video_warnings) == 1

    def test_file_block_warns(self):
        """File/PDF blocks emit a warning and are skipped."""
        rt = self._make_runtime()
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            rt._call([{"type": "text", "text": "hi"}, {"type": "file", "path": "test.pdf"}])
            file_warnings = [x for x in w if "file" in str(x.message).lower()]
            assert len(file_warnings) == 1


def test_visualizer_codex_runtime_enables_search(monkeypatch):
    """Visualizer chat uses stateless Codex with native web search enabled."""
    from agentic.visualize import server

    captured = {}

    def fake_create_runtime(provider=None, model=None, **kwargs):
        captured["provider"] = provider
        captured["model"] = model
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr("agentic.providers.create_runtime", fake_create_runtime)

    server._create_runtime_for_visualizer("codex")

    assert captured["provider"] == "codex"
    assert captured["kwargs"]["session_id"] is None
    assert captured["kwargs"]["search"] is True



# ══════════════════════════════════════════════════════════════
# ClaudeCodeRuntime unsupported modality tests
# ══════════════════════════════════════════════════════════════

class TestClaudeCodeRuntimeUnsupported:
    """Tests that ClaudeCodeRuntime warns on unsupported modalities."""

    @pytest.fixture(autouse=True)
    def setup_mock(self, monkeypatch):
        """Mock shutil.which and subprocess.Popen for persistent process mode."""
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/claude" if name == "claude" else None)

        # Mock Popen to simulate a persistent claude process
        self._mock_stdin = MagicMock()
        self._mock_stdout = MagicMock()
        self._mock_proc = MagicMock()
        self._mock_proc.poll.return_value = None  # process is alive
        self._mock_proc.stdin = self._mock_stdin
        self._mock_proc.stdout = self._mock_stdout
        self._mock_proc.stderr = MagicMock()

        # _read_response reads lines from stdout; return a result message
        self._mock_stdout.readline.side_effect = [
            '{"type":"result","result":"mock reply"}\n',
        ]

        self._orig_popen = subprocess.Popen
        monkeypatch.setattr("subprocess.Popen", lambda *a, **kw: self._mock_proc)

    def _reset_stdout(self):
        """Reset mock stdout for a fresh _call."""
        self._mock_stdout.readline.side_effect = [
            '{"type":"result","result":"mock reply"}\n',
        ]

    def _make_runtime(self, **kwargs):
        from agentic.providers.claude_code import ClaudeCodeRuntime
        return ClaudeCodeRuntime(cli_path="/usr/bin/claude", **kwargs)

    def test_audio_block_warns(self):
        """Audio blocks emit a warning and are filtered out."""
        rt = self._make_runtime()
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            rt._call([{"type": "text", "text": "hi"}, {"type": "audio", "path": "test.wav"}])
            audio_warnings = [x for x in w if "audio" in str(x.message).lower()]
            assert len(audio_warnings) == 1

    def test_video_block_warns(self):
        """Video blocks emit a warning and are filtered out."""
        rt = self._make_runtime()
        self._reset_stdout()
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            rt._call([{"type": "text", "text": "hi"}, {"type": "video", "path": "test.mp4"}])
            video_warnings = [x for x in w if "video" in str(x.message).lower()]
            assert len(video_warnings) == 1

    def test_file_block_warns(self):
        """File/PDF blocks emit a warning and are filtered out."""
        rt = self._make_runtime()
        self._reset_stdout()
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            rt._call([{"type": "text", "text": "hi"}, {"type": "file", "path": "test.pdf"}])
            file_warnings = [x for x in w if "file" in str(x.message).lower()]
            assert len(file_warnings) == 1

    def test_unknown_block_with_text_fallback(self):
        """Unknown blocks with text fall back to text content."""
        rt = self._make_runtime()
        self._reset_stdout()
        result = rt._call([{"type": "custom", "text": "fallback text"}])
        assert result == "mock reply"
        # Verify the text was sent via stdin
        written = self._mock_stdin.write.call_args[0][0]
        msg = json.loads(written.strip())
        content = msg["message"]["content"]
        assert any(block.get("type") == "text" and block.get("text") == "fallback text" for block in content)


# ══════════════════════════════════════════════════════════════
# Provider lazy import tests
# ══════════════════════════════════════════════════════════════

class TestGeminiCLIRuntime:
    """Tests for GeminiCLIRuntime with mocked subprocess."""

    @pytest.fixture(autouse=True)
    def setup_mock(self, monkeypatch):
        """Mock shutil.which and subprocess.run."""
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/gemini" if name == "gemini" else None)

        def mock_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = "mock gemini reply"
            result.stderr = ""
            return result

        self._mock_run = MagicMock(side_effect=mock_run)
        monkeypatch.setattr("subprocess.run", self._mock_run)

    def _make_runtime(self, **kwargs):
        from agentic.providers.gemini_cli import GeminiCLIRuntime
        return GeminiCLIRuntime(cli_path="/usr/bin/gemini", **kwargs)

    def test_unknown_block_with_text_fallback(self):
        """Unknown blocks with text fall back to plain text."""
        rt = self._make_runtime()
        result = rt._call([{"type": "custom", "text": "fallback text"}])
        assert result == "mock gemini reply"
        cmd = self._mock_run.call_args[0][0]
        # prompt is at index 1 (no -p flag)
        assert cmd[1] == "fallback text"

    def test_missing_type_defaults_to_text(self):
        """Blocks without type default to text instead of raising KeyError."""
        rt = self._make_runtime()
        result = rt._call([{"text": "implicit text"}])
        assert result == "mock gemini reply"
        cmd = self._mock_run.call_args[0][0]
        assert cmd[1] == "implicit text"


# ═══════════════════════════════════════════════════════════���══
# general_action tests
# ════════════════════════��═════════════════════════════��═══════

class TestGeneralAction:
    """Tests for general_action agentic function."""

    def test_json_response(self):
        """general_action parses JSON response from LLM."""
        from agentic.functions.general_action import general_action
        from agentic.runtime import Runtime

        rt = Runtime(
            call=lambda *a, **kw: '{"success": true, "output": "installed numpy", "error": null}'
        )
        result = general_action(instruction="install numpy", runtime=rt)
        assert result["success"] is True
        assert "numpy" in result["output"]

    def test_markdown_json_response(self):
        """general_action extracts JSON from markdown fences."""
        from agentic.functions.general_action import general_action
        from agentic.runtime import Runtime

        rt = Runtime(
            call=lambda *a, **kw: 'Here is the result:\n```json\n{"success": true, "output": "done", "error": null}\n```'
        )
        result = general_action(instruction="do something", runtime=rt)
        assert result["success"] is True

    def test_plain_text_fallback(self):
        """general_action falls back when LLM returns plain text."""
        from agentic.functions.general_action import general_action
        from agentic.runtime import Runtime

        rt = Runtime(call=lambda *a, **kw: "I completed the task successfully.")
        result = general_action(instruction="do something", runtime=rt)
        assert result["success"] is True
        assert "completed" in result["output"]

    def test_error_response(self):
        """general_action handles error JSON."""
        from agentic.functions.general_action import general_action
        from agentic.runtime import Runtime

        rt = Runtime(
            call=lambda *a, **kw: '{"success": false, "output": "", "error": "file not found"}'
        )
        result = general_action(instruction="read missing file", runtime=rt)
        assert result["success"] is False
        assert "not found" in result["error"]

    def test_no_runtime_raises(self):
        """general_action raises ValueError without runtime."""
        from agentic.functions.general_action import general_action
        with pytest.raises(ValueError, match="runtime is required"):
            general_action(instruction="hello")


# ══════════════════════════════════════════════════════════════
# agent_loop tests
# ══════════════════════════════════════════════════════════════

class TestAgentLoop:
    """Tests for agent_loop autonomous execution."""

    @staticmethod
    def _mock_call(step_responses):
        """Create a mock call that handles both _step and wait calls.

        step_responses: list of JSON strings for _step calls (consumed in order).
        wait calls are auto-detected by content and return wait=0.
        """
        step_idx = [0]
        def mock(content, **kw):
            # Detect wait calls by checking content text
            text = ""
            for block in content:
                if isinstance(block, dict) and "text" in block:
                    text += block["text"]
            if "Action just completed" in text:
                return '{"wait": 0, "reason": "test"}'
            # Step call
            idx = step_idx[0]
            step_idx[0] += 1
            if idx < len(step_responses):
                return step_responses[idx]
            return step_responses[-1]  # repeat last
        return mock

    def test_done_on_first_step(self):
        """agent_loop stops when LLM reports done=true."""
        from agentic.functions.agent_loop import agent_loop
        from agentic.runtime import Runtime

        rt = Runtime(call=self._mock_call([
            '{"done": true, "action": "wrote paper", "result": "complete", "next": null, "error": null}',
        ]))
        result = agent_loop(goal="write a paper", runtime=rt, max_steps=10, state_dir="/tmp/ap-test-state")
        assert result["done"] is True
        assert result["steps"] == 1

    def test_multi_step(self):
        """agent_loop runs multiple steps until done."""
        from agentic.functions.agent_loop import agent_loop
        from agentic.runtime import Runtime

        rt = Runtime(call=self._mock_call([
            '{"done": false, "action": "research", "result": "found papers", "next": "write intro", "error": null}',
            '{"done": false, "action": "write intro", "result": "drafted", "next": "finalize", "error": null}',
            '{"done": true, "action": "finalize", "result": "complete", "next": null, "error": null}',
        ]))
        result = agent_loop(goal="write survey", runtime=rt, max_steps=10, state_dir="/tmp/ap-test-state")
        assert result["done"] is True
        assert result["steps"] == 3

    def test_max_steps_reached(self):
        """agent_loop stops at max_steps."""
        from agentic.functions.agent_loop import agent_loop
        from agentic.runtime import Runtime

        rt = Runtime(call=self._mock_call([
            '{"done": false, "action": "work", "result": "progress", "next": "more", "error": null}',
        ]))
        result = agent_loop(goal="infinite task", runtime=rt, max_steps=3, state_dir="/tmp/ap-test-state")
        assert result["done"] is False
        assert result["steps"] == 3
        assert "max_steps" in result.get("error", "")

    def test_callback_can_cancel(self):
        """Returning False from callback stops the loop."""
        from agentic.functions.agent_loop import agent_loop
        from agentic.runtime import Runtime

        rt = Runtime(call=self._mock_call([
            '{"done": false, "action": "work", "result": "ok", "next": "more", "error": null}',
        ]))
        result = agent_loop(goal="task", runtime=rt, max_steps=100, state_dir="/tmp/ap-test-state", callback=lambda r: False)
        assert result["done"] is True
        assert result.get("cancelled") is True
        assert result["steps"] == 1

    def test_handles_exception(self):
        """agent_loop records errors and continues."""
        from agentic.functions.agent_loop import agent_loop
        from agentic.runtime import Runtime

        call_count = [0]
        def mock(content, **kw):
            text = ""
            for block in content:
                if isinstance(block, dict) and "text" in block:
                    text += block["text"]
            if "Action just completed" in text:
                return '{"wait": 0, "reason": "test"}'
            call_count[0] += 1
            if call_count[0] == 1:
                raise ConnectionError("network down")
            return '{"done": true, "action": "retry", "result": "ok", "next": null, "error": null}'

        rt = Runtime(call=mock, max_retries=1)
        result = agent_loop(goal="fragile task 3", runtime=rt, max_steps=5, state_dir="/tmp/ap-test-state")
        assert result["done"] is True
        assert result["steps"] == 2
        assert "error" in result["history"][0]["error"].lower()
        assert result["history"][1]["done"] is True

    def test_no_runtime_raises(self):
        """agent_loop raises ValueError without runtime."""
        from agentic.functions.agent_loop import agent_loop
        with pytest.raises(ValueError, match="runtime is required"):
            agent_loop(goal="hello")

    def test_state_persistence(self, tmp_path):
        """agent_loop persists state to disk."""
        from agentic.functions.agent_loop import agent_loop
        from agentic.runtime import Runtime

        rt = Runtime(call=self._mock_call([
            '{"done": true, "action": "done", "result": "ok", "next": null, "error": null}',
        ]))
        state_dir = str(tmp_path)
        result = agent_loop(goal="persist test", runtime=rt, state_dir=state_dir)
        assert result["done"] is True

        state_files = list(tmp_path.glob("agent_loop_*.json"))
        assert len(state_files) == 1

        import json
        with open(state_files[0]) as f:
            saved = json.load(f)
        assert saved["goal"] == "persist test"
        assert saved["done"] is True


# ══════════════════════════════════════════════════════════════
# wait tests
# ══════════════════════════════════════════════════════════════

class TestWait:
    """Tests for wait agentic function."""

    def test_returns_seconds(self):
        """wait returns the number of seconds decided by LLM."""
        from agentic.functions.wait import wait
        from agentic.runtime import Runtime

        rt = Runtime(call=lambda *a, **kw: '{"wait": 0, "reason": "check immediately"}')
        seconds = wait(action="wrote a file", runtime=rt)
        assert seconds == 0

    def test_parses_nonzero_wait(self):
        """wait parses a nonzero wait time. Note: sleep is called internally."""
        from agentic.functions.wait import wait
        from agentic.runtime import Runtime
        from unittest.mock import patch

        rt = Runtime(call=lambda *a, **kw: '{"wait": 5, "reason": "server starting"}')
        with patch("agentic.functions.wait.time.sleep") as mock_sleep:
            seconds = wait(action="started server", runtime=rt)
            assert seconds == 5
            mock_sleep.assert_called_once_with(5)

    def test_fallback_on_bad_json(self):
        """wait defaults to 0 if LLM returns unparseable response."""
        from agentic.functions.wait import wait
        from agentic.runtime import Runtime

        rt = Runtime(call=lambda *a, **kw: "I think you should wait a bit")
        seconds = wait(action="did something", runtime=rt)
        assert seconds == 0

    def test_no_runtime_raises(self):
        """wait raises ValueError without runtime."""
        from agentic.functions.wait import wait
        with pytest.raises(ValueError, match="runtime is required"):
            wait(action="hello")


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
