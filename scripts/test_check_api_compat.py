import copy
from typing import Any

from check_api_compat import breaking_changes

CONTRACT: dict[str, Any] = {
    "paths": {
        "/api/v1/devices/{device_id}/weight": {
            "put": {
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/WeightRequest"}
                        }
                    }
                }
            }
        },
        "/api/v1/health": {"get": {}},
    },
    "components": {
        "schemas": {
            "WeightRequest": {
                "properties": {
                    "grams": {"type": "integer"},
                    "stable": {"type": "boolean", "default": True},
                },
                "required": ["grams"],
            },
            "Health": {"properties": {"status": {"type": "string"}, "version": {"type": "string"}}},
        }
    },
}


def changed(edit: Any) -> dict[str, Any]:
    new = copy.deepcopy(CONTRACT)
    edit(new)
    return new


def test_identical_contract_is_compatible() -> None:
    assert breaking_changes(CONTRACT, CONTRACT) == []


def test_additions_are_compatible() -> None:
    def add(new: dict[str, Any]) -> None:
        new["paths"]["/api/v1/devices"] = {"get": {}}
        new["components"]["schemas"]["Health"]["properties"]["uptime"] = {"type": "integer"}
        new["components"]["schemas"]["WeightRequest"]["properties"]["note"] = {"type": "string"}
        new["components"]["schemas"]["Health"]["properties"]["status"]["description"] = "reworded"

    assert breaking_changes(CONTRACT, changed(add)) == []


def test_removed_endpoint_is_breaking() -> None:
    assert breaking_changes(CONTRACT, changed(lambda new: new["paths"].pop("/api/v1/health"))) == [
        "GET /api/v1/health was removed"
    ]


def test_removed_or_retyped_field_is_breaking() -> None:
    def edit(new: dict[str, Any]) -> None:
        new["components"]["schemas"]["Health"]["properties"].pop("version")
        new["components"]["schemas"]["WeightRequest"]["properties"]["grams"] = {"type": "number"}

    assert breaking_changes(CONTRACT, changed(edit)) == [
        "WeightRequest.grams changed type",
        "Health.version was removed",
    ]


def test_newly_required_request_field_is_breaking() -> None:
    def edit(new: dict[str, Any]) -> None:
        new["components"]["schemas"]["WeightRequest"]["required"] = ["grams", "stable"]

    assert breaking_changes(CONTRACT, changed(edit)) == ["WeightRequest.stable became required"]
