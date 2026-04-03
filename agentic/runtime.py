"""
runtime — LLM call interface with automatic Context integration.

When you call runtime.exec() inside an @agentic_function:

    1. READS from the Context tree:
       Calls ctx.summarize() using the function's `summarize` config
       to build context text. This text is prepended to the LLM prompt.

    2. CALLS the LLM:
       Builds a message list and calls the provided `call` function.

    3. WRITES to the Context tree:
       Records input, media, and raw_reply on the current Context node.

If called outside any @agentic_function, it works as a plain LLM call
with no context injection or recording.

Usage:
    from agentic import agentic_function, runtime

    @agentic_function
    def observe(task):
        '''Look at the screen and describe what you see.'''
        img = take_screenshot()
        return runtime.exec(
            prompt=observe.__doc__,
            input={"task": task},
            images=[img],
            call=my_llm_provider,
        )
"""

from __future__ import annotations

import json
from typing import Any, Optional

from agentic.context import _current_ctx


def exec(
    prompt: str,
    input: dict = None,
    images: list[str] = None,
    context: str = None,
    schema: dict = None,
    model: str = "sonnet",
    call: Any = None,
) -> str:
    """
    Call an LLM and auto-record to the current Context.

    Args:
        prompt:   Instructions for the LLM.

        input:    Structured data to include in the prompt.
                  Serialized as JSON under an [Input] header.

        images:   Image file paths to include.
                  Currently passed as text placeholders — actual image
                  encoding depends on the `call` provider.

        context:  Override auto-generated context string.
                  If None (default): auto-generates from the Context tree
                  using the function's summarize config.
                  If provided: used as-is, no tree query.

        schema:   Expected JSON output schema.
                  Appended as a "return only valid JSON" instruction.

        model:    Model name or alias. Passed to the `call` function.

        call:     LLM provider function.
                  Signature: fn(messages: list[dict], model: str) -> str
                  If None, raises NotImplementedError.

    Returns:
        str — the LLM's reply text.
    """
    ctx = _current_ctx.get(None)

    # --- Guard: one runtime.exec() per function ---
    if ctx is not None and ctx.raw_reply:
        raise RuntimeError(
            f"runtime.exec() called twice in {ctx.name}(). "
            f"Each @agentic_function should call runtime.exec() at most once. "
            f"Split into separate @agentic_function calls."
        )

    # --- Read: auto-generate context from the tree ---
    if context is None and ctx is not None:
        if ctx._summarize_kwargs:
            context = ctx.summarize(**ctx._summarize_kwargs)
        else:
            context = ctx.summarize()

    # --- Write: record what we're sending ---
    if ctx is not None:
        ctx.input = input
        ctx.media = images

    # --- Call the LLM ---
    messages = _build_messages(prompt, input, images, context, schema)

    if call is not None:
        reply = call(messages, model=model)
    else:
        reply = _default_api_call(messages, model=model)

    # --- Write: record what we got back ---
    if ctx is not None:
        ctx.raw_reply = reply

    return reply


# ======================================================================
# Message building
# ======================================================================

def _build_messages(prompt, input=None, images=None, context=None, schema=None):
    """
    Build the message list for the LLM API.

    Message layout (optimized for prompt cache hit rate):

        1. [Context] block     — from summarize(), stable prefix across calls
        2. [Assistant ack]     — "Understood." (keeps context as cacheable prefix)
        3. Prompt + [Input]    — the actual task (new content each call)
        4. [Schema]            — JSON output constraint (if any)

    The context block is placed FIRST because it's the most stable part.
    Each successive call appends new siblings to the context, so the prefix
    grows monotonically — maximizing prompt cache hits.
    """
    messages = []

    # Context as stable prefix
    if context:
        messages.append({"role": "user", "content": f"[Context]\n{context}"})
        messages.append({"role": "assistant", "content": "Understood."})

    # Prompt + input (new each call)
    content_parts = [{"type": "text", "text": prompt}]

    if input:
        input_str = json.dumps(input, ensure_ascii=False, default=str)
        content_parts.append({"type": "text", "text": f"\n[Input]\n{input_str}"})

    if images:
        for img_path in images:
            content_parts.append({"type": "text", "text": f"\n[Image: {img_path}]"})

    messages.append({"role": "user", "content": content_parts})

    # Schema constraint
    if schema:
        schema_str = json.dumps(schema, indent=2)
        messages.append({
            "role": "user",
            "content": f"Return ONLY valid JSON matching this schema:\n{schema_str}",
        })

    return messages


async def async_exec(
    prompt: str,
    input: dict = None,
    images: list[str] = None,
    context: str = None,
    schema: dict = None,
    model: str = "sonnet",
    call: Any = None,
) -> str:
    """
    Async version of exec(). Same behavior, but awaits the call function.

    The `call` function must be async: async fn(messages, model) -> str
    """
    ctx = _current_ctx.get(None)

    if ctx is not None and ctx.raw_reply:
        raise RuntimeError(
            f"runtime.async_exec() called twice in {ctx.name}(). "
            f"Each @agentic_function should call runtime.exec/async_exec at most once. "
            f"Split into separate @agentic_function calls."
        )

    if context is None and ctx is not None:
        if ctx._summarize_kwargs:
            context = ctx.summarize(**ctx._summarize_kwargs)
        else:
            context = ctx.summarize()

    if ctx is not None:
        ctx.input = input
        ctx.media = images

    messages = _build_messages(prompt, input, images, context, schema)

    if call is not None:
        reply = await call(messages, model=model)
    else:
        raise NotImplementedError(
            "No async LLM API configured. Pass `call=your_async_function` to runtime.async_exec().\n"
            "The call function should have signature: async fn(messages, model) -> str"
        )

    if ctx is not None:
        ctx.raw_reply = reply

    return reply


def _default_api_call(messages, model="sonnet"):
    """Placeholder. Users must provide a `call` function."""
    raise NotImplementedError(
        "No LLM API configured. Pass `call=your_function` to runtime.exec().\n"
        "The call function should have signature: fn(messages, model) -> str"
    )
