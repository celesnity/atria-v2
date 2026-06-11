"""JSON parameter schemas for deep_analyze tools."""

PARAMS_DEEP_ANALYZE = {
    "type": "object",
    "properties": {
        "file_path": {
            "type": "string",
            "description": "Absolute path to a .csv or .xlsx file.",
        }
    },
    "required": ["file_path"],
}

PARAMS_GET_ANALYZE_STATUS = {
    "type": "object",
    "properties": {
        "job_id": {"type": "string", "description": "Job ID from deep_analyze."}
    },
    "required": ["job_id"],
}

PARAMS_CANCEL_ANALYZE = {
    "type": "object",
    "properties": {
        "job_id": {"type": "string", "description": "Job ID from deep_analyze."}
    },
    "required": ["job_id"],
}
