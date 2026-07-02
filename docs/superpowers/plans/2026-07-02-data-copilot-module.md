# Data Copilot Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a self-contained `modules/data_copilot/` module that answers a natural-language question about a tabular dataset by generating Python, running it in a bounded sandbox, self-repairing, semantically verifying, and emitting a grounded Markdown report.

**Architecture:** Standalone Python scripts invoked via bash (no in-process atria imports), following the exact conventions of `modules/maintenance_copilot`. A module-local `config.py`/`client.py` pair provides OpenAI-compatible LLM access by *role*; focused scripts implement each loop stage; `copilot.py` is an argparse orchestrator with an append-only audit trail.

**Tech Stack:** Python 3.10+, `pandas`, `openpyxl`, `matplotlib`, `openai`, `pytest`. The loop is a clean reimplementation of `.reference/data-agent/langgraph_agent/`.

## Global Constraints

- Module folder name: `data_copilot` (matches `[a-z0-9_-]+`; store.py enforces this).
- Scripts are standalone; each begins with `sys.path.insert(0, str(Path(__file__).resolve().parent))` so sibling scripts import by bare name (matches maintenance_copilot).
- LLM config is self-contained via `DC_<ROLE>_<FIELD>` env vars; roles are exactly `codegen`, `verify`, `report`. Default endpoint is OpenAI-compatible `https://api.openai.com/v1`, default model `gpt-4o-mini`, api_key falling back to `OPENAI_API_KEY`. Do NOT touch atria's global provider system.
- Generated code runs ONLY as a bounded local subprocess (timeout + output cap + scoped cwd). No Docker, no Jupyter kernel.
- The loop never presents an unverified answer as settled: on exhausted repair/verify budgets the report is labelled unverified.
- All `copilot.py` subcommands print JSON (or a report path) to stdout and return `0` on success.
- Line length 100; type hints on public functions; Google-style docstrings (repo CLAUDE.md).
- Dependencies limited to `pandas`, `openpyxl`, `matplotlib`, `openai` — no `torch`/`gradio`/`transformers`/`sentence_transformers`/`scikit-learn`.
- Tests load module scripts by path with `importlib` (see the `_load` helper repeated in each test file); test files live at `tests/test_data_copilot_<unit>.py`.

---

### Task 1: Module scaffold + `config.py`

**Files:**
- Create: `modules/data_copilot/SKILL.md` (minimal; finalized in Task 11)
- Create: `modules/data_copilot/requirements.txt`
- Create: `modules/data_copilot/.gitignore`
- Create: `modules/data_copilot/scripts/config.py`
- Create: `modules/data_copilot/sample_data/demo.csv`
- Test: `tests/test_data_copilot_config.py`

**Interfaces:**
- Produces: `ROLES: tuple[str,...]`; `RoleConfig(provider, model, base_url, api_key)` (frozen dataclass); `load_config(env: Mapping[str,str] | None = None) -> dict[str, RoleConfig]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_copilot_config.py
"""Tests for data_copilot module-local model config."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"


def _load(name: str, sentinel: str):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


def test_defaults_use_openai_and_env_key():
    config = _load("config", "dc_config_defaults")
    cfg = config.load_config({"OPENAI_API_KEY": "sk-test"})
    assert set(cfg) == set(config.ROLES) == {"codegen", "verify", "report"}
    assert cfg["codegen"].base_url == "https://api.openai.com/v1"
    assert cfg["codegen"].model == "gpt-4o-mini"
    assert cfg["codegen"].api_key == "sk-test"


def test_env_overrides_take_precedence():
    config = _load("config", "dc_config_override")
    cfg = config.load_config({
        "OPENAI_API_KEY": "sk-test",
        "DC_CODEGEN_BASE_URL": "http://localhost:8000/v1",
        "DC_CODEGEN_MODEL": "qwen2.5-coder",
        "DC_CODEGEN_API_KEY": "sk-local",
    })
    assert cfg["codegen"].base_url == "http://localhost:8000/v1"
    assert cfg["codegen"].model == "qwen2.5-coder"
    assert cfg["codegen"].api_key == "sk-local"
    # verify role untouched, still falls back to OPENAI_API_KEY
    assert cfg["verify"].api_key == "sk-test"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_config.py -v`
Expected: FAIL — `FileNotFoundError`/import error (config.py does not exist).

- [ ] **Step 3: Create scaffold files**

`modules/data_copilot/requirements.txt`:
```text
pandas>=2.2.0
openpyxl>=3.1.0
matplotlib>=3.8.0
openai>=1.0.0
```

`modules/data_copilot/.gitignore`:
```text
__pycache__/
runs/
audit_log.jsonl
```

`modules/data_copilot/SKILL.md` (minimal for now; finalized in Task 11):
```markdown
---
name: data_copilot
description: Data-analysis copilot — answers a natural-language question about a tabular dataset by generating Python, running it in a bounded sandbox, self-repairing, semantically verifying, and returning a grounded report.
---

# data_copilot

Data-analysis copilot. See Task 11 for the full SKILL body.
```

`modules/data_copilot/sample_data/demo.csv`:
```text
region,product,units,revenue,date
North,Widget,120,2400,2026-01-05
North,Gadget,80,3200,2026-01-06
South,Widget,60,1200,2026-01-07
South,Gadget,140,5600,2026-01-08
East,Widget,90,1800,2026-01-09
East,Gadget,110,4400,2026-01-10
West,Widget,200,4000,2026-01-11
West,Gadget,50,2000,2026-01-12
```

- [ ] **Step 4: Write `config.py`**

```python
# modules/data_copilot/scripts/config.py
"""Module-local model-provider config for the data_copilot module.

Maps three feature *roles* to OpenAI-compatible endpoints. Every field is read
from ``DC_<ROLE>_<FIELD>`` environment variables with OpenAI defaults, and the
api_key falls back to ``OPENAI_API_KEY`` when a role-specific key is unset. This
layer is deliberately self-contained: it does not touch Atria's global provider
system.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Mapping, Optional

ROLES = ("codegen", "verify", "report")


@dataclass(frozen=True)
class RoleConfig:
    """Endpoint + model for one feature role."""

    provider: str
    model: str
    base_url: str
    api_key: str


# OpenAI-compatible defaults. Code generation needs a capable model; every field
# is overridable per role via env (e.g. point DC_CODEGEN_BASE_URL at local vLLM).
_DEFAULTS: Dict[str, RoleConfig] = {
    "codegen": RoleConfig("openai", "gpt-4o-mini", "https://api.openai.com/v1", ""),
    "verify": RoleConfig("openai", "gpt-4o-mini", "https://api.openai.com/v1", ""),
    "report": RoleConfig("openai", "gpt-4o-mini", "https://api.openai.com/v1", ""),
}


def load_config(env: Optional[Mapping[str, str]] = None) -> Dict[str, RoleConfig]:
    """Return the resolved config for all roles, applying env overrides.

    For each role, ``DC_<ROLE>_PROVIDER|MODEL|BASE_URL|API_KEY`` (role upper-
    cased) overrides the corresponding default field. A role's api_key defaults
    to ``OPENAI_API_KEY`` when neither an override nor a default is set.

    Args:
        env: Optional environment mapping (defaults to ``os.environ``).

    Returns:
        Mapping of role name to its resolved :class:`RoleConfig`.
    """
    src = os.environ if env is None else env
    fallback_key = src.get("OPENAI_API_KEY", "")
    resolved: Dict[str, RoleConfig] = {}
    for role in ROLES:
        d = _DEFAULTS[role]
        prefix = f"DC_{role.upper()}_"
        resolved[role] = RoleConfig(
            provider=src.get(f"{prefix}PROVIDER", d.provider),
            model=src.get(f"{prefix}MODEL", d.model),
            base_url=src.get(f"{prefix}BASE_URL", d.base_url),
            api_key=src.get(f"{prefix}API_KEY", d.api_key or fallback_key),
        )
    return resolved
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_data_copilot_config.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add modules/data_copilot/ tests/test_data_copilot_config.py
git commit -m "feat(data_copilot): module scaffold + role config"
```

---

### Task 2: `client.py` — role-dispatched chat client

**Files:**
- Create: `modules/data_copilot/scripts/client.py`
- Test: `tests/test_data_copilot_client.py`

**Interfaces:**
- Consumes: `config.RoleConfig` from Task 1.
- Produces: `RoleClient(config: dict[str, RoleConfig], client_factory=None)` with `chat(role: str, messages: list[dict], **kw) -> str`. `client_factory: Callable[[str, str], object]` (base_url, api_key) → object exposing `.chat.completions.create(...)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_copilot_client.py
"""Tests for the data_copilot role-dispatched chat client."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_MOD = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"


def _load(name: str, sentinel: str):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


class _FakeResp:
    def __init__(self, text):
        self.choices = [type("C", (), {"message": type("M", (), {"content": text})()})()]


class _FakeCompletions:
    def __init__(self, text):
        self._text = text
        self.calls = []

    def create(self, model, messages, **kw):
        self.calls.append((model, messages, kw))
        return _FakeResp(self._text)


class _FakeClient:
    def __init__(self, base_url, api_key):
        self.base_url = base_url
        self.api_key = api_key
        self.chat = type("Chat", (), {"completions": _FakeCompletions("hello")})()


def test_chat_dispatches_to_role_endpoint():
    config = _load("config", "dc_config_for_client")
    client = _load("client", "dc_client_uut")
    cfg = config.load_config({"OPENAI_API_KEY": "sk-test"})
    made = {}

    def factory(base_url, api_key):
        made["args"] = (base_url, api_key)
        return _FakeClient(base_url, api_key)

    rc = client.RoleClient(cfg, client_factory=factory)
    out = rc.chat("codegen", [{"role": "user", "content": "hi"}], temperature=0)
    assert out == "hello"
    assert made["args"] == ("https://api.openai.com/v1", "sk-test")


def test_unknown_role_raises():
    config = _load("config", "dc_config_for_client2")
    client = _load("client", "dc_client_uut2")
    rc = client.RoleClient(config.load_config({"OPENAI_API_KEY": "k"}),
                           client_factory=lambda b, a: _FakeClient(b, a))
    with pytest.raises(ValueError):
        rc.chat("nope", [{"role": "user", "content": "x"}])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_client.py -v`
Expected: FAIL — client.py does not exist.

- [ ] **Step 3: Write `client.py`**

```python
# modules/data_copilot/scripts/client.py
"""Thin OpenAI-compatible client that dispatches chat calls by feature role.

One underlying ``openai.OpenAI`` is created per distinct ``(base_url, api_key)``
so roles that share an endpoint reuse the same client.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from typing import Callable, Dict, List, Optional, Tuple

try:  # Import lazily so tests can inject a fake factory without openai.
    from openai import OpenAI as _OpenAI
except ImportError:  # pragma: no cover - openai installed in real env
    _OpenAI = None  # type: ignore[assignment]

from config import RoleConfig  # type: ignore[import-not-found]

ClientFactory = Callable[[str, str], object]


def _default_factory(base_url: str, api_key: str) -> object:
    if _OpenAI is None:  # pragma: no cover
        raise RuntimeError("openai package is not installed")
    return _OpenAI(base_url=base_url, api_key=api_key)


class RoleClient:
    """Resolve chat calls to the endpoint configured for a role."""

    def __init__(
        self,
        config: Dict[str, RoleConfig],
        client_factory: Optional[ClientFactory] = None,
    ) -> None:
        self._config = config
        self._factory = client_factory or _default_factory
        self._clients: Dict[Tuple[str, str], object] = {}

    def _role(self, role: str) -> RoleConfig:
        if role not in self._config:
            raise ValueError(f"unknown role: {role!r}")
        return self._config[role]

    def _client_for(self, rc: RoleConfig) -> object:
        key = (rc.base_url, rc.api_key)
        if key not in self._clients:
            self._clients[key] = self._factory(rc.base_url, rc.api_key)
        return self._clients[key]

    def chat(self, role: str, messages: List[dict], **kw) -> str:
        """Send a chat-completion request using the endpoint for *role*.

        Args:
            role: Feature role key (``"codegen"``, ``"verify"``, ``"report"``).
            messages: OpenAI-format message list.
            **kw: Extra kwargs forwarded to ``completions.create``.

        Returns:
            The text content of the first choice's message.
        """
        rc = self._role(role)
        client = self._client_for(rc)
        resp = client.chat.completions.create(  # type: ignore[attr-defined]
            model=rc.model, messages=messages, **kw
        )
        return resp.choices[0].message.content
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_data_copilot_client.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add modules/data_copilot/scripts/client.py tests/test_data_copilot_client.py
git commit -m "feat(data_copilot): role-dispatched chat client"
```

---

### Task 3: `profile.py` — dataset loading + profiling

**Files:**
- Create: `modules/data_copilot/scripts/profile.py`
- Test: `tests/test_data_copilot_profile.py`

**Interfaces:**
- Produces: `load_dataset(path: str) -> pandas.DataFrame`; `profile_dataframe(df, sample_rows: int = 5) -> dict`; `profile_dataset(path: str, sample_rows: int = 5) -> dict`. Profile dict keys: `path`, `n_rows`, `n_cols`, `columns` (list of `{name, dtype, non_null, n_unique}`), `sample` (list of row dicts), `numeric_summary` (dict of describe()).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_copilot_profile.py
"""Tests for dataset loading + profiling."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_MOD = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"


def _load(name: str, sentinel: str):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


def _demo_csv() -> str:
    return str(_MOD.parent / "sample_data" / "demo.csv")


def test_profile_csv_shape_and_columns():
    profile = _load("profile", "dc_profile_csv")
    prof = profile.profile_dataset(_demo_csv())
    assert prof["n_rows"] == 8
    assert prof["n_cols"] == 5
    names = [c["name"] for c in prof["columns"]]
    assert names == ["region", "product", "units", "revenue", "date"]
    assert len(prof["sample"]) == 5
    # numeric columns appear in the numeric summary
    assert "revenue" in prof["numeric_summary"]


def test_load_dataset_unsupported_extension_raises(tmp_path):
    profile = _load("profile", "dc_profile_bad")
    bad = tmp_path / "data.txt"
    bad.write_text("not a table")
    with pytest.raises(ValueError):
        profile.load_dataset(str(bad))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_profile.py -v`
Expected: FAIL — profile.py does not exist.

- [ ] **Step 3: Write `profile.py`**

```python
# modules/data_copilot/scripts/profile.py
"""Load a tabular dataset and produce a compact, grounding-friendly profile.

The profile (schema + stats + sample rows) is the context handed to code
generation so the model never guesses column names.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pandas as pd


def load_dataset(path: str) -> pd.DataFrame:
    """Load a CSV / Excel / Parquet file into a DataFrame by extension.

    Args:
        path: Filesystem path to the dataset.

    Returns:
        The loaded :class:`pandas.DataFrame`.

    Raises:
        ValueError: If the extension is unsupported.
        FileNotFoundError: If the path does not exist.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(path)
    ext = p.suffix.lower()
    if ext == ".csv":
        return pd.read_csv(p)
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(p)
    if ext == ".parquet":
        return pd.read_parquet(p)
    raise ValueError(f"unsupported dataset extension: {ext!r}")


def profile_dataframe(df: pd.DataFrame, sample_rows: int = 5) -> Dict[str, Any]:
    """Summarize a DataFrame into a JSON-serializable profile.

    Args:
        df: The DataFrame to profile.
        sample_rows: Number of head rows to include as examples.

    Returns:
        A dict with ``n_rows``, ``n_cols``, ``columns``, ``sample``, and
        ``numeric_summary``.
    """
    columns = [
        {
            "name": str(name),
            "dtype": str(df[name].dtype),
            "non_null": int(df[name].notna().sum()),
            "n_unique": int(df[name].nunique(dropna=True)),
        }
        for name in df.columns
    ]
    numeric = df.select_dtypes(include="number")
    numeric_summary = (
        {} if numeric.empty else {str(k): v for k, v in numeric.describe().to_dict().items()}
    )
    sample = df.head(sample_rows).astype(object).where(pd.notna(df.head(sample_rows)), None)
    return {
        "n_rows": int(len(df)),
        "n_cols": int(df.shape[1]),
        "columns": columns,
        "sample": sample.to_dict(orient="records"),
        "numeric_summary": numeric_summary,
    }


def profile_dataset(path: str, sample_rows: int = 5) -> Dict[str, Any]:
    """Load a dataset and return its profile, tagged with the source path.

    Args:
        path: Filesystem path to the dataset.
        sample_rows: Number of head rows to include as examples.

    Returns:
        The profile dict from :func:`profile_dataframe` plus a ``path`` key.
    """
    df = load_dataset(path)
    prof = profile_dataframe(df, sample_rows=sample_rows)
    prof["path"] = str(path)
    return prof
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_data_copilot_profile.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add modules/data_copilot/scripts/profile.py tests/test_data_copilot_profile.py
git commit -m "feat(data_copilot): dataset loading + profiling"
```

---

### Task 4: `guardrails.py` — static pre-execution gate

**Files:**
- Create: `modules/data_copilot/scripts/guardrails.py`
- Test: `tests/test_data_copilot_guardrails.py`

**Interfaces:**
- Produces: `check_code(code: str) -> dict` returning `{"allowed": bool, "reasons": list[str]}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_copilot_guardrails.py
"""Tests for the static code guardrail gate."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"


def _load(name: str, sentinel: str):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


def test_allows_benign_pandas_code():
    g = _load("guardrails", "dc_guard_ok")
    code = "import pandas as pd\ndf = pd.read_csv('demo.csv')\nprint(df['revenue'].sum())\n"
    verdict = g.check_code(code)
    assert verdict["allowed"] is True
    assert verdict["reasons"] == []


def test_blocks_network_and_subprocess_and_escape():
    g = _load("guardrails", "dc_guard_block")
    for bad in [
        "import requests\nrequests.get('http://x')",
        "import socket",
        "import os\nos.system('rm -rf /')",
        "import subprocess\nsubprocess.run(['ls'])",
        "open('/etc/passwd', 'w')",
        "__import__('os').system('x')",
    ]:
        verdict = g.check_code(bad)
        assert verdict["allowed"] is False, bad
        assert verdict["reasons"], bad
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_guardrails.py -v`
Expected: FAIL — guardrails.py does not exist.

- [ ] **Step 3: Write `guardrails.py`**

```python
# modules/data_copilot/scripts/guardrails.py
"""Static pre-execution guardrails for generated analysis code.

Enforced in code, not left to the prompt: code that reaches out to the network,
spawns processes, escapes the run directory, or does dynamic imports is blocked
before it ever runs. Analysis code only needs to read the dataset, compute over
it in memory, print results, and save figures into the run directory.
"""

from __future__ import annotations

import re
from typing import Dict, List

# (compiled pattern, human-readable reason). Substring/regex matches on source.
_RULES = [
    (re.compile(r"\bimport\s+(socket|requests|urllib|http|ftplib|smtplib)\b"),
     "network access is not allowed"),
    (re.compile(r"\bfrom\s+(socket|requests|urllib|http)\b"),
     "network access is not allowed"),
    (re.compile(r"\bimport\s+(subprocess|multiprocessing)\b"),
     "spawning processes is not allowed"),
    (re.compile(r"\bos\.(system|popen|exec[lv]?[pe]*|spawn\w*)\s*\("),
     "shell/process execution is not allowed"),
    (re.compile(r"\b__import__\s*\("), "dynamic __import__ is not allowed"),
    (re.compile(r"\b(eval|exec)\s*\("), "eval/exec is not allowed"),
    (re.compile(r"\bshutil\.rmtree\s*\("), "recursive delete is not allowed"),
    (re.compile(r"\bos\.remove\s*\(|\bos\.unlink\s*\("), "file deletion is not allowed"),
    # open(...) in a write/append mode targeting an absolute or parent path.
    (re.compile(r"open\s*\(\s*['\"](/|[a-zA-Z]:\\|\.\.)"),
     "writing outside the run directory is not allowed"),
]


def check_code(code: str) -> Dict[str, object]:
    """Statically screen generated code for disallowed operations.

    Args:
        code: The Python source to screen.

    Returns:
        ``{"allowed": bool, "reasons": list[str]}`` — ``allowed`` is ``False``
        when any rule matches; ``reasons`` lists the distinct triggered reasons.
    """
    reasons: List[str] = []
    for pattern, reason in _RULES:
        if pattern.search(code) and reason not in reasons:
            reasons.append(reason)
    return {"allowed": not reasons, "reasons": reasons}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_data_copilot_guardrails.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add modules/data_copilot/scripts/guardrails.py tests/test_data_copilot_guardrails.py
git commit -m "feat(data_copilot): static code guardrail gate"
```

---

### Task 5: `sandbox.py` — bounded subprocess execution

**Files:**
- Create: `modules/data_copilot/scripts/sandbox.py`
- Test: `tests/test_data_copilot_sandbox.py`

**Interfaces:**
- Produces: `run_code(code: str, workdir: str, timeout: float = 30.0, max_output: int = 20000) -> dict` returning `{"status": "text"|"error", "stdout": str, "stderr": str, "figures": list[str], "returncode": int|None}`. Writes code to `<workdir>/_run.py`, executes with cwd=workdir, collects newly-created image files.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_copilot_sandbox.py
"""Tests for the bounded subprocess sandbox."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"


def _load(name: str, sentinel: str):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


def test_runs_and_captures_stdout(tmp_path):
    sandbox = _load("sandbox", "dc_sandbox_ok")
    res = sandbox.run_code("print('answer is', 6*7)", str(tmp_path))
    assert res["status"] == "text"
    assert "answer is 42" in res["stdout"]
    assert res["returncode"] == 0


def test_captures_error(tmp_path):
    sandbox = _load("sandbox", "dc_sandbox_err")
    res = sandbox.run_code("raise ValueError('boom')", str(tmp_path))
    assert res["status"] == "error"
    assert "ValueError" in res["stderr"]


def test_timeout_is_enforced(tmp_path):
    sandbox = _load("sandbox", "dc_sandbox_timeout")
    res = sandbox.run_code("import time\ntime.sleep(5)", str(tmp_path), timeout=0.5)
    assert res["status"] == "error"
    assert "timeout" in res["stderr"].lower()


def test_collects_figures(tmp_path):
    sandbox = _load("sandbox", "dc_sandbox_fig")
    code = (
        "import matplotlib\nmatplotlib.use('Agg')\n"
        "import matplotlib.pyplot as plt\n"
        "plt.plot([1,2,3]); plt.savefig('chart.png')\n"
        "print('done')\n"
    )
    res = sandbox.run_code(code, str(tmp_path))
    assert res["status"] == "text"
    assert any(f.endswith("chart.png") for f in res["figures"])


def test_output_is_capped(tmp_path):
    sandbox = _load("sandbox", "dc_sandbox_cap")
    res = sandbox.run_code("print('x' * 100000)", str(tmp_path), max_output=1000)
    assert len(res["stdout"]) <= 1000 + 64  # cap + truncation notice slack
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_sandbox.py -v`
Expected: FAIL — sandbox.py does not exist.

- [ ] **Step 3: Write `sandbox.py`**

```python
# modules/data_copilot/scripts/sandbox.py
"""Execute generated analysis code as a bounded local subprocess.

Atria already runs inside a sandbox, so this adds process-level bounds rather
than container isolation: a wall-clock timeout, an output-size cap, and a cwd
scoped to a per-run directory into which figures are written.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Dict, List

_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".svg")
_TRUNCATION_NOTICE = "\n...[truncated]..."


def _cap(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + _TRUNCATION_NOTICE


def run_code(
    code: str,
    workdir: str,
    timeout: float = 30.0,
    max_output: int = 20000,
) -> Dict[str, object]:
    """Run *code* in *workdir* as a subprocess with bounds.

    Args:
        code: Python source to execute.
        workdir: Directory used as cwd; created if missing. Figures land here.
        timeout: Wall-clock limit in seconds.
        max_output: Max characters kept from each of stdout/stderr.

    Returns:
        ``{"status", "stdout", "stderr", "figures", "returncode"}`` where
        ``status`` is ``"text"`` on a clean exit (code 0) and ``"error"``
        otherwise. ``figures`` lists image files present after the run.
    """
    wd = Path(workdir)
    wd.mkdir(parents=True, exist_ok=True)
    before = {p.name for p in wd.iterdir() if p.is_file()}
    script = wd / "_run.py"
    script.write_text(code, encoding="utf-8")

    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(wd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        stdout, stderr, rc = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", "replace")
        return {
            "status": "error",
            "stdout": _cap(stdout, max_output),
            "stderr": f"timeout: execution exceeded {timeout}s",
            "figures": [],
            "returncode": None,
        }

    figures: List[str] = [
        str(wd / p.name)
        for p in sorted(wd.iterdir())
        if p.is_file() and p.name not in before and p.suffix.lower() in _IMAGE_EXTS
    ]
    return {
        "status": "text" if rc == 0 else "error",
        "stdout": _cap(stdout, max_output),
        "stderr": _cap(stderr, max_output),
        "figures": figures,
        "returncode": rc,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_data_copilot_sandbox.py -v`
Expected: PASS (5 passed). (The figure test needs matplotlib installed; it is in requirements.txt.)

- [ ] **Step 5: Commit**

```bash
git add modules/data_copilot/scripts/sandbox.py tests/test_data_copilot_sandbox.py
git commit -m "feat(data_copilot): bounded subprocess sandbox"
```

---

### Task 6: `generate.py` — NL + profile → code

**Files:**
- Create: `modules/data_copilot/scripts/generate.py`
- Test: `tests/test_data_copilot_generate.py`

**Interfaces:**
- Consumes: profile dict from Task 3.
- Produces: `extract_code(text: str) -> tuple[bool, str]`; `build_messages(question: str, profile: dict, prior_error: str | None = None, hypotheses: str | None = None) -> list[dict]`; `generate_code(question: str, profile: dict, chat_fn: Callable[[list[dict]], str], prior_error: str | None = None, hypotheses: str | None = None) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_copilot_generate.py
"""Tests for code generation + extraction."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"


def _load(name: str, sentinel: str):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


def test_extract_code_from_fenced_block():
    gen = _load("generate", "dc_gen_extract")
    ok, code = gen.extract_code("Here:\n```python\nprint(1)\n```\ndone")
    assert ok is True
    assert "print(1)" in code


def test_extract_code_returns_false_when_absent():
    gen = _load("generate", "dc_gen_noextract")
    ok, code = gen.extract_code("no code here")
    assert ok is False
    assert code == ""


def test_generate_code_passes_profile_and_extracts():
    gen = _load("generate", "dc_gen_full")
    captured = {}

    def chat_fn(messages):
        captured["messages"] = messages
        return "```python\ndf['revenue'].sum()\n```"

    profile = {"path": "demo.csv", "n_rows": 8, "n_cols": 5,
               "columns": [{"name": "revenue", "dtype": "int64",
                            "non_null": 8, "n_unique": 8}],
               "sample": [], "numeric_summary": {}}
    code = gen.generate_code("total revenue?", profile, chat_fn)
    assert "revenue" in code
    # the column name is present in the prompt sent to the model (grounding)
    joined = " ".join(m["content"] for m in captured["messages"])
    assert "revenue" in joined and "demo.csv" in joined


def test_prior_error_included_in_repair_prompt():
    gen = _load("generate", "dc_gen_repair")
    captured = {}

    def chat_fn(messages):
        captured["messages"] = messages
        return "```python\npass\n```"

    gen.generate_code("q", {"path": "d", "columns": [], "sample": [],
                            "numeric_summary": {}, "n_rows": 0, "n_cols": 0},
                      chat_fn, prior_error="NameError: x not defined")
    joined = " ".join(m["content"] for m in captured["messages"])
    assert "NameError" in joined
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_generate.py -v`
Expected: FAIL — generate.py does not exist.

- [ ] **Step 3: Write `generate.py`**

```python
# modules/data_copilot/scripts/generate.py
"""Generate Python analysis code from a question + dataset profile.

Adapted from .reference/data-agent's programmer/nodes.generate_code: the dataset
profile is injected so the model uses real column names, and any prior execution
error or verifier hypotheses are appended to drive repair/revision.
"""

from __future__ import annotations

import json
import re
from typing import Callable, List, Optional

_CODE_RE = re.compile(r"```python([^\n]*)(.*?)```", re.DOTALL)

_SYSTEM = (
    "You are a senior data analyst. Write a single self-contained Python script "
    "that answers the user's question about the dataset. Rules: use pandas; load "
    "the dataset from the exact path given; PRINT the answer with clear labels; "
    "if a chart helps, use matplotlib with the 'Agg' backend and savefig into the "
    "current directory. Do NOT access the network, spawn processes, or write "
    "outside the current directory. Return the code in one ```python``` block."
)


def extract_code(text: str) -> tuple[bool, str]:
    """Extract Python from ```python fenced blocks (concatenated if several).

    Args:
        text: The model response.

    Returns:
        ``(found, code)``. ``found`` is ``False`` and ``code`` empty if no block.
    """
    matches = _CODE_RE.findall(text)
    if not matches:
        return False, ""
    if len(matches) > 1:
        return True, "".join(m[1] for m in matches)
    return True, matches[-1][1]


def build_messages(
    question: str,
    profile: dict,
    prior_error: Optional[str] = None,
    hypotheses: Optional[str] = None,
) -> List[dict]:
    """Build the chat messages for code generation.

    Args:
        question: The user's natural-language question.
        profile: Dataset profile from :func:`profile.profile_dataset`.
        prior_error: Traceback/stderr from a failed run, to drive repair.
        hypotheses: Verifier suggestions, to drive semantic revision.

    Returns:
        OpenAI-format message list.
    """
    prof_json = json.dumps(
        {k: profile[k] for k in ("path", "n_rows", "n_cols", "columns", "sample")
         if k in profile},
        default=str,
    )
    user = (
        f"Dataset path: {profile.get('path')}\n"
        f"Dataset profile (JSON):\n{prof_json}\n\n"
        f"Question: {question}\n"
    )
    if prior_error:
        user += (
            "\nThe previous code failed with this error — fix it:\n"
            f"{prior_error}\n"
        )
    if hypotheses:
        user += (
            "\nA verifier judged the previous result insufficient. Address:\n"
            f"{hypotheses}\n"
        )
    return [{"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user}]


def generate_code(
    question: str,
    profile: dict,
    chat_fn: Callable[[List[dict]], str],
    prior_error: Optional[str] = None,
    hypotheses: Optional[str] = None,
) -> str:
    """Generate analysis code, returning the extracted Python (or raw text).

    Args:
        question: The user's question.
        profile: Dataset profile.
        chat_fn: Callable mapping messages -> model text (bound to the codegen role).
        prior_error: Optional error from a prior run.
        hypotheses: Optional verifier hypotheses.

    Returns:
        The extracted Python code; if no fenced block is present, the raw text.
    """
    messages = build_messages(question, profile, prior_error, hypotheses)
    text = chat_fn(messages)
    found, code = extract_code(text)
    return code if found else text
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_data_copilot_generate.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add modules/data_copilot/scripts/generate.py tests/test_data_copilot_generate.py
git commit -m "feat(data_copilot): NL+profile code generation"
```

---

### Task 7: `verify.py` — semantic verdict

**Files:**
- Create: `modules/data_copilot/scripts/verify.py`
- Test: `tests/test_data_copilot_verify.py`

**Interfaces:**
- Produces: `parse_verdict(text: str) -> dict` returning `{"status": "OK"|"REVISE", "hypotheses": str}`; `build_messages(question, code, output) -> list[dict]`; `verify(question: str, code: str, output: str, chat_fn: Callable[[list[dict]], str]) -> dict`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_copilot_verify.py
"""Tests for semantic verification parsing + flow."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"


def _load(name: str, sentinel: str):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


def test_parse_ok():
    v = _load("verify", "dc_verify_ok")
    assert v.parse_verdict("STATUS: OK\nThe output answers the question.")["status"] == "OK"


def test_parse_revise_captures_hypotheses():
    v = _load("verify", "dc_verify_rev")
    out = v.parse_verdict("STATUS: REVISE\nHYPOTHESES: group by region first")
    assert out["status"] == "REVISE"
    assert "group by region" in out["hypotheses"]


def test_parse_defaults_to_revise_when_unclear():
    v = _load("verify", "dc_verify_default")
    assert v.parse_verdict("hmm not sure")["status"] == "REVISE"


def test_verify_calls_model_and_returns_verdict():
    v = _load("verify", "dc_verify_flow")
    out = v.verify("q", "code", "output", lambda m: "STATUS: OK")
    assert out["status"] == "OK"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_verify.py -v`
Expected: FAIL — verify.py does not exist.

- [ ] **Step 3: Write `verify.py`**

```python
# modules/data_copilot/scripts/verify.py
"""Semantic verification of an analysis result against the question.

Adapted from .reference/data-agent's SemanticVerifier/nodes.semantic_verify.
This is NOT a syntax check (execution errors are handled by the repair path);
it judges whether the produced output actually answers the question.
"""

from __future__ import annotations

import re
from typing import Callable, Dict, List

_SYSTEM = (
    "You are a strict verifier. Given a question, the Python code that ran, and "
    "its printed output, decide whether the output actually and correctly answers "
    "the question. Reply on the first line with exactly 'STATUS: OK' or "
    "'STATUS: REVISE'. If REVISE, add a line 'HYPOTHESES: <concrete fixes>'. "
    "Default to REVISE when uncertain."
)
_STATUS_RE = re.compile(r"STATUS:\s*(OK|REVISE)", re.IGNORECASE)
_HYP_RE = re.compile(r"HYPOTHESES:\s*(.+)", re.IGNORECASE | re.DOTALL)


def parse_verdict(text: str) -> Dict[str, str]:
    """Parse the verifier reply into a structured verdict.

    Args:
        text: The verifier model's reply.

    Returns:
        ``{"status": "OK"|"REVISE", "hypotheses": str}``. Unclear replies
        default to ``REVISE`` (fail-safe).
    """
    m = _STATUS_RE.search(text)
    status = m.group(1).upper() if m else "REVISE"
    hyp_match = _HYP_RE.search(text)
    hypotheses = hyp_match.group(1).strip() if hyp_match else ""
    return {"status": status, "hypotheses": hypotheses}


def build_messages(question: str, code: str, output: str) -> List[dict]:
    """Build the verifier chat messages.

    Args:
        question: The user's question.
        code: The code that produced the output.
        output: The captured stdout.

    Returns:
        OpenAI-format message list.
    """
    user = (
        f"Question: {question}\n\n"
        f"Code:\n```python\n{code}\n```\n\n"
        f"Output:\n{output}\n"
    )
    return [{"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user}]


def verify(
    question: str,
    code: str,
    output: str,
    chat_fn: Callable[[List[dict]], str],
) -> Dict[str, str]:
    """Ask the verifier model whether *output* answers *question*.

    Args:
        question: The user's question.
        code: The code that produced the output.
        output: The captured stdout.
        chat_fn: Callable mapping messages -> model text (bound to the verify role).

    Returns:
        The parsed verdict from :func:`parse_verdict`.
    """
    return parse_verdict(chat_fn(build_messages(question, code, output)))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_data_copilot_verify.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add modules/data_copilot/scripts/verify.py tests/test_data_copilot_verify.py
git commit -m "feat(data_copilot): semantic verification"
```

---

### Task 8: `report.py` — grounded Markdown report

**Files:**
- Create: `modules/data_copilot/scripts/report.py`
- Test: `tests/test_data_copilot_report.py`

**Interfaces:**
- Produces: `build_messages(question, output, figures) -> list[dict]`; `generate_report(question: str, output: str, figures: list[str], chat_fn: Callable[[list[dict]], str], verified: bool = True) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_copilot_report.py
"""Tests for grounded report generation."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"


def _load(name: str, sentinel: str):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


def test_report_includes_output_and_figures_in_prompt():
    report = _load("report", "dc_report_prompt")
    captured = {}

    def chat_fn(messages):
        captured["messages"] = messages
        return "# Report\nTotal revenue is 24600."

    md = report.generate_report("total revenue?", "revenue sum: 24600",
                                 ["/runs/chart.png"], chat_fn)
    assert "Report" in md
    joined = " ".join(m["content"] for m in captured["messages"])
    assert "24600" in joined and "chart.png" in joined


def test_unverified_prepends_warning():
    report = _load("report", "dc_report_unverified")
    md = report.generate_report("q", "partial output", [], lambda m: "body",
                                verified=False)
    assert "UNVERIFIED" in md.upper()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_report.py -v`
Expected: FAIL — report.py does not exist.

- [ ] **Step 3: Write `report.py`**

```python
# modules/data_copilot/scripts/report.py
"""Compose a grounded Markdown report from a verified analysis result.

Adapted from .reference/data-agent's report generator: the report is grounded in
the actual printed output and produced figures, and must not introduce claims
absent from that evidence.
"""

from __future__ import annotations

from typing import Callable, List

_SYSTEM = (
    "You are a data analyst writing a concise Markdown report. Ground every "
    "statement in the provided output — do not invent numbers. Reference figures "
    "by their file path. Keep it tight: a short answer, the key evidence, and "
    "any figures. Do not add further suggestions at the end."
)
_UNVERIFIED = (
    "> ⚠️ **UNVERIFIED** — the analysis loop did not confirm this result "
    "(repair/verify budget exhausted). Treat the numbers below as provisional "
    "and review the code and output before relying on them.\n\n"
)


def build_messages(question: str, output: str, figures: List[str]) -> List[dict]:
    """Build the report chat messages.

    Args:
        question: The user's question.
        output: The verified stdout to ground the report in.
        figures: Paths to any produced figures.

    Returns:
        OpenAI-format message list.
    """
    fig_lines = "\n".join(f"- {f}" for f in figures) if figures else "(none)"
    user = (
        f"Question: {question}\n\n"
        f"Computed output:\n{output}\n\n"
        f"Figures:\n{fig_lines}\n"
    )
    return [{"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user}]


def generate_report(
    question: str,
    output: str,
    figures: List[str],
    chat_fn: Callable[[List[dict]], str],
    verified: bool = True,
) -> str:
    """Generate a grounded Markdown report.

    Args:
        question: The user's question.
        output: The stdout to ground the report in.
        figures: Paths to any produced figures.
        chat_fn: Callable mapping messages -> model text (bound to the report role).
        verified: When ``False``, prepend an UNVERIFIED warning banner.

    Returns:
        The Markdown report string.
    """
    body = chat_fn(build_messages(question, output, figures))
    return body if verified else _UNVERIFIED + body
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_data_copilot_report.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add modules/data_copilot/scripts/report.py tests/test_data_copilot_report.py
git commit -m "feat(data_copilot): grounded report generation"
```

---

### Task 9: `audit.py` — append-only JSONL trail

**Files:**
- Create: `modules/data_copilot/scripts/audit.py`
- Test: `tests/test_data_copilot_audit.py`

**Interfaces:**
- Produces: `audit_path() -> pathlib.Path`; `append_event(event: dict) -> None`; `read_events() -> list[dict]`. Path is `DC_AUDIT_PATH` env, else `<module_dir>/audit_log.jsonl`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_copilot_audit.py
"""Tests for the append-only audit trail."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"


def _load(name: str, sentinel: str):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


def test_append_and_read_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("DC_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    audit = _load("audit", "dc_audit_rt")
    audit.append_event({"type": "analyze", "question": "q1"})
    audit.append_event({"type": "analyze", "question": "q2"})
    events = audit.read_events()
    assert [e["question"] for e in events] == ["q1", "q2"]


def test_read_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("DC_AUDIT_PATH", str(tmp_path / "none.jsonl"))
    audit = _load("audit", "dc_audit_missing")
    assert audit.read_events() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_audit.py -v`
Expected: FAIL — audit.py does not exist.

- [ ] **Step 3: Write `audit.py`**

```python
# modules/data_copilot/scripts/audit.py
"""Append-only JSONL audit trail for data_copilot analyses.

Each analysis appends one line so every run is traceable: question, dataset,
verification outcome, and retry counts. Location is ``DC_AUDIT_PATH`` if set,
else ``<module_dir>/audit_log.jsonl``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List


def audit_path() -> Path:
    """Return the audit log path (``DC_AUDIT_PATH`` or module-local default)."""
    override = os.environ.get("DC_AUDIT_PATH")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "audit_log.jsonl"


def append_event(event: Dict[str, object]) -> None:
    """Append one JSON event as a line to the audit log.

    Args:
        event: JSON-serializable event payload.
    """
    path = audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, default=str) + "\n")


def read_events() -> List[Dict[str, object]]:
    """Read all audit events, oldest first. Empty list if the file is absent.

    Returns:
        The parsed events; malformed lines are skipped.
    """
    path = audit_path()
    if not path.is_file():
        return []
    out: List[Dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_data_copilot_audit.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add modules/data_copilot/scripts/audit.py tests/test_data_copilot_audit.py
git commit -m "feat(data_copilot): append-only audit trail"
```

---

### Task 10: `copilot.py` — orchestrator CLI + analysis loop

**Files:**
- Create: `modules/data_copilot/scripts/copilot.py`
- Test: `tests/test_data_copilot_cli.py`

**Interfaces:**
- Consumes: `config.load_config`, `client.RoleClient`, `profile.profile_dataset`, `generate.generate_code`, `guardrails.check_code`, `sandbox.run_code`, `verify.verify`, `report.generate_report`, `audit.append_event`/`read_events`.
- Produces: `run_analysis(dataset, question, *, out_dir, max_repair, max_verify, codegen_fn, verify_fn, report_fn, profile_fn=..., guard_fn=..., exec_fn=..., timeout=30.0, max_output=20000) -> dict` (keys: `dataset`, `question`, `code`, `status`, `verified`, `verdict`, `figures`, `report`, `repairs`, `verify_rounds`); `build_parser()`; `main(argv=None) -> int`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_copilot_cli.py
"""Tests for the copilot orchestrator loop + CLI (injected fakes, no real LLM)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"


def _load(name: str, sentinel: str):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


def _fakes():
    prof = {"path": "d.csv", "n_rows": 1, "n_cols": 1,
            "columns": [{"name": "x", "dtype": "int64", "non_null": 1, "n_unique": 1}],
            "sample": [], "numeric_summary": {}}
    return prof


def test_happy_path_verifies_first_try(tmp_path, monkeypatch):
    monkeypatch.setenv("DC_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    copilot = _load("copilot", "dc_cli_happy")
    prof = _fakes()
    result = copilot.run_analysis(
        "d.csv", "sum?", out_dir=str(tmp_path / "run"),
        max_repair=3, max_verify=2,
        codegen_fn=lambda q, p, pe=None, hy=None: "print(42)",
        verify_fn=lambda q, c, o: {"status": "OK", "hypotheses": ""},
        report_fn=lambda q, o, f, verified=True: "# Report\n42",
        profile_fn=lambda path: prof,
        guard_fn=lambda code: {"allowed": True, "reasons": []},
        exec_fn=lambda code, wd, timeout, max_output: {
            "status": "text", "stdout": "42", "stderr": "", "figures": [], "returncode": 0},
    )
    assert result["verified"] is True
    assert result["repairs"] == 0
    assert "42" in result["report"]


def test_repairs_execution_error_then_succeeds(tmp_path, monkeypatch):
    monkeypatch.setenv("DC_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    copilot = _load("copilot", "dc_cli_repair")
    prof = _fakes()
    runs = {"n": 0}

    def exec_fn(code, wd, timeout, max_output):
        runs["n"] += 1
        if runs["n"] == 1:
            return {"status": "error", "stdout": "", "stderr": "NameError",
                    "figures": [], "returncode": 1}
        return {"status": "text", "stdout": "ok", "stderr": "", "figures": [],
                "returncode": 0}

    result = copilot.run_analysis(
        "d.csv", "q", out_dir=str(tmp_path / "run"),
        max_repair=3, max_verify=2,
        codegen_fn=lambda q, p, pe=None, hy=None: "code",
        verify_fn=lambda q, c, o: {"status": "OK", "hypotheses": ""},
        report_fn=lambda q, o, f, verified=True: "r",
        profile_fn=lambda path: prof,
        guard_fn=lambda code: {"allowed": True, "reasons": []},
        exec_fn=exec_fn,
    )
    assert result["repairs"] == 1
    assert result["verified"] is True


def test_verify_budget_exhausted_marks_unverified(tmp_path, monkeypatch):
    monkeypatch.setenv("DC_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    copilot = _load("copilot", "dc_cli_unverified")
    prof = _fakes()
    captured = {}

    def report_fn(q, o, f, verified=True):
        captured["verified"] = verified
        return "r"

    result = copilot.run_analysis(
        "d.csv", "q", out_dir=str(tmp_path / "run"),
        max_repair=1, max_verify=1,
        codegen_fn=lambda q, p, pe=None, hy=None: "code",
        verify_fn=lambda q, c, o: {"status": "REVISE", "hypotheses": "try again"},
        report_fn=report_fn,
        profile_fn=lambda path: prof,
        guard_fn=lambda code: {"allowed": True, "reasons": []},
        exec_fn=lambda code, wd, timeout, max_output: {
            "status": "text", "stdout": "x", "stderr": "", "figures": [], "returncode": 0},
    )
    assert result["verified"] is False
    assert captured["verified"] is False


def test_guardrail_block_counts_as_repair(tmp_path, monkeypatch):
    monkeypatch.setenv("DC_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    copilot = _load("copilot", "dc_cli_guard")
    prof = _fakes()
    result = copilot.run_analysis(
        "d.csv", "q", out_dir=str(tmp_path / "run"),
        max_repair=2, max_verify=1,
        codegen_fn=lambda q, p, pe=None, hy=None: "import socket",
        verify_fn=lambda q, c, o: {"status": "OK", "hypotheses": ""},
        report_fn=lambda q, o, f, verified=True: "r",
        profile_fn=lambda path: prof,
        guard_fn=lambda code: {"allowed": False, "reasons": ["network"]},
        exec_fn=lambda code, wd, timeout, max_output: {
            "status": "text", "stdout": "x", "stderr": "", "figures": [], "returncode": 0},
    )
    # every generation is blocked -> exhausts repair budget -> unverified error
    assert result["verified"] is False
    assert result["status"] == "error"


def test_cli_audit_subcommand_prints_events(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DC_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    copilot = _load("copilot", "dc_cli_audit")
    audit = _load("audit", "dc_cli_audit_dep")
    audit.append_event({"type": "analyze", "question": "q1"})
    rc = copilot.main(["audit", "--limit", "10"])
    assert rc == 0
    assert "q1" in capsys.readouterr().out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_cli.py -v`
Expected: FAIL — copilot.py does not exist.

- [ ] **Step 3: Write `copilot.py`**

```python
#!/usr/bin/env python
"""data_copilot CLI.

Subcommands:
  health   — check the configured LLM endpoint(s) are reachable.
  profile  — print a dataset profile as JSON.
  analyze  — run the full generate → execute → repair → verify → report loop.
  audit    — print recent audit-trail events.

The loop is a clean reimplementation of .reference/data-agent/langgraph_agent.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import audit  # type: ignore[import-not-found]
import generate  # type: ignore[import-not-found]
import guardrails  # type: ignore[import-not-found]
import profile as profile_mod  # type: ignore[import-not-found]
import report as report_mod  # type: ignore[import-not-found]
import sandbox  # type: ignore[import-not-found]
import verify as verify_mod  # type: ignore[import-not-found]
from client import RoleClient  # type: ignore[import-not-found]
from config import load_config  # type: ignore[import-not-found]


def _gen_and_run(question, prof, out_dir, codegen_fn, guard_fn, exec_fn,
                 prior_error, hypotheses, timeout, max_output):
    """Generate code, screen it, and (if allowed) execute it once."""
    code = codegen_fn(question, prof, prior_error, hypotheses)
    guard = guard_fn(code)
    if not guard["allowed"]:
        return code, {"status": "error", "stdout": "",
                      "stderr": "GUARDRAIL: " + "; ".join(guard["reasons"]),
                      "figures": [], "returncode": None}
    return code, exec_fn(code, out_dir, timeout, max_output)


def run_analysis(
    dataset: str,
    question: str,
    *,
    out_dir: str,
    max_repair: int,
    max_verify: int,
    codegen_fn: Callable,
    verify_fn: Callable,
    report_fn: Callable,
    profile_fn: Callable = profile_mod.profile_dataset,
    guard_fn: Callable = guardrails.check_code,
    exec_fn: Callable = sandbox.run_code,
    timeout: float = 30.0,
    max_output: int = 20000,
) -> Dict[str, object]:
    """Run the full analysis loop and append an audit event.

    Args:
        dataset: Path to the dataset.
        question: Natural-language question.
        out_dir: Directory for the run (code + figures).
        max_repair: Max execution-error repair attempts.
        max_verify: Max semantic-revision rounds.
        codegen_fn: ``(question, profile, prior_error, hypotheses) -> code``.
        verify_fn: ``(question, code, output) -> {"status","hypotheses"}``.
        report_fn: ``(question, output, figures, verified=) -> markdown``.
        profile_fn, guard_fn, exec_fn: injectable dependencies (defaults wired
            to the module functions).
        timeout, max_output: sandbox bounds.

    Returns:
        A summary dict (see Interfaces block in the plan).
    """
    prof = profile_fn(dataset)
    prior_error: Optional[str] = None
    hypotheses: Optional[str] = None
    verify_round = 0
    repairs = 0
    verdict = {"status": "REVISE", "hypotheses": ""}
    code = ""
    result = {"status": "error", "stdout": "", "stderr": "", "figures": [], "returncode": None}
    unverified = True

    while True:
        code, result = _gen_and_run(question, prof, out_dir, codegen_fn, guard_fn,
                                    exec_fn, prior_error, hypotheses, timeout, max_output)
        prior_error = None
        hypotheses = None
        while result["status"] == "error" and repairs < max_repair:
            repairs += 1
            code, result = _gen_and_run(question, prof, out_dir, codegen_fn, guard_fn,
                                        exec_fn, result["stderr"], None, timeout, max_output)
        if result["status"] == "error":
            verdict = {"status": "REVISE",
                       "hypotheses": "code could not be made to run: " + result["stderr"]}
            unverified = True
            break
        verdict = verify_fn(question, code, result["stdout"])
        if verdict["status"] == "OK":
            unverified = False
            break
        verify_round += 1
        if verify_round > max_verify:
            unverified = True
            break
        hypotheses = verdict["hypotheses"]

    report_md = report_fn(question, result["stdout"], result["figures"],
                          verified=not unverified)
    audit.append_event({"type": "analyze", "dataset": dataset, "question": question,
                        "verified": not unverified, "status": result["status"],
                        "repairs": repairs, "verify_rounds": verify_round})
    return {"dataset": dataset, "question": question, "code": code,
            "status": result["status"], "verified": not unverified, "verdict": verdict,
            "figures": result["figures"], "report": report_md,
            "repairs": repairs, "verify_rounds": verify_round}


def _role_chat(rc: RoleClient, role: str) -> Callable:
    """Return a ``messages -> text`` callable bound to *role*."""
    return lambda messages: rc.chat(role, messages)


def _cmd_health() -> int:
    rc = RoleClient(load_config())
    try:
        rc.chat("codegen", [{"role": "user", "content": "ping"}], max_tokens=1)
        print(json.dumps({"codegen": "ok"}, indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001 - health must never raise
        print(json.dumps({"codegen": f"error: {exc}"}, indent=2))
        return 1


def _cmd_profile(dataset: str) -> int:
    print(json.dumps(profile_mod.profile_dataset(dataset), indent=2, default=str))
    return 0


def _cmd_analyze(dataset: str, question: str, out_dir: str,
                 max_repair: int, max_verify: int) -> int:
    rc = RoleClient(load_config())
    summary = run_analysis(
        dataset, question, out_dir=out_dir, max_repair=max_repair, max_verify=max_verify,
        codegen_fn=lambda q, p, pe=None, hy=None: generate.generate_code(
            q, p, _role_chat(rc, "codegen"), pe, hy),
        verify_fn=lambda q, c, o: verify_mod.verify(q, c, o, _role_chat(rc, "verify")),
        report_fn=lambda q, o, f, verified=True: report_mod.generate_report(
            q, o, f, _role_chat(rc, "report"), verified=verified),
    )
    print(json.dumps(summary, indent=2, default=str))
    return 0


def _cmd_audit(limit: int) -> int:
    events = audit.read_events()
    if limit and limit > 0:
        events = events[-limit:]
    print(json.dumps({"events": events}, indent=2, default=str))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(prog="data_copilot", description="Data Copilot CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("health", help="Check the configured LLM endpoint is reachable.")
    p_prof = sub.add_parser("profile", help="Print a dataset profile as JSON.")
    p_prof.add_argument("dataset")
    p_an = sub.add_parser("analyze", help="Run the full analysis loop.")
    p_an.add_argument("dataset")
    p_an.add_argument("question")
    p_an.add_argument("--out", default=None, help="Run output dir (default: runs/latest).")
    p_an.add_argument("--max-repair", type=int, default=3)
    p_an.add_argument("--max-verify", type=int, default=2)
    p_aud = sub.add_parser("audit", help="Show recent audit-trail events.")
    p_aud.add_argument("--limit", type=int, default=50)
    return parser


def _default_out_dir() -> str:
    return str(Path(__file__).resolve().parent.parent / "runs" / "latest")


def main(argv: Optional[list] = None) -> int:
    """CLI entry point.

    Returns:
        ``0`` on success, ``1`` when health fails, ``2`` for an unknown command.
    """
    args = build_parser().parse_args(argv)
    if args.command == "health":
        return _cmd_health()
    if args.command == "profile":
        return _cmd_profile(args.dataset)
    if args.command == "analyze":
        return _cmd_analyze(args.dataset, args.question,
                            args.out or _default_out_dir(),
                            args.max_repair, args.max_verify)
    if args.command == "audit":
        return _cmd_audit(args.limit)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_data_copilot_cli.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Run the whole module test suite**

Run: `uv run pytest tests/test_data_copilot_*.py -v`
Expected: PASS (all data_copilot tests green).

- [ ] **Step 6: Commit**

```bash
git add modules/data_copilot/scripts/copilot.py tests/test_data_copilot_cli.py
git commit -m "feat(data_copilot): orchestrator CLI + analysis loop"
```

---

### Task 11: Presentation — `manifest.json`, `dashboard.html`, final `SKILL.md`, `icon.svg`

**Files:**
- Create: `modules/data_copilot/manifest.json`
- Create: `modules/data_copilot/dashboard.html`
- Create: `modules/data_copilot/icon.svg`
- Modify: `modules/data_copilot/SKILL.md` (replace the minimal stub with the full body)
- Test: `tests/test_data_copilot_module_loads.py`

**Interfaces:**
- Consumes: `atria.core.modules.store.read_module` (validates the module is well-formed and discoverable by the registry).
- Produces: a fully-formed module directory the registry loads with a valid manifest, dashboard, and subskill-free SKILL.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_copilot_module_loads.py
"""The data_copilot module is well-formed and loads via the module store."""
from __future__ import annotations

import json
from pathlib import Path

from atria.core.modules import store

_ROOT = Path(__file__).resolve().parent.parent / "modules"


def test_module_reads_with_manifest_and_description():
    mod = store.read_module(_ROOT, "data_copilot")
    assert mod.name == "data_copilot"
    assert "data" in mod.description.lower()
    assert mod.manifest is not None
    assert mod.manifest.display_name == "Data Copilot"
    # dashboard declared
    assert mod.manifest.dashboard is not None


def test_manifest_json_is_valid_and_has_activity_labels():
    raw = json.loads((_ROOT / "data_copilot" / "manifest.json").read_text())
    assert raw["activity"]["actions"]["analyze"]["running"]
    assert raw["activity"]["actions"]["profile"]["running"]


def test_key_scripts_present():
    scripts = _ROOT / "data_copilot" / "scripts"
    for name in ["config", "client", "profile", "guardrails", "sandbox",
                 "generate", "verify", "report", "audit", "copilot"]:
        assert (scripts / f"{name}.py").is_file(), name
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_module_loads.py -v`
Expected: FAIL — `manifest.json` missing / `display_name` assertion fails.

- [ ] **Step 3: Write `manifest.json`**

```json
{
  "display_name": "Data Copilot",
  "tooltip": "Data-analysis copilot · generate → run → verify → grounded report",
  "icon": "icon.svg",
  "dashboard": {
    "title": "Data Copilot · Analysis Loop",
    "default_height": 780,
    "badge_color": "info"
  },
  "activity": {
    "default": { "running": "Working…", "done": "Done" },
    "actions": {
      "profile": { "running": "Profiling dataset…", "done": "Profiled" },
      "analyze": { "running": "Analyzing…",         "done": "Report ready" }
    }
  },
  "subagent": {
    "enabled": false,
    "model": null,
    "tools": null
  }
}
```

- [ ] **Step 4: Write `icon.svg`**

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
     stroke="currentColor" stroke-width="2" stroke-linecap="round"
     stroke-linejoin="round">
  <path d="M3 3v18h18" />
  <rect x="7" y="12" width="3" height="6" />
  <rect x="12" y="8" width="3" height="10" />
  <rect x="17" y="5" width="3" height="13" />
</svg>
```

- [ ] **Step 5: Write the full `SKILL.md`** (replaces the Task 1 stub)

```markdown
---
name: data_copilot
description: Data-analysis copilot — answers a natural-language question about a tabular dataset (CSV/Excel/Parquet) by generating Python, running it in a bounded sandbox, self-repairing on error, semantically verifying the result, and returning a grounded Markdown report with charts. Use for exploratory data analysis, ad-hoc metrics, and quick dataset Q&A.
---

# data_copilot

**Data-analysis copilot.** Given a tabular dataset and a natural-language
question, this module generates Python, runs it in a bounded local sandbox,
repairs execution errors, semantically verifies that the output answers the
question, and returns a grounded Markdown report (with any charts).

The loop is a clean reimplementation of the analysis pipeline from the
`data-agent` project — no self-evolution engine, no external UI.

## When to use

Reach for this module when the user has a dataset (CSV, Excel, or Parquet) and
asks a question that is answered by computing over it — totals, breakdowns,
correlations, trends, quick charts — rather than by reading documentation.

## How to use

Run the CLI via the bash tool (``<modules>`` resolves to the active modules
directory — see the SKILL block header in the system prompt):

- Health check: `python <modules>/data_copilot/scripts/copilot.py health`
- Profile a dataset:
  `python <modules>/data_copilot/scripts/copilot.py profile path/to/data.csv`
- Analyze:
  `python <modules>/data_copilot/scripts/copilot.py analyze path/to/data.csv "What is total revenue by region?"`
  Flags: `--max-repair` (default 3), `--max-verify` (default 2), `--out <dir>`.
- Recent audit events:
  `python <modules>/data_copilot/scripts/copilot.py audit --limit 20`

Configure the model via `DC_<ROLE>_*` env vars (roles: `codegen`, `verify`,
`report`). Defaults target OpenAI with `OPENAI_API_KEY`; point
`DC_CODEGEN_BASE_URL`/`_MODEL`/`_API_KEY` at a local vLLM/Ollama endpoint to run
offline.

## Guardrails (non-negotiable)

- **Bounded execution.** Generated code runs as a timeout-bounded, output-capped
  subprocess scoped to a run directory. Network access, process spawning, and
  writes outside the run directory are statically blocked before execution.
- **Grounded reports.** The report is grounded in the code's actual printed
  output and produced figures — no invented numbers.
- **No unverified answers presented as settled.** If the repair or verification
  budget is exhausted, the report is labelled UNVERIFIED.
- **Auditable.** Every analysis appends an event (question, dataset, verified,
  retry counts) to the audit trail.
```

- [ ] **Step 6: Write `dashboard.html`**

A single self-contained HTML page (inline CSS, no external assets) titled
"Data Copilot · Analysis Loop" that renders: a one-paragraph concept summary,
the loop diagram (profile → generate → guardrail → execute → repair → verify →
report), the four CLI commands, and the guardrails list. Model the visual style
on `modules/maintenance_copilot/dashboard.html` (read it first for the shared
look). Keep it under ~200 lines; the body must not scroll horizontally.

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Data Copilot · Analysis Loop</title>
  <style>
    :root { --ink:#1f2933; --muted:#647089; --accent:#2f6feb; --line:#e3e8f0; }
    body { font-family: system-ui, sans-serif; color: var(--ink); margin: 0;
           padding: 2rem; line-height: 1.55; max-width: 900px; }
    h1 { font-size: 1.5rem; margin: 0 0 .25rem; }
    .sub { color: var(--muted); margin: 0 0 1.5rem; }
    .loop { display: flex; flex-wrap: wrap; gap: .5rem; margin: 1rem 0; }
    .step { border: 1px solid var(--line); border-radius: 8px; padding: .5rem .75rem;
            background: #f7f9fc; font-size: .9rem; }
    .arrow { color: var(--accent); align-self: center; }
    code { background: #f2f4f8; padding: .1rem .35rem; border-radius: 4px; }
    ul { padding-left: 1.2rem; }
    section { border-top: 1px solid var(--line); padding-top: 1.25rem; margin-top: 1.5rem; }
  </style>
</head>
<body>
  <h1>Data Copilot</h1>
  <p class="sub">Ask a question about a dataset — the copilot generates Python,
     runs it in a bounded sandbox, self-repairs, verifies, and returns a grounded
     report.</p>

  <section>
    <h2>The loop</h2>
    <div class="loop">
      <span class="step">Profile dataset</span><span class="arrow">→</span>
      <span class="step">Generate code</span><span class="arrow">→</span>
      <span class="step">Guardrail gate</span><span class="arrow">→</span>
      <span class="step">Execute (sandbox)</span><span class="arrow">→</span>
      <span class="step">Repair on error</span><span class="arrow">→</span>
      <span class="step">Verify answer</span><span class="arrow">→</span>
      <span class="step">Grounded report</span>
    </div>
  </section>

  <section>
    <h2>Commands</h2>
    <ul>
      <li><code>copilot.py health</code> — check the LLM endpoint</li>
      <li><code>copilot.py profile &lt;data&gt;</code> — dataset schema + stats</li>
      <li><code>copilot.py analyze &lt;data&gt; "&lt;question&gt;"</code> — full loop</li>
      <li><code>copilot.py audit --limit N</code> — recent runs</li>
    </ul>
  </section>

  <section>
    <h2>Guardrails</h2>
    <ul>
      <li>Bounded execution: timeout, output cap, scoped run dir; no network,
          no process spawning, no writes outside the run dir.</li>
      <li>Reports grounded in actual computed output — no invented numbers.</li>
      <li>Exhausted repair/verify budget ⇒ result labelled UNVERIFIED.</li>
      <li>Every analysis is appended to the audit trail.</li>
    </ul>
  </section>
</body>
</html>
```

- [ ] **Step 7: Run test to verify it passes**

Run: `uv run pytest tests/test_data_copilot_module_loads.py -v`
Expected: PASS (3 passed).

- [ ] **Step 8: Commit**

```bash
git add modules/data_copilot/manifest.json modules/data_copilot/dashboard.html \
        modules/data_copilot/icon.svg modules/data_copilot/SKILL.md \
        tests/test_data_copilot_module_loads.py
git commit -m "feat(data_copilot): manifest, dashboard, full SKILL, icon"
```

---

### Task 12: End-to-end verification with a real LLM

**Files:**
- None created (verification task). Uses `sample_data/demo.csv`.

**Interfaces:**
- Consumes: the finished module and `OPENAI_API_KEY`.

- [ ] **Step 1: Confirm the full unit suite is green**

Run: `uv run pytest tests/test_data_copilot_*.py -v`
Expected: PASS (all data_copilot tests).

- [ ] **Step 2: Format + lint + typecheck**

Run: `make format && make lint && make typecheck`
Expected: no errors introduced by the new module.

- [ ] **Step 3: Real health check**

Run:
```bash
export OPENAI_API_KEY="<key>"
python modules/data_copilot/scripts/copilot.py health
```
Expected: `{"codegen": "ok"}` and exit code 0.

- [ ] **Step 4: Real end-to-end analysis**

Run:
```bash
python modules/data_copilot/scripts/copilot.py analyze \
  modules/data_copilot/sample_data/demo.csv \
  "What is the total revenue by region, and which region is highest?" \
  --out /tmp/dc_run
```
Expected (verify by reading the JSON summary printed to stdout):
- `"verified": true`
- `"status": "text"`
- `"report"` contains regional totals grounded in the CSV (West/South highest),
- `"repairs"` is a small integer (0–3).

- [ ] **Step 5: Confirm the audit trail recorded the run**

Run: `python modules/data_copilot/scripts/copilot.py audit --limit 5`
Expected: a JSON `events` array whose last entry has `"type": "analyze"` and the
question above.

- [ ] **Step 6: Commit any fixes**

If Steps 2–5 surfaced issues, fix them (with a failing test first where
applicable), re-run, and commit:
```bash
git add -A
git commit -m "fix(data_copilot): address end-to-end findings"
```

---

## Notes for the implementer

- The reference implementation lives at `.reference/data-agent/` (read-only).
  Map: loop → `langgraph_agent/graph.py` + `nodes.py`; code extraction →
  `utils/utils.py::extract_code`; verify → `triadic_dgm/agent/verifier.py`;
  report → `triadic_dgm/services/report_generator.py`. Reimplement — do not
  import from there.
- The module contract is enforced by `atria/core/modules/store.py` (only
  `SKILL.md` is strictly required) and dependencies auto-install via
  `atria/core/modules/registry.py::install_module_deps`.
- Mirror `modules/maintenance_copilot/` for every convention (script header
  `sys.path.insert`, JSON stdout, audit trail, manifest shape).
