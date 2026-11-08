"""MCP tools for After Effects. Every tool sends one ExtendScript job through runner.run_jsx."""

from __future__ import annotations

import time as time_mod
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .runner import AEError, find_afterfx, run_jsx

mcp = FastMCP(
    "aftereffects",
    instructions=(
        "Controls a running Adobe After Effects through ExtendScript. "
        "Comps are addressed by name (or project item index); layers by name or 1-based index; "
        "properties by '/'-separated path of display or match names, e.g. 'Transform/Position', "
        "'Effects/Gaussian Blur/Blurriness'. Times are in seconds. Colors are [r,g,b] in 0..1. "
        "Use eval_jsx for anything the specific tools don't cover; AEB.comp/layer/prop helpers are available there. "
        "Editing tools are wrapped in an undo group, so one Ctrl+Z in AE reverts one tool call."
    ),
)

CompRef = str | int | None
LayerRef = str | int


@mcp.tool()
def ping() -> dict:
    """Check the bridge: returns AE version and the open project's path."""
    return run_jsx("""
        return { version: app.version, build: app.buildName,
                 project: app.project.file ? app.project.file.fsName : null,
                 numItems: app.project.numItems,
                 afterfx: args.afterfx };""", {"afterfx": find_afterfx()}, timeout=30)


@mcp.tool()
def eval_jsx(code: str, undo_name: str | None = None, timeout: float | None = None) -> Any:
    """Run ExtendScript inside AE. `code` is a function body: use `return` to send back a value
    (plain objects/arrays/numbers/strings serialize to JSON). Helpers: AEB.comp(nameOrIndex),
    AEB.layer(comp, nameOrIndex), AEB.prop(layer, 'Transform/Position'), AEB.item(nameOrIndex).
    Pass undo_name to wrap the edit in an undo group."""
    return run_jsx(code, undo=undo_name, timeout=timeout)


@mcp.tool()
def project_info() -> dict:
    """List every project item (id/index, name, type, parent folder)."""
    return run_jsx("""
        var p = app.project, items = [];
        for (var i = 1; i <= p.numItems; i++) {
            var it = p.item(i);
            var o = { index: i, id: it.id, name: it.name, type: AEB.itemType(it),
                      folder: it.parentFolder ? it.parentFolder.name : null };
            if (it instanceof CompItem) { o.width = it.width; o.height = it.height;
                o.duration = it.duration; o.fps = it.frameRate; o.numLayers = it.numLayers; }
            if (it instanceof FootageItem && it.file) o.file = it.file.fsName;
            items.push(o);
        }
        return { project: p.file ? p.file.fsName : null,
                 activeItem: p.activeItem ? p.activeItem.name : null, items: items };""")


@mcp.tool()
def list_comps() -> list:
    """List compositions with size, duration and frame rate."""
    return run_jsx("""
        var a = [];
        for (var i = 1; i <= app.project.numItems; i++) {
            var c = app.project.item(i);
            if (c instanceof CompItem) a.push({ index: i, name: c.name, width: c.width, height: c.height,
                duration: c.duration, fps: c.frameRate, numLayers: c.numLayers });
        }
        return a;""")


@mcp.tool()
def comp_info(comp: CompRef = None) -> dict:
    """Describe a comp and its layers (type, timing, parent, effects). comp=None uses the active comp."""
    return run_jsx("""
        var c = AEB.comp(args.comp), layers = [];
        for (var i = 1; i <= c.numLayers; i++) {
            var l = c.layer(i), fx = [];
            var parade = l.property('ADBE Effect Parade');
            if (parade) for (var j = 1; j <= parade.numProperties; j++)
                fx.push({ name: parade.property(j).name, matchName: parade.property(j).matchName });
            var o = { index: i, name: l.name, type: AEB.layerType(l), enabled: l.enabled,
                      inPoint: l.inPoint, outPoint: l.outPoint, startTime: l.startTime,
                      parent: l.parent ? l.parent.name : null, effects: fx };
            if (l instanceof TextLayer) o.text = l.property('Source Text').value.text;
            if (l instanceof AVLayer && l.source) o.source = l.source.name;
            layers.push(o);
        }
        return { name: c.name, width: c.width, height: c.height, duration: c.duration,
                 fps: c.frameRate, bgColor: c.bgColor, workArea: [c.workAreaStart, c.workAreaDuration],
                 layers: layers };""", {"comp": comp})


@mcp.tool()
def create_comp(name: str, width: int = 1920, height: int = 1080, duration: float = 10,
                fps: float = 30, pixel_aspect: float = 1.0,
                bg_color: list[float] | None = None, open_in_viewer: bool = True) -> dict:
    """Create a new composition."""
    return run_jsx("""
        var c = app.project.items.addComp(args.name, args.width, args.height, args.pixel_aspect,
                                          args.duration, args.fps);
        if (args.bg_color) c.bgColor = args.bg_color;
        if (args.open_in_viewer) c.openInViewer();
        return { name: c.name, id: c.id };""",
        dict(name=name, width=width, height=height, duration=duration, fps=fps,
             pixel_aspect=pixel_aspect, bg_color=bg_color, open_in_viewer=open_in_viewer),
        undo="ae-bridge: create comp")


@mcp.tool()
def add_text_layer(text: str, comp: CompRef = None, name: str | None = None,
                   font_size: float | None = None, fill_color: list[float] | None = None,
                   font: str | None = None, justification: str | None = None,
                   position: list[float] | None = None) -> dict:
    """Add a text layer. font is a PostScript name (e.g. 'Arial-BoldMT').
    justification: left | center | right."""
    return run_jsx("""
        var c = AEB.comp(args.comp);
        var l = c.layers.addText(args.text);
        if (args.name) l.name = args.name;
        var sp = l.property('Source Text'), td = sp.value;
        if (args.font_size) td.fontSize = args.font_size;
        if (args.fill_color) { td.applyFill = true; td.fillColor = args.fill_color; }
        if (args.font) td.font = args.font;
        if (args.justification) td.justification = { left: ParagraphJustification.LEFT_JUSTIFY,
            center: ParagraphJustification.CENTER_JUSTIFY, right: ParagraphJustification.RIGHT_JUSTIFY }[args.justification];
        sp.setValue(td);
        if (args.position) l.property('Transform').property('Position').setValue(args.position);
        return { index: l.index, name: l.name };""",
        dict(text=text, comp=comp, name=name, font_size=font_size, fill_color=fill_color,
             font=font, justification=justification, position=position),
        undo="ae-bridge: add text")


@mcp.tool()
def add_solid(comp: CompRef = None, name: str = "Solid", color: list[float] | None = None,
              width: int | None = None, height: int | None = None,
              adjustment: bool = False) -> dict:
    """Add a solid layer (comp size by default). adjustment=True makes it an adjustment layer."""
    return run_jsx("""
        var c = AEB.comp(args.comp);
        var l = c.layers.addSolid(args.color || [0, 0, 0], args.name, args.width || c.width,
                                  args.height || c.height, c.pixelAspect, c.duration);
        if (args.adjustment) l.adjustmentLayer = true;
        return { index: l.index, name: l.name };""",
        dict(comp=comp, name=name, color=color, width=width, height=height, adjustment=adjustment),
        undo="ae-bridge: add solid")


@mcp.tool()
def add_null(comp: CompRef = None, name: str = "Null") -> dict:
    """Add a null object layer."""
    return run_jsx("""
        var c = AEB.comp(args.comp), l = c.layers.addNull(c.duration);
        l.name = args.name; return { index: l.index, name: l.name };""",
        dict(comp=comp, name=name), undo="ae-bridge: add null")


@mcp.tool()
def add_item_to_comp(item: str | int, comp: CompRef = None, start_time: float | None = None) -> dict:
    """Place a project item (footage or comp, by name or index) into a comp as a new layer."""
    return run_jsx("""
        var c = AEB.comp(args.comp), it = AEB.item(args.item), l = c.layers.add(it);
        if (args.start_time !== null) l.startTime = args.start_time;
        return { index: l.index, name: l.name };""",
        dict(item=item, comp=comp, start_time=start_time), undo="ae-bridge: add layer")


@mcp.tool()
def import_file(path: str, as_sequence: bool = False, as_comp: bool = False) -> dict:
    """Import a file into the project. as_sequence for image sequences; as_comp for layered PSD/AI."""
    return run_jsx("""
        var f = new File(args.path);
        if (!f.exists) throw new Error('File not found: ' + args.path);
        var io = new ImportOptions(f);
        if (args.as_sequence) io.sequence = true;
        if (args.as_comp && io.canImportAs(ImportAsType.COMP)) io.importAs = ImportAsType.COMP;
        var it = app.project.importFile(io);
        var r = { name: it.name, id: it.id, type: AEB.itemType(it) };
        if (it instanceof CompItem) { r.layers = [];
            for (var i = 1; i <= it.numLayers; i++) r.layers.push(it.layer(i).name); }
        return r;""",
        dict(path=str(Path(path)), as_sequence=as_sequence, as_comp=as_comp), undo="ae-bridge: import")


@mcp.tool()
def convert_to_shapes(comp: CompRef = None, layers: list[LayerRef] | None = None,
                      keep_original: bool = False, rename: bool = True) -> dict:
    """Convert Illustrator/EPS/PDF footage layers into editable shape layers
    (AE's 'Create Shapes from Vector Layer'). layers=None converts every vector layer in the comp.
    By default the original vector layer is deleted and the shape layer takes its name, so
    existing layer references keep working. keep_original=True leaves the original (AE turns
    its video off) and names the new layer '<name> Outlines'."""
    return run_jsx("""
        var c = AEB.comp(args.comp);
        var isVector = function (l) {
            if (!(l instanceof AVLayer) || !l.source || !(l.source instanceof FootageItem)) return false;
            var f = l.source.file; return !!(f && /\\.(ai|eps|pdf)$/i.test(f.name));
        };
        var targets = [];
        if (args.layers) {
            for (var i = 0; i < args.layers.length; i++) {
                var l = AEB.layer(c, args.layers[i]);
                if (!isVector(l)) throw new Error('Layer "' + l.name + '" is not an Illustrator/EPS/PDF layer');
                targets.push(l);
            }
        } else {
            for (var j = 1; j <= c.numLayers; j++) if (isVector(c.layer(j))) targets.push(c.layer(j));
        }
        if (!targets.length) throw new Error('No Illustrator/EPS/PDF layers found in comp ' + c.name);

        var cmd = app.findMenuCommandId('Create Shapes from Vector Layer');
        if (!cmd) cmd = 3973;   // English-independent fallback id
        c.openInViewer();

        var results = [], skipped = [];
        for (var t = 0; t < targets.length; t++) {
            var orig = targets[t], origName = orig.name;
            if (orig.locked) { skipped.push({ layer: origName, reason: 'locked' }); continue; }
            for (var s = 1; s <= c.numLayers; s++) c.layer(s).selected = false;
            orig.selected = true;
            var before = c.numLayers;
            app.executeCommand(cmd);
            if (c.numLayers !== before + 1) { skipped.push({ layer: origName, reason: 'AE created no shape layer' }); continue; }
            var shape = c.layer(orig.index - 1);
            if (!(shape instanceof ShapeLayer)) { skipped.push({ layer: origName, reason: 'unexpected result layer' }); continue; }
            if (!args.keep_original) { orig.remove(); if (args.rename) shape.name = origName; }
            var contents = shape.property('ADBE Root Vectors Group'), groups = [];
            for (var g = 1; g <= contents.numProperties; g++) groups.push(contents.property(g).name);
            results.push({ from: origName, layer: shape.name, index: shape.index, groups: groups });
        }
        for (var u = 1; u <= c.numLayers; u++) c.layer(u).selected = false;
        return { comp: c.name, converted: results, skipped: skipped };""",
        dict(comp=comp, layers=layers, keep_original=keep_original, rename=rename),
        undo="ae-bridge: convert to shapes", timeout=180)


@mcp.tool()
def get_property(layer: LayerRef, property: str, comp: CompRef = None,
                 time: float | None = None) -> dict:
    """Read a property's value (at `time`, default current time), keyframes and expression."""
    return run_jsx("""
        var c = AEB.comp(args.comp), p = AEB.prop(AEB.layer(c, args.layer), args.property);
        if (p.propertyType !== PropertyType.PROPERTY) {
            var kids = []; for (var i = 1; i <= p.numProperties; i++)
                kids.push({ name: p.property(i).name, matchName: p.property(i).matchName });
            return { group: p.name, children: kids };
        }
        var t = args.time !== null ? args.time : c.time, keys = [];
        for (var k = 1; k <= p.numKeys; k++) keys.push({ time: p.keyTime(k), value: p.keyValue(k) });
        return { name: p.name, matchName: p.matchName, value: p.valueAtTime(t, false),
                 keyframes: keys, expression: p.canSetExpression ? p.expression : null };""",
        dict(layer=layer, property=property, comp=comp, time=time))


@mcp.tool()
def set_property(layer: LayerRef, property: str, value: Any, comp: CompRef = None,
                 time: float | None = None) -> dict:
    """Set a property value. With `time`, sets (or adds) a keyframe at that time instead."""
    return run_jsx("""
        var c = AEB.comp(args.comp), p = AEB.prop(AEB.layer(c, args.layer), args.property);
        if (args.time !== null) p.setValueAtTime(args.time, args.value);
        else if (p.numKeys > 0) throw new Error('Property has keyframes; pass time= to set a keyframe');
        else p.setValue(args.value);
        return { ok: true };""",
        dict(layer=layer, property=property, value=value, comp=comp, time=time),
        undo="ae-bridge: set property")


@mcp.tool()
def set_keyframes(layer: LayerRef, property: str, keyframes: list[dict], comp: CompRef = None,
                  ease: str = "linear", clear_existing: bool = False) -> dict:
    """Set keyframes: keyframes=[{"time": 0, "value": [960,540]}, ...].
    ease: linear | ease (easy ease, 33%) | hold. A per-key "ease" overrides it."""
    return run_jsx("""
        var c = AEB.comp(args.comp), p = AEB.prop(AEB.layer(c, args.layer), args.property);
        if (args.clear_existing) while (p.numKeys > 0) p.removeKey(1);
        var vt = p.propertyValueType;
        var spatial = (vt === PropertyValueType.TwoD_SPATIAL || vt === PropertyValueType.ThreeD_SPATIAL);
        var added = [];
        for (var i = 0; i < args.keyframes.length; i++) {
            var kf = args.keyframes[i], idx = p.addKey(kf.time);
            p.setValueAtKey(idx, kf.value);
            var mode = kf.ease || args.ease;
            if (mode === 'hold') {
                p.setInterpolationTypeAtKey(idx, KeyframeInterpolationType.HOLD, KeyframeInterpolationType.HOLD);
            } else if (mode === 'ease') {
                var n = spatial ? 1 : (kf.value instanceof Array ? kf.value.length : 1);
                var e = []; for (var d = 0; d < n; d++) e.push(new KeyframeEase(0, 33.33));
                p.setTemporalEaseAtKey(idx, e, e);
            } else {
                p.setInterpolationTypeAtKey(idx, KeyframeInterpolationType.LINEAR, KeyframeInterpolationType.LINEAR);
            }
            added.push(kf.time);
        }
        return { property: p.name, numKeys: p.numKeys, added: added };""",
        dict(layer=layer, property=property, keyframes=keyframes, comp=comp, ease=ease,
             clear_existing=clear_existing),
        undo="ae-bridge: keyframes")


@mcp.tool()
def set_expression(layer: LayerRef, property: str, expression: str, comp: CompRef = None) -> dict:
    """Set (or clear with '') an expression on a property. Returns any expression error AE reports."""
    return run_jsx("""
        var c = AEB.comp(args.comp), p = AEB.prop(AEB.layer(c, args.layer), args.property);
        if (!p.canSetExpression) throw new Error('Property cannot take an expression: ' + p.name);
        p.expression = args.expression;
        return { enabled: p.expressionEnabled, error: p.expressionError || null };""",
        dict(layer=layer, property=property, expression=expression, comp=comp),
        undo="ae-bridge: expression")


@mcp.tool()
def add_effect(layer: LayerRef, effect: str, comp: CompRef = None,
               params: dict[str, Any] | None = None) -> dict:
    """Add an effect by display or match name (e.g. 'Gaussian Blur' or 'ADBE Gaussian Blur 2'),
    optionally setting params by name: {"Blurriness": 20}."""
    return run_jsx("""
        var c = AEB.comp(args.comp), l = AEB.layer(c, args.layer);
        var parade = l.property('ADBE Effect Parade');
        if (!parade.canAddProperty(args.effect)) throw new Error('Cannot add effect: ' + args.effect);
        var fx = parade.addProperty(args.effect), set = [];
        if (args.params) for (var k in args.params) if (args.params.hasOwnProperty(k)) {
            var pp = fx.property(k);
            if (!pp) throw new Error('Effect param not found: ' + k);
            pp.setValue(args.params[k]); set.push(k);
        }
        var names = []; for (var i = 1; i <= fx.numProperties; i++) names.push(fx.property(i).name);
        return { effect: fx.name, matchName: fx.matchName, set: set, params: names };""",
        dict(layer=layer, effect=effect, comp=comp, params=params), undo="ae-bridge: add effect")


@mcp.tool()
def layer_update(layer: LayerRef, comp: CompRef = None, name: str | None = None,
                 in_point: float | None = None, out_point: float | None = None,
                 start_time: float | None = None, enabled: bool | None = None,
                 parent: LayerRef | None = None, move_to_index: int | None = None,
                 delete: bool = False) -> dict:
    """Change layer basics: rename, trim, shift, toggle, parent (use '' to unparent), reorder or delete."""
    return run_jsx("""
        var c = AEB.comp(args.comp), l = AEB.layer(c, args.layer);
        if (args['delete']) { var n = l.name; l.remove(); return { deleted: n }; }
        if (args.name !== null) l.name = args.name;
        if (args.start_time !== null) l.startTime = args.start_time;
        if (args.in_point !== null) l.inPoint = args.in_point;
        if (args.out_point !== null) l.outPoint = args.out_point;
        if (args.enabled !== null) l.enabled = args.enabled;
        if (args.parent !== null) l.parent = (args.parent === '') ? null : AEB.layer(c, args.parent);
        if (args.move_to_index !== null) l.moveTo(args.move_to_index);
        return { index: l.index, name: l.name, inPoint: l.inPoint, outPoint: l.outPoint };""",
        dict(layer=layer, comp=comp, name=name, in_point=in_point, out_point=out_point,
             start_time=start_time, enabled=enabled, parent=parent, move_to_index=move_to_index,
             delete=delete),
        undo="ae-bridge: layer update")


@mcp.tool()
def render_frame(output_png: str, comp: CompRef = None, time: float | None = None) -> dict:
    """Save one frame of a comp to a PNG (for previewing the result). Returns the file path."""
    out = Path(output_png)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    run_jsx("""
        var c = AEB.comp(args.comp), t = args.time !== null ? args.time : c.time;
        c.saveFrameToPng(t, new File(args.path));
        return true;""", dict(comp=comp, time=time, path=str(out)), timeout=120)
    deadline = time_mod.monotonic() + 30
    while not out.exists() or out.stat().st_size == 0:
        if time_mod.monotonic() > deadline:
            raise AEError("AE did not write the frame within 30s")
        time_mod.sleep(0.1)
    return {"path": str(out)}


@mcp.tool()
def render(comp: CompRef, output_path: str, output_template: str | None = None,
           render_template: str | None = None, start: bool = True,
           timeout: float = 3600) -> dict:
    """Add a comp to the render queue with an output file, then (start=True) render it.
    AE is blocked while rendering. Templates are names from AE's output module / render settings lists."""
    return run_jsx("""
        var c = AEB.comp(args.comp), rq = app.project.renderQueue, item = rq.items.add(c);
        if (args.render_template) item.applyTemplate(args.render_template);
        var om = item.outputModule(1);
        if (args.output_template) om.applyTemplate(args.output_template);
        om.file = new File(args.output_path);
        if (args.start) { rq.render(); }
        return { queued: true, rendered: args.start, file: om.file.fsName, status: String(item.status) };""",
        dict(comp=comp, output_path=str(Path(output_path)), output_template=output_template,
             render_template=render_template, start=start), timeout=timeout)


@mcp.tool()
def save_project(path: str | None = None) -> dict:
    """Save the project (to `path` if given, i.e. Save As)."""
    return run_jsx("""
        if (args.path) app.project.save(new File(args.path));
        else if (app.project.file) app.project.save();
        else throw new Error('Project has never been saved; pass path');
        return { project: app.project.file.fsName };""", {"path": path})


@mcp.tool()
def open_project(path: str, save_current: bool = True) -> dict:
    """Open a .aep. With save_current, the current project is saved first if it has a file
    (otherwise AE may show a save prompt and the call times out)."""
    return run_jsx("""
        var f = new File(args.path);
        if (!f.exists) throw new Error('File not found: ' + args.path);
        if (args.save_current && app.project.file) app.project.save();
        app.open(f);
        return { project: app.project.file.fsName };""",
        {"path": str(Path(path)), "save_current": save_current}, timeout=180)




def serve() -> None:
    mcp.run()
