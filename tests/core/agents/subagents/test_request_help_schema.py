from atria.core.agents.subagents.task_tool import (
    REQUEST_HELP_TOOL_NAME,
    create_request_help_schema,
)


class FakeCfg:
    def __init__(self, name, desc, profile):
        self.name = name
        self.description = desc
        self.capability_profile = profile


class FakeMgr:
    def get_agent_configs(self):
        return [
            FakeCfg("Planner", "maps code", "explores code"),
            FakeCfg("ask-user", "asks the user", None),
        ]


def test_schema_has_no_subagent_type():
    schema = create_request_help_schema(FakeMgr())
    assert schema["function"]["name"] == REQUEST_HELP_TOOL_NAME == "request_help"
    props = schema["function"]["parameters"]["properties"]
    assert set(props) == {"prompt", "max_helpers"}
    # No caller-chosen routing anywhere in the schema.
    assert "subagent_type" not in str(schema)
