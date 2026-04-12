"""build_catalog — render a function registry into readable text for LLM dispatch."""

from __future__ import annotations


def _format_type(value) -> str:
    """Return a compact display name for a type-like object."""
    if value is None:
        return "any"
    if isinstance(value, str):
        return value
    return getattr(value, "__name__", str(value))


def build_catalog(available: dict) -> str:
    """Build a readable catalog from an Agentic dispatch registry.

    Args:
        available: Mapping of function name to registry metadata.

    Returns:
        Multi-line text describing callable functions and their LLM-provided args.
    """
    if not available:
        return "(no functions available)"

    blocks: list[str] = []
    for name, spec in available.items():
        description = spec.get("description", "")
        lines = [f"- {name}: {description}".rstrip()]

        input_spec = spec.get("input", {}) or {}
        llm_params = [
            (param, meta)
            for param, meta in input_spec.items()
            if (meta or {}).get("source") == "llm"
        ]
        if llm_params:
            lines.append("  inputs:")
            for param, meta in llm_params:
                meta = meta or {}
                bits = [f"type={_format_type(meta.get('type'))}"]
                options = meta.get("options")
                if options:
                    bits.append("options=" + ", ".join(map(str, options)))
                desc = meta.get("description")
                if desc:
                    bits.append(desc)
                lines.append(f"    - {param}: {'; '.join(bits)}")

        output_spec = spec.get("output")
        if output_spec:
            if isinstance(output_spec, dict):
                rendered = ", ".join(
                    f"{key}: {_format_type(value)}" for key, value in output_spec.items()
                )
            else:
                rendered = _format_type(output_spec)
            lines.append(f"  output: {rendered}")

        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)
