"""Runs ExtendScript inside a running After Effects via `AfterFX.exe -r` and reads back a JSON result file."""

from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

PRELUDE = (Path(__file__).parent / "prelude.jsx").read_text(encoding="utf-8")
WORK_DIR = Path(os.environ.get("AE_BRIDGE_DIR") or Path(tempfile.gettempdir()) / "ae-bridge")
DEFAULT_TIMEOUT = float(os.environ.get("AE_BRIDGE_TIMEOUT", "60"))
AUTO_LAUNCH = os.environ.get("AE_BRIDGE_AUTOLAUNCH", "0") == "1"

_lock = threading.Lock()


class AEError(RuntimeError):
    pass


def find_afterfx() -> str:
    env = os.environ.get("AE_BRIDGE_AFTERFX")
    if env:
        if not Path(env).is_file():
            raise AEError(f"AE_BRIDGE_AFTERFX points to a missing file: {env}")
        return env
    candidates = glob.glob(r"C:\Program Files\Adobe\Adobe After Effects*\Support Files\AfterFX.exe")

    def key(p: str):
        m = re.search(r"After Effects (?:\(Beta\)|(\d{4}))", p)
        return int(m.group(1)) if m and m.group(1) else 0

    candidates.sort(key=key, reverse=True)
    if not candidates:
        raise AEError("AfterFX.exe not found. Set AE_BRIDGE_AFTERFX to its full path.")
    return candidates[0]


def ae_running() -> bool:
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq AfterFX.exe", "/NH"],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout
    except Exception:
        return True  # can't tell; let the call try
    return "afterfx.exe" in out.lower()


def _js_literal(value) -> str:
    # JSON is a valid JS literal except for U+2028/2029 in older engines.
    return json.dumps(value, ensure_ascii=True)


def build_script(body: str, args: dict | None, out_path: Path, undo: str | None) -> str:
    out = out_path.as_posix()
    return f"""{PRELUDE}
(function () {{
    var OUT = {_js_literal(out)};
    var ARGS = {_js_literal(args or {})};
    var UNDO = {_js_literal(undo)};
    var r;
    try {{ app.beginSuppressDialogs(); }} catch (e0) {{}}
    if (UNDO) app.beginUndoGroup(UNDO);
    try {{
        var v = (function (args) {{
{body}
        }})(ARGS);
        r = '{{"ok":true,"value":' + AEB.json(v) + '}}';
    }} catch (e) {{
        r = '{{"ok":false,"error":' + AEB.q(String(e)) + ',"line":' + (e && e.line ? e.line : 'null') + '}}';
    }} finally {{
        if (UNDO) {{ try {{ app.endUndoGroup(); }} catch (e1) {{}} }}
        try {{ app.endSuppressDialogs(false); }} catch (e2) {{}}
    }}
    var f = new File(OUT + '.tmp');
    f.encoding = 'UTF-8';
    f.open('w');
    f.write(r);
    f.close();
    f.rename(File(OUT).name);
}})();
"""


def run_jsx(body: str, args: dict | None = None, *, undo: str | None = None,
            timeout: float | None = None):
    """Run `body` (a function body; use `return`) inside AE. `args` is available as `args`."""
    timeout = timeout or DEFAULT_TIMEOUT
    afterfx = find_afterfx()
    if not ae_running():
        if not AUTO_LAUNCH:
            raise AEError("After Effects is not running. Open it (or set AE_BRIDGE_AUTOLAUNCH=1).")
        timeout = max(timeout, 180)

    WORK_DIR.mkdir(parents=True, exist_ok=True)
    jid = uuid.uuid4().hex
    jsx = WORK_DIR / f"{jid}.jsx"
    out = WORK_DIR / f"{jid}.json"
    jsx.write_text(build_script(body, args, out, undo), encoding="utf-8-sig")

    with _lock:
        subprocess.Popen(
            [afterfx, "-r", str(jsx)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        deadline = time.monotonic() + timeout
        while not out.exists():
            if time.monotonic() > deadline:
                raise AEError(
                    f"No response from After Effects after {timeout:.0f}s. Likely causes: a modal dialog "
                    "is open in AE, AE is busy rendering, or 'Allow Scripts to Write Files and Access "
                    "Network' is off (Settings > Scripting & Expressions). Job file: " + str(jsx)
                )
            time.sleep(0.05)

    raw = out.read_text(encoding="utf-8-sig")
    for p in (jsx, out):
        try:
            p.unlink()
        except OSError:
            pass
    result = json.loads(raw)
    if not result.get("ok"):
        line = result.get("line")
        raise AEError(f"AE script error: {result.get('error')}" + (f" (line {line})" if line else ""))
    return result.get("value")
