"""Keep tests away from the developer's real config.json and downloads folder."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def core(tmp_path, monkeypatch):
    import core as core_module

    monkeypatch.setattr(core_module, "CONFIG", str(tmp_path / "config.json"))
    monkeypatch.setattr(core_module, "DEFAULT_OUT_DIR", str(tmp_path / "downloads"))
    monkeypatch.setattr(core_module, "run_job", lambda *a: None)  # never start a real download
    core_module.jobs.clear()
    core_module.partials.clear()
    yield core_module
    core_module.jobs.clear()
    core_module.partials.clear()
