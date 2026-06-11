"""JSON parameter schemas for deep_research tools."""

PARAMS_DEEP_RESEARCH = {
    "type": "object",
    "properties": {
        "topic": {
            "type": "string",
            "description": (
                "The research topic or question. Be specific enough to guide "
                "taxonomy generation."
            ),
        },
        "depth": {
            "type": "string",
            "enum": ["fast", "standard", "deep"],
            "description": (
                "Research depth. 'fast' = quick overview, 'standard' = balanced "
                "(default), 'deep' = exhaustive."
            ),
            "default": "standard",
        },
    },
    "required": ["topic"],
}

PARAMS_GET_RESEARCH_STATUS = {
    "type": "object",
    "properties": {
        "job_id": {
            "type": "string",
            "description": "The job ID returned by deep_research.",
        },
    },
    "required": ["job_id"],
}
