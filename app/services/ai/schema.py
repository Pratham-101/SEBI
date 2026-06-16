"""Build OpenAI-compatible strict JSON schemas from Pydantic models."""

from __future__ import annotations

import copy
from typing import Any

from pydantic import BaseModel


def _resolve_ref(ref: str, defs: dict[str, Any]) -> dict[str, Any]:
    if ref.startswith("#/$defs/"):
        name = ref.removeprefix("#/$defs/")
    elif ref.startswith("#/definitions/"):
        name = ref.removeprefix("#/definitions/")
    else:
        raise ValueError(f"Unsupported schema ref: {ref}")
    if name not in defs:
        raise ValueError(f"Missing schema definition: {name}")
    return copy.deepcopy(defs[name])


def _inline_refs(node: Any, defs: dict[str, Any]) -> Any:
    if isinstance(node, dict):
        if "$ref" in node:
            return _inline_refs(_resolve_ref(node["$ref"], defs), defs)
        return {k: _inline_refs(v, defs) for k, v in node.items()}
    if isinstance(node, list):
        return [_inline_refs(item, defs) for item in node]
    return node


def _strip_defaults(node: Any) -> None:
    """OpenAI strict json_schema rejects `default` on properties."""
    if isinstance(node, dict):
        if "properties" in node:
            for prop in node["properties"].values():
                prop.pop("default", None)
        for value in node.values():
            _strip_defaults(value)
    elif isinstance(node, list):
        for item in node:
            _strip_defaults(item)


def _patch_strict_object(node: Any) -> None:
    if isinstance(node, dict):
        if node.get("type") == "object" or "properties" in node:
            node["additionalProperties"] = False
            props = node.get("properties", {})
            if props:
                node["required"] = list(props.keys())
        for value in node.values():
            if isinstance(value, dict):
                _patch_strict_object(value)
            elif isinstance(value, list):
                for item in value:
                    _patch_strict_object(item)
    elif isinstance(node, list):
        for item in node:
            _patch_strict_object(item)


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Schema for OpenAI structured outputs (strict mode, no $ref)."""
    raw = model.model_json_schema()
    defs = raw.pop("$defs", None) or raw.pop("definitions", None) or {}
    schema = _inline_refs(raw, defs) if defs else raw
    _strip_defaults(schema)
    _patch_strict_object(schema)
    schema.pop("$defs", None)
    schema.pop("definitions", None)
    if "properties" in schema:
        schema["additionalProperties"] = False
        schema["required"] = list(schema["properties"].keys())
    return schema
