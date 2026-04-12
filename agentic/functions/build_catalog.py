"""build_catalog — render an LLM-facing catalog from an available-function registry."""

from __future__ import annotations


def _type_name(value) -> str:
    if isinstance(value, type):
        return value.__name__
    return str(value)


def build_catalog(available: dict[str, dict]) -> str:
    """Render a compact text catalog for dispatch-style agentic functions."""
    lines: list[str] = []
    for name, spec in available.items():
        lines.append(f"- {name}: {spec.get('description', '').strip()}")
        inputs = spec.get("input", {}) or {}
        if inputs:
            lines.append("  inputs:")
            for param, meta in inputs.items():
                source = meta.get("source", "llm")
                details = [f"source={source}"]
                if "type" in meta:
                    details.append(f"type={_type_name(meta['type'])}")
                if meta.get("options"):
                    details.append(f"options={list(meta['options'])}")
                if meta.get("description"):
                    details.append(f"description={meta['description']}")
                lines.append(f"    - {param}: {', '.join(details)}")
        output = spec.get("output")
        if output:
            lines.append(f"  output: {output}")
    return "\n".join(lines)
