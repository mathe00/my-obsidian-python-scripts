"""Shared test infrastructure for the OPB scripts test-suite.

The scripts under test import ``ObsidianPluginDevPythonToJS`` at module level
and execute part of their boilerplate (event guard, settings discovery) at
*import time*. Since the real bridge library only exists inside an Obsidian
installation (or the plugin dev clone), this conftest injects a **stub module**
into ``sys.modules`` *before* any script import happens.

Two loading strategies coexist:

1. **Unit tests** load scripts via :func:`load_script` (handles the hyphen in
   ``script-auto-linker.py`` which is not a valid Python identifier) against
   the injected stub — fast, fully isolated, no network, no HTTP.

2. **Integration tests** (optional) execute the scripts in a subprocess with
   ``PYTHONPATH`` pointed at the local Obsidian Python Bridge dev clone,
   exercising the REAL current library (event guard, ``--get-settings-json``
   discovery). They self-skip when the clone cannot be located.
"""

import importlib.util
import os
import subprocess
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent

# Candidate locations of the Obsidian Python Bridge source (shim + package).
_OPB_CLONE_CANDIDATES = [
    Path.home() / "Documents/Obsidian/MonOrganisation/.obsidian/plugins/obsidian-python-bridge",
]


def find_opb_clone() -> Path | None:
    """Return the first existing OPB library directory, or None."""
    for candidate in _OPB_CLONE_CANDIDATES:
        shim = candidate / "ObsidianPluginDevPythonToJS.py"
        if shim.exists():
            return candidate
    return None


# ---------------------------------------------------------------------------
# Stub bridge module — installed BEFORE any script import
# ---------------------------------------------------------------------------


class _StubBridgeModule(types.ModuleType):
    """Minimal stand-in for ObsidianPluginDevPythonToJS.py."""

    def __init__(self) -> None:
        super().__init__("ObsidianPluginDevPythonToJS")

        class ObsidianCommError(Exception):
            """Mirror of the real exception raised on bridge failures."""

            def __init__(
                self, message: str, action: str | None = None, status_code: int | None = None
            ):
                super().__init__(message)
                self.action = action
                self.status_code = status_code

        def define_settings(settings_list):
            return None

        def _handle_cli_args():
            return None  # Never exits during unit tests.

        def is_handling_event():
            # Mirror the real behaviour: read the environment each call.
            return bool(os.environ.get("OBSIDIAN_EVENT_NAME"))

        # Callable factory: ObsidianPluginDevPythonToJS() -> MagicMock client.
        client_factory = MagicMock(name="ObsidianPluginDevPythonToJSClass")

        self.ObsidianCommError = ObsidianCommError
        self.define_settings = define_settings
        self._handle_cli_args = _handle_cli_args
        self.is_handling_event = is_handling_event
        self.ObsidianPluginDevPythonToJS = client_factory


def install_bridge_stub() -> types.ModuleType:
    """Idempotently inject the stub module into sys.modules and return it."""
    existing = sys.modules.get("ObsidianPluginDevPythonToJS")
    if isinstance(existing, _StubBridgeModule):
        return existing
    stub = _StubBridgeModule()
    sys.modules["ObsidianPluginDevPythonToJS"] = stub
    return stub


# Installing at conftest import time guarantees the stub precedes every import.
install_bridge_stub()


# ---------------------------------------------------------------------------
# Script loader (hyphen-safe)
# ---------------------------------------------------------------------------

_LOADED_SCRIPTS: dict[str, object] = {}


def load_script(filename: str):
    """Import a repo-root script as a module, fresh per unique filename.

    Uses :func:`importlib.util.spec_from_file_location` because
    ``script-auto-linker.py`` contains a hyphen and cannot be imported
    through normal package machinery.
    """
    cached = _LOADED_SCRIPTS.get(filename)
    if cached is not None:
        return cached

    path = REPO_ROOT / filename
    if not path.exists():
        raise FileNotFoundError(f"Script not found: {path}")

    module_name = "script_under_test_" + filename.removesuffix(".py").replace("-", "_")
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None, f"Cannot build import spec for {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module  # Register: some introspection needs it.
    spec.loader.exec_module(module)

    _LOADED_SCRIPTS[filename] = module
    return module


def reload_script(filename: str):
    """Force-reload a script module (used when import-time state matters)."""
    _LOADED_SCRIPTS.pop(filename, None)
    name = "script_under_test_" + filename.removesuffix(".py").replace("-", "_")
    sys.modules.pop(name, None)
    return load_script(filename)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_bridge_environment(monkeypatch):
    """Guarantee deterministic import/execution context for every test.

    - No event variables: scripts behave as manually triggered.
    - Clean argv: ``_handle_cli_args``-style parsing never sees pytest args.
    """
    monkeypatch.delenv("OBSIDIAN_EVENT_NAME", raising=False)
    monkeypatch.delenv("OBSIDIAN_EVENT_PAYLOAD", raising=False)
    monkeypatch.setattr(sys, "argv", ["script-under-test"])


@pytest.fixture()
def bridge_stub():
    """Direct access to the injected stub module (e.g. its ObsidianCommError)."""
    return install_bridge_stub()


@pytest.fixture()
def fake_bridge():
    """A MagicMock standing in for ObsidianPluginDevPythonToJS() results.

    Pre-configured with sane defaults; individual tests override attributes::

        fake_bridge.get_selected_text.return_value = "serendipity"
        fake_bridge.get_active_note_content.return_value = "# Title\\nbody"
    """
    client = MagicMock(name="fake_obsidian_client")
    client.get_selected_text.return_value = ""
    client.get_active_note_absolute_path.return_value = "/vault/notes/active.md"
    client.get_active_note_content.return_value = ""
    client.get_all_note_paths.return_value = []
    client.get_script_settings.return_value = {}
    client.show_notification.return_value = None
    client.modify_note_content.return_value = None
    return client


@pytest.fixture()
def bind_client(monkeypatch, fake_bridge):
    """Bind ``ObsidianPluginDevPythonToJS()`` to *fake_bridge* inside a script module.

    Scripts do ``from ... import ObsidianPluginDevPythonToJS`` at import time,
    so the name lives on the *script module* — patching the stub would be too
    late. Usage::

        bind_client(mod)
        mod.run(fake_bridge)
    """

    def _bind(module):
        from unittest.mock import MagicMock

        monkeypatch.setattr(
            module, "ObsidianPluginDevPythonToJS", MagicMock(return_value=fake_bridge)
        )
        return fake_bridge

    return _bind


# ---------------------------------------------------------------------------
# Integration helpers (real OPB library, subprocess)
# ---------------------------------------------------------------------------


def run_script_subprocess(script_name: str, extra_env: dict[str, str], args: list[str]):
    """Run a script in a subprocess using the REAL OPB library if available.

    Skips when no OPB clone is found. Returns CompletedProcess.
    """
    opb_dir = find_opb_clone()
    if opb_dir is None:
        pytest.skip("Obsidian Python Bridge clone not found — skipping integration test")

    env = os.environ.copy()
    env.pop("OBSIDIAN_EVENT_NAME", None)
    env.pop("OBSIDIAN_EVENT_PAYLOAD", None)
    env["PYTHONPATH"] = str(opb_dir)
    env.update(extra_env)

    return subprocess.run(
        [sys.executable, str(REPO_ROOT / script_name), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(opb_dir),
    )
