import importlib.util, sys
from pathlib import Path
_MOD = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"
def _load(n, s):
    spec = importlib.util.spec_from_file_location(s, _MOD / f"{n}.py")
    m = importlib.util.module_from_spec(spec); sys.modules[s] = m; spec.loader.exec_module(m); return m


def test_prompts_present():
    p = _load("prompts", "dc_prompts")
    for name in ("PLANNER_PROMPT", "CLASSIFIER_PROMPT", "CRITIC_PROMPT", "SEMANTIC_FIX", "PROGRAMMER_PROMPT"):
        assert isinstance(getattr(p, name), str) and getattr(p, name).strip()
    assert "{feedback}" in p.CLASSIFIER_PROMPT
    assert "{code}" in p.CRITIC_PROMPT
