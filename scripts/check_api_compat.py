# /// script
# requires-python = ">=3.13"
# ///
"""Fail when the control API breaks its /api/v1 contract (control-api spec, "Versioned and stable contract").

    uv run scripts/check_api_compat.py            # compare the code with docs/api/openapi-v1.json
    uv run scripts/check_api_compat.py --update   # accept the current API as the contract

Allowed within /api/v1: new endpoints, new optional request fields, new response fields.
Breaking: a removed endpoint or method, a removed field, a changed field type, or a request
field that became required. A breaking change belongs under a new /api/v2 instead.

Error codes and event types are part of the contract too, but OpenAPI does not describe them;
reviewers check those by hand.
"""

import json
import sys
from pathlib import Path
from typing import Any

SNAPSHOT = Path(__file__).parent.parent / "docs" / "api" / "openapi-v1.json"
IGNORED_KEYS = {"title", "description", "default", "examples"}


def current_openapi() -> dict[str, Any]:
    from emupos.api.app import create_app
    from emupos.config import demo_config
    from emupos.daemon import Simulator

    return create_app(Simulator(demo_config(platform="linux"))).openapi()


def breaking_changes(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    for path, operations in old.get("paths", {}).items():
        for method in operations:
            if method not in new.get("paths", {}).get(path, {}):
                problems.append(f"{method.upper()} {path} was removed")
    old_schemas = old.get("components", {}).get("schemas", {})
    new_schemas = new.get("components", {}).get("schemas", {})
    request_schemas = _request_schema_names(old)
    for name, schema in old_schemas.items():
        if name not in new_schemas:
            problems.append(f"schema {name} was removed")
            continue
        problems += _property_changes(
            name, schema, new_schemas[name], request=name in request_schemas
        )
    return problems


def _property_changes(
    name: str, old: dict[str, Any], new: dict[str, Any], *, request: bool
) -> list[str]:
    problems: list[str] = []
    new_properties = new.get("properties", {})
    for field, definition in old.get("properties", {}).items():
        if field not in new_properties:
            problems.append(f"{name}.{field} was removed")
        elif _shape(definition) != _shape(new_properties[field]):
            problems.append(f"{name}.{field} changed type")
    if request:
        newly_required = set(new.get("required", [])) - set(old.get("required", []))
        problems += [f"{name}.{field} became required" for field in sorted(newly_required)]
    return problems


def _request_schema_names(openapi: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for operations in openapi.get("paths", {}).values():
        for operation in operations.values():
            content = operation.get("requestBody", {}).get("content", {})
            for media in content.values():
                reference = media.get("schema", {}).get("$ref", "")
                names.add(reference.rsplit("/", 1)[-1])
    return names


def _shape(definition: Any) -> Any:
    """A field's type without human-readable metadata, for comparison."""
    if isinstance(definition, dict):
        return {key: _shape(value) for key, value in definition.items() if key not in IGNORED_KEYS}
    if isinstance(definition, list):
        return [_shape(item) for item in definition]
    return definition


def main() -> None:
    current = current_openapi()
    if "--update" in sys.argv:
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {SNAPSHOT}")
        return
    problems = breaking_changes(json.loads(SNAPSHOT.read_text(encoding="utf-8")), current)
    for problem in problems:
        print(f"breaking change in /api/v1: {problem}")
    if problems:
        raise SystemExit(1)
    print("the control API is compatible with docs/api/openapi-v1.json")


if __name__ == "__main__":
    main()
