"""ae-bridge CLI.

  ae-bridge                 run the MCP server (stdio)
  ae-bridge serve           same
  ae-bridge ping            check the connection to After Effects
  ae-bridge eval CODE       run an ExtendScript function body (use `return`)
  ae-bridge exec FILE.jsx   run a file's contents as a function body
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    argv = sys.argv[1:]
    cmd = argv[0] if argv else "serve"
    if cmd == "serve":
        from .server import serve
        serve()
        return
    if cmd in ("-h", "--help", "help"):
        print(__doc__)
        return

    from .runner import AEError, run_jsx
    try:
        if cmd == "ping":
            from .server import ping
            out = ping()
        elif cmd == "eval" and len(argv) > 1:
            out = run_jsx(argv[1])
        elif cmd == "exec" and len(argv) > 1:
            out = run_jsx(Path(argv[1]).read_text(encoding="utf-8-sig"))
        else:
            print(__doc__)
            sys.exit(2)
    except AEError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
