"""Runner tests that don't need After Effects.

`subprocess.Popen` is replaced by a fake "After Effects" that reads the job script it is given,
finds the result path the script would write to, and writes a result there, the way AE does.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from ae_bridge import runner
from ae_bridge.runner import AEError, build_script, run_jsx


@pytest.fixture
def fake_ae(tmp_path, monkeypatch):
    """Point the runner at a temp folder and a fake AfterFX.exe that answers with `reply`."""
    exe = tmp_path / "AfterFX.exe"
    exe.write_text("")
    monkeypatch.setenv("AE_BRIDGE_AFTERFX", str(exe))
    monkeypatch.setattr(runner, "WORK_DIR", tmp_path / "jobs")
    monkeypatch.setattr(runner, "ae_running", lambda: True)

    state = {"reply": {"ok": True, "value": None}, "calls": [], "respond": True}

    class FakePopen:
        def __init__(self, cmd, **kwargs):
            state["calls"].append(cmd)
            assert cmd[0] == str(exe) and cmd[1] == "-r"
            script = Path(cmd[2]).read_text(encoding="utf-8-sig")
            out = json.loads(re.search(r"var OUT = (\".*?\");", script).group(1))
            if state["respond"]:
                # AE writes <out>.tmp then renames it; the end state is the same file.
                Path(out).write_text(json.dumps(state["reply"]), encoding="utf-8")

    monkeypatch.setattr(runner.subprocess, "Popen", FakePopen)
    return state


def test_returns_the_value_and_cleans_up(fake_ae, tmp_path):
    fake_ae["reply"] = {"ok": True, "value": {"numItems": 3}}

    assert run_jsx("return app.project.numItems;") == {"numItems": 3}
    assert list((tmp_path / "jobs").iterdir()) == [], "job and result files are deleted"


def test_a_script_error_is_raised_with_its_line(fake_ae):
    fake_ae["reply"] = {"ok": False, "error": "ReferenceError: foo is undefined", "line": 7}

    with pytest.raises(AEError, match=r"foo is undefined \(line 7\)"):
        run_jsx("return foo;")


def test_no_answer_times_out_with_a_hint(fake_ae):
    fake_ae["respond"] = False

    with pytest.raises(AEError, match="Allow Scripts to Write Files"):
        run_jsx("return 1;", timeout=0.2)


def test_refuses_when_after_effects_is_not_running(fake_ae, monkeypatch):
    monkeypatch.setattr(runner, "ae_running", lambda: False)
    monkeypatch.setattr(runner, "AUTO_LAUNCH", False)

    with pytest.raises(AEError, match="not running"):
        run_jsx("return 1;")
    assert fake_ae["calls"] == []


def test_a_missing_afterfx_path_is_reported(monkeypatch, tmp_path):
    monkeypatch.setenv("AE_BRIDGE_AFTERFX", str(tmp_path / "nope.exe"))

    with pytest.raises(AEError, match="missing file"):
        runner.find_afterfx()


def test_the_script_wraps_edits_in_one_undo_group_and_passes_args():
    out = Path("C:/tmp/ae-bridge/abc.json")

    with_undo = build_script("return args.n;", {"n": 2, "name": "Logo \u2028"}, out, "ae-bridge: set_property")
    assert 'app.beginUndoGroup(UNDO)' in with_undo and 'var UNDO = "ae-bridge: set_property";' in with_undo
    assert 'var ARGS = {"n": 2, "name": "Logo \\u2028"};' in with_undo, "args are escaped JS literals"
    assert 'var OUT = "C:/tmp/ae-bridge/abc.json";' in with_undo
    assert "beginSuppressDialogs" in with_undo

    read_only = build_script("return 1;", None, out, None)
    assert "var UNDO = null;" in read_only
