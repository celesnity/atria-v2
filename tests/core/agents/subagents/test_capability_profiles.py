from minder.core.agents.subagents.agents.module_worker import MODULE_WORKER_SUBAGENT


def test_module_worker_has_profile():
    assert MODULE_WORKER_SUBAGENT.get("capability_profile")
    assert "module" in MODULE_WORKER_SUBAGENT["capability_profile"].lower()
