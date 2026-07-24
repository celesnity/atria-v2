"""Provider-specific schema adaptation.

Different LLM providers have different JSON Schema requirements. This module
applies provider-specific transformations to tool schemas before they are
sent to the LLM.
"""

from __future__ import annotations

import copy
import logging
from typing import Any

logger = logging.getLogger(__name__)


def adapt_for_provider(
    schemas: list[dict[str, Any]],
    provider: str,
) -> list[dict[str, Any]]:
    """Apply provider-specific schema transformations.

    This is a pure function — does not mutate the input schemas.

    Args:
        schemas: List of tool schema dicts (OpenAI function calling format).
        provider: Provider identifier (e.g., "gemini", "xai", "mistral", "openai", "anthropic").

    Returns:
        Transformed list of schemas. Returns a deep copy if any changes were made.
    """
    provider = provider.lower().strip()

    # No adaptation needed for standard providers
    if provider in ("openai", "anthropic", "openrouter"):
        return schemas

    # Deep copy to avoid mutating originals
    adapted = copy.deepcopy(schemas)
    modified = False

    if provider in ("gemini", "google"):
        adapted, changed = _adapt_gemini(adapted)
        modified = modified or changed
    elif provider in ("xai", "grok"):
        adapted, changed = _adapt_xai(adapted)
        modified = modified or changed
    elif provider == "mistral":
        adapted, changed = _adapt_mistral(adapted)
        modified = modified or changed

    # General cleanup for all non-standard providers
    adapted, changed = _general_cleanup(adapted)
    modified = modified or changed

    if modified:
        logger.debug("Adapted %d schemas for provider '%s'", len(adapted), provider)

    return adapted


def _adapt_gemini(schemas: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """Gemini rejects additionalProperties, default, $schema, format in nested schemas."""
    changed = False
    for schema in schemas:
        params = schema.get("function", {}).get("parameters", {})
        if _strip_keys_recursive(params, {"additionalProperties", "default", "$schema", "format"}):
            changed = True
    return schemas, changed


def _adapt_xai(schemas: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """xAI/Grok currently needs no schema adaptation."""
    return schemas, False


def _adapt_mistral(schemas: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """Mistral doesn't support anyOf/oneOf/allOf — flatten to simple types."""
    changed = False
    for schema in schemas:
        params = schema.get("function", {}).get("parameters", {})
        if _flatten_union_types(params):
            changed = True
    return schemas, changed


def _general_cleanup(schemas: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """Ensure schemas follow basic requirements for all providers."""
    changed = False
    for schema in schemas:
        func = schema.get("function", {})
        params = func.get("parameters", {})

        # Ensure top-level has type: "object"
        if params and "type" not in params:
            params["type"] = "object"
            changed = True

        # Ensure properties exists
        if params and "properties" not in params:
            params["properties"] = {}
            changed = True

        if _normalize_bool_subschemas(params):
            changed = True

    return schemas, changed


def _normalize_bool_subschemas(obj: Any) -> bool:
    """Replace bare-boolean JSON Schema subschemas with their object-schema
    equivalents (`true` -> `{}`, `false` -> `{"not": {}}`).

    JSON Schema 2020-12 allows `true`/`false` wherever a subschema is expected
    (e.g. a free-form property declared as `"input": true`, meaning "any
    value"). Some providers' schema converters (e.g. litellm's Gemini/Vertex
    path) assume every subschema is a dict and raise `AttributeError` on the
    bare-boolean form, so normalize it before sending. Lossless: both forms
    describe the same constraint.

    Returns True if any changes were made.
    """
    if not isinstance(obj, dict):
        return False

    changed = False

    properties = obj.get("properties")
    if isinstance(properties, dict):
        for name, value in list(properties.items()):
            if isinstance(value, bool):
                properties[name] = {} if value else {"not": {}}
                changed = True
            elif isinstance(value, dict) and _normalize_bool_subschemas(value):
                changed = True

    items = obj.get("items")
    if isinstance(items, bool):
        obj["items"] = {} if items else {"not": {}}
        changed = True
    elif isinstance(items, dict) and _normalize_bool_subschemas(items):
        changed = True
    elif isinstance(items, list):
        for i, item in enumerate(items):
            if isinstance(item, bool):
                items[i] = {} if item else {"not": {}}
                changed = True
            elif isinstance(item, dict) and _normalize_bool_subschemas(item):
                changed = True

    for key in ("anyOf", "oneOf", "allOf"):
        variants = obj.get(key)
        if not isinstance(variants, list):
            continue
        for i, variant in enumerate(variants):
            if isinstance(variant, bool):
                variants[i] = {} if variant else {"not": {}}
                changed = True
            elif isinstance(variant, dict) and _normalize_bool_subschemas(variant):
                changed = True

    return changed


def _strip_keys_recursive(obj: Any, keys_to_strip: set[str]) -> bool:
    """Recursively remove specified keys from a dict structure.

    Returns True if any keys were actually removed.
    """
    if not isinstance(obj, dict):
        return False

    changed = False
    for key in list(obj.keys()):
        if key in keys_to_strip:
            del obj[key]
            changed = True
        elif isinstance(obj[key], dict):
            if _strip_keys_recursive(obj[key], keys_to_strip):
                changed = True
        elif isinstance(obj[key], list):
            for item in obj[key]:
                if _strip_keys_recursive(item, keys_to_strip):
                    changed = True

    return changed


def _flatten_union_types(obj: Any) -> bool:
    """Replace anyOf/oneOf/allOf with the first variant (lossy but compatible).

    Returns True if any changes were made.
    """
    if not isinstance(obj, dict):
        return False

    changed = False
    for key in list(obj.keys()):
        if key in ("anyOf", "oneOf"):
            variants = obj[key]
            if isinstance(variants, list) and variants:
                # Replace with the first variant
                first = variants[0]
                del obj[key]
                if isinstance(first, dict):
                    obj.update(first)
                changed = True
        elif key == "allOf":
            variants = obj[key]
            if isinstance(variants, list):
                # Merge all variants
                del obj[key]
                for variant in variants:
                    if isinstance(variant, dict):
                        obj.update(variant)
                changed = True
        elif isinstance(obj[key], dict):
            if _flatten_union_types(obj[key]):
                changed = True
        elif isinstance(obj[key], list):
            for item in obj[key]:
                if _flatten_union_types(item):
                    changed = True

    return changed
