"""Generate the Visual Document JSON Schema and the frontend TypeScript types.

``shared/visual_document.py`` is the only place the schema is defined. This script
projects it into two generated artifacts:

* ``shared/visual_document.schema.json`` - contract for validation/documentation
* ``new-frontend/app/src/types/visualDocument.generated.ts`` - frontend wire types

Run after any schema change::

    python shared/visual_schema_export.py

``backend/tests/test_visual_document.py`` fails if the checked-in artifacts differ
from a fresh generation, so the TS types can never silently drift from Python.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared import visual_document as vd  # noqa: E402

SCHEMA_PATH = ROOT / "shared" / "visual_document.schema.json"
TS_PATH = ROOT / "new-frontend" / "app" / "src" / "types" / "visualDocument.generated.ts"

HEADER = """/**
 * GENERATED FILE - DO NOT EDIT.
 *
 * Source of truth: shared/visual_document.py
 * Regenerate with: python shared/visual_schema_export.py
 *
 * Wire format is snake_case to match the FastAPI payloads exactly.
 */
"""


def build_schema() -> dict[str, Any]:
    schema = vd.VisualDocument.model_json_schema(ref_template="#/$defs/{model}")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "VisualDocument"
    schema["$id"] = "https://eventhorizon.local/schemas/visual-document-1.0.json"
    return schema


# ---------------------------------------------------------------------------
# TypeScript emission
# ---------------------------------------------------------------------------

_PRIMITIVES = {
    "string": "string",
    "integer": "number",
    "number": "number",
    "boolean": "boolean",
    "null": "null",
}


def _literal(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(value)
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def ts_type(node: Any) -> str:
    """Map one JSON Schema node to a TypeScript type expression."""
    if node is True or node is None:
        return "unknown"
    if not isinstance(node, dict):
        return "unknown"

    if "$ref" in node:
        return node["$ref"].rsplit("/", 1)[-1]

    if "const" in node:
        return _literal(node["const"])

    if "enum" in node:
        return " | ".join(_literal(v) for v in node["enum"])

    for key in ("anyOf", "oneOf"):
        if key in node:
            parts = [ts_type(sub) for sub in node[key]]
            deduped: list[str] = []
            for part in parts:
                if part not in deduped:
                    deduped.append(part)
            return " | ".join(deduped) if deduped else "unknown"

    if "allOf" in node and len(node["allOf"]) == 1:
        return ts_type(node["allOf"][0])

    node_type = node.get("type")
    if isinstance(node_type, list):
        return " | ".join(_PRIMITIVES.get(t, "unknown") for t in node_type)

    if node_type == "array":
        item = ts_type(node.get("items", True))
        wrapped = f"({item})" if " | " in item else item
        return f"{wrapped}[]"

    if node_type == "object":
        if node.get("properties"):
            fields = ", ".join(
                f"{name}: {ts_type(sub)}" for name, sub in node["properties"].items()
            )
            return "{ " + fields + " }"
        additional = node.get("additionalProperties", True)
        value = "unknown" if additional in (True, None) else ts_type(additional)
        return f"Record<string, {value}>"

    if node_type in _PRIMITIVES:
        return _PRIMITIVES[node_type]

    return "unknown"


def _doc_comment(text: str | None, indent: str = "") -> list[str]:
    if not text:
        return []
    first = text.strip().splitlines()[0].strip()
    if not first:
        return []
    return [f"{indent}/** {first} */"]


def emit_interface(name: str, node: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.extend(_doc_comment(node.get("description")))
    lines.append(f"export interface {name} {{")
    required = set(node.get("required", []))
    for field, sub in node.get("properties", {}).items():
        lines.extend(_doc_comment(sub.get("description"), "  "))
        optional = "" if field in required else "?"
        lines.append(f"  {field}{optional}: {ts_type(sub)};")
    lines.append("}")
    return "\n".join(lines)


def emit_alias(name: str, node: dict[str, Any]) -> str:
    lines = _doc_comment(node.get("description"))
    lines.append(f"export type {name} = {ts_type(node)};")
    return "\n".join(lines)


def _union_from(node: dict[str, Any]) -> str | None:
    """Extract a discriminated-union type expression from an array/property node."""
    target = node.get("items", node)
    if not isinstance(target, dict):
        return None
    for key in ("oneOf", "anyOf"):
        if key in target:
            return " | ".join(ts_type(sub) for sub in target[key])
    return None


def build_typescript(schema: dict[str, Any]) -> str:
    defs: dict[str, Any] = schema.get("$defs", {})
    blocks: list[str] = [HEADER.rstrip()]

    limits = {
        "SCHEMA_VERSION": vd.SCHEMA_VERSION,
        "CANVAS_MIN": vd.CANVAS_MIN,
        "CANVAS_MAX": vd.CANVAS_MAX,
        "MIN_ELEMENT_SIZE": vd.MIN_ELEMENT_SIZE,
        "MAX_ELEMENT_SIZE": vd.MAX_ELEMENT_SIZE,
        "MIN_ZOOM": vd.MIN_ZOOM,
        "MAX_ZOOM": vd.MAX_ZOOM,
        "MAX_ELEMENTS": vd.MAX_ELEMENTS,
        "MAX_HISTORY": vd.MAX_HISTORY,
    }
    limit_lines = ["/** Canvas limits mirrored from the Python schema. */", "export const VISUAL_LIMITS = {"]
    for key, value in limits.items():
        limit_lines.append(f"  {key}: {json.dumps(value)},")
    limit_lines.append("} as const;")
    blocks.append("\n".join(limit_lines))

    for name in sorted(defs):
        node = defs[name]
        if node.get("properties") is not None and node.get("type", "object") == "object":
            blocks.append(emit_interface(name, node))
        else:
            blocks.append(emit_alias(name, node))

    root_name = schema.get("title", "VisualDocument")
    blocks.append(emit_interface(root_name, schema))

    element_union = _union_from(schema.get("properties", {}).get("elements", {}))
    if element_union:
        blocks.append(f"export type VisualElement = {element_union};")
        blocks.append("export type VisualElementType = VisualElement['type'];")

    commit = defs.get("Commit", {})
    op_union = _union_from(commit.get("properties", {}).get("ops", {}))
    if op_union:
        blocks.append(f"export type VisualOp = {op_union};")
        blocks.append("export type VisualOpName = VisualOp['op'];")

    return "\n\n".join(blocks) + "\n"


def generate() -> tuple[str, str]:
    schema = build_schema()
    schema_text = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    return schema_text, build_typescript(schema)


def main() -> int:
    schema_text, ts_text = generate()
    SCHEMA_PATH.write_text(schema_text, encoding="utf-8")
    TS_PATH.parent.mkdir(parents=True, exist_ok=True)
    TS_PATH.write_text(ts_text, encoding="utf-8")
    print(f"wrote {SCHEMA_PATH.relative_to(ROOT)} ({len(schema_text)} bytes)")
    print(f"wrote {TS_PATH.relative_to(ROOT)} ({len(ts_text)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
