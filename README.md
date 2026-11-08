# ae-bridge

[![CI](https://github.com/WaifaiMT/ae-bridge/actions/workflows/ci.yml/badge.svg)](https://github.com/WaifaiMT/ae-bridge/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A minimal [MCP](https://modelcontextprotocol.io) server that lets an AI agent (Claude Code, Claude Desktop, or any MCP client) drive a running Adobe After Effects: build comps, add layers and effects, set keyframes and expressions, convert Illustrator logos to shapes, and render. There is no plugin or panel to install inside AE.

**Windows only.** It uses `AfterFX.exe -r` and the default `C:\Program Files\Adobe\...` install location. You need your own licensed copy of After Effects.

> Not affiliated with or endorsed by Adobe. After Effects and ExtendScript are trademarks of Adobe Inc.

## How it works

1. A tool call becomes an ExtendScript job: helpers (`prelude.jsx`), your arguments and the tool's script body.
2. The job is written to `%TEMP%\ae-bridge\<id>.jsx` and handed to the open AE with `AfterFX.exe -r <file>`.
3. The script writes `{ok, value | error}` as JSON to `<id>.json`, writing a temporary file first and then renaming it.
4. Python polls for the file, reads it and returns the result.

Each editing tool is wrapped in an undo group, so one Ctrl+Z in AE undoes one tool call. Dialogs are suppressed while the job runs.

## Setup

1. In AE: **Edit > Preferences > Scripting & Expressions > Allow Scripts to Write Files and Access Network**. Without this setting, every call times out.
2. `uv sync`
3. With AE open: `uv run ae-bridge ping`

Register with Claude Code (replace the path with where you cloned it):

```
git clone https://github.com/WaifaiMT/ae-bridge.git
claude mcp add -s user aftereffects -- uv --directory C:/path/to/ae-bridge run ae-bridge
```

## CLI

```
ae-bridge ping
ae-bridge eval "return app.project.numItems;"
ae-bridge exec script.jsx      # file body runs as a function; use return
```

## Environment variables

| Var | Default | Meaning |
|---|---|---|
| `AE_BRIDGE_AFTERFX` | newest `C:\Program Files\Adobe\Adobe After Effects*\Support Files\AfterFX.exe` | AE executable |
| `AE_BRIDGE_TIMEOUT` | `60` | seconds per call |
| `AE_BRIDGE_AUTOLAUNCH` | `0` | `1` = launch AE if it isn't running (the first call waits for startup) |
| `AE_BRIDGE_DIR` | `%TEMP%\ae-bridge` | job/result folder |

## Tools

`ping`, `eval_jsx`, `project_info`, `list_comps`, `comp_info`, `create_comp`, `add_text_layer`, `add_solid`,
`add_null`, `add_item_to_comp`, `import_file`, `convert_to_shapes`, `get_property`, `set_property`, `set_keyframes`,
`set_expression`, `add_effect`, `layer_update`, `render_frame`, `render`, `save_project`, `open_project`.

Addressing:
- Comps: by name or project index. Leave `comp` out to use the active comp.
- Layers: by name or 1-based index.
- Properties: by a `/` path of display or match names, e.g. `Transform/Position` or `Effects/Gaussian Blur/Blurriness`.
- Units: times in seconds, colors as `[r,g,b]` from 0 to 1.

In `eval_jsx`, the helpers `AEB.comp()`, `AEB.layer()`, `AEB.prop()`, `AEB.item()` and `AEB.json()` are available.

## Limits

- Each call takes about 0.3–1 s to start up.
- A modal dialog in AE blocks calls until someone closes it, and the call times out with a hint.
- `render` blocks AE until the render finishes. For long renders, consider `aerender.exe` instead.
- Calls run one at a time (there is a lock).

## Illustrator logos

1. `import_file(path="logo.ai", as_comp=True)` makes each top-level Illustrator layer its own AE layer.
2. `convert_to_shapes(comp="logo")` turns every `.ai`/`.eps`/`.pdf` layer into an editable shape layer.
   - By default it deletes the original vector layer and gives the shape layer its name, so layer names still work.
   - Pass `keep_original=True` to keep the originals. AE turns their video off.
   - Pass `layers=[...]` to convert only some layers.
3. Animate the paths, e.g. add `ADBE Vector Filter - Trim` and keyframe `ADBE Vector Trim End` from 0 to 100 for a draw-on.

## Development

```
uv sync
uv run ruff check .
uv run pytest
```

The tests don't need After Effects: they replace `AfterFX.exe` with a fake that reads the job script and writes the result file, and check that the README lists exactly the tools the server registers. CI runs them on Windows and Linux.

## License

[MIT](LICENSE) © 2026 Gilbert Addai Gyan
