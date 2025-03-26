# ruff: noqa: D100, D101, D102, D107
from collections.abc import Mapping
import logging

import voluptuous as vol

from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import VolSchemaType

_LOGGER = logging.getLogger(__name__)


_ADDITIONAL_PROPERTIES_MARKER = [
    "additional properties",
]


def vol_to_jsonschema(name: str, schema: VolSchemaType) -> dict | None:  # noqa: C901
    """Convert a vol schema to JSON Schema.

    This is a best-effort, not a perfect translation, since vol schemas can be dynamic. It attempts
    to account for several common Home Assistant schema helpers that are not native vol types.

    Inspired by voluptuous-serialize.
    """

    if isinstance(schema, vol.Coerce):
        schema = schema.type
    if schema is int:
        return {"type": "integer"}
    if schema in (
        str,
        cv.string,
        cv.template,
        cv.dynamic_template,
        cv.date,
        cv.datetime,
        cv.time,
        cv.slug,
        cv.slugify,
    ):
        return {"type": "string"}
    if schema is float:
        return {"type": "number"}
    if schema in (bool, cv.boolean):
        return {"type": "boolean"}
    if schema in (dict, cv.match_all):
        return {"type": "object"}

    if schema is cv.entity_id:
        return {"type": "string"}
    if schema is cv.entity_ids:
        return {"type": "array", "items": {"type": "string"}}

    if isinstance(schema, list) and len(schema) == 1:
        if item_schema := vol_to_jsonschema(name, schema[0]):
            return {"type": "array", "items": item_schema}

    # For both All and Any, just pick the first variant that we can make a schema for
    if isinstance(schema, (vol.All, vol.Any)):
        for val in schema.validators:
            if val is not None:
                if val_schema := vol_to_jsonschema(name, val):
                    return val_schema
        if all(isinstance(val, str) for val in schema.validators):
            return {"type": "string"}
        return None

    # Convert enums using In to oneOf+const
    if isinstance(schema, vol.In):
        if isinstance(schema.container, Mapping) and all(
            isinstance(k, str) and (isinstance(v, (float, int)))
            for k, v in schema.container.items()
        ):
            return {
                "oneOf": [
                    {"title": k, "const": v} for k, v in schema.container.items()
                ],
            }
        if isinstance(schema.container, list) and all(
            isinstance(val, str) for val in schema.container
        ):
            return {"type": "string"}

    if isinstance(schema, vol.Schema) and isinstance(schema.schema, Mapping):
        properties = {}
        additional_properties = None
        missing_keys = []
        for key, val in schema.schema.items():
            if isinstance(key, vol.Marker):
                key = key.schema
            if key is cv.string:
                key = _ADDITIONAL_PROPERTIES_MARKER
            if not isinstance(key, str) and key != _ADDITIONAL_PROPERTIES_MARKER:
                missing_keys.append("(not a string)")
                _LOGGER.debug(
                    "Failed to convert %s > %s to JSON Schema (non-string key)",
                    name,
                    key,
                )
                continue
            if val_schema := vol_to_jsonschema(f"{name} > {key}", val):
                if key is _ADDITIONAL_PROPERTIES_MARKER:
                    if additional_properties is not None:
                        _LOGGER.debug(
                            "More than one additionalProperties schema for %s",
                            name,
                        )
                    additional_properties = val_schema
                else:
                    properties[key] = val_schema
            else:
                missing_keys.append(key)
                _LOGGER.debug(
                    "Failed to convert %s > %s to JSON Schema: %s", name, key, val
                )

        result = {"type": "object", "properties": properties}
        if additional_properties:
            result["additionalProperties"] = additional_properties
        if missing_keys:
            result["$comment"] = (
                f"Unable to determine schema for the following keys: {', '.join(missing_keys)}"
            )
        return result

    return None
