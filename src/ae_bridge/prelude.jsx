// ae-bridge runtime helpers. Prepended to every job. ExtendScript (ES3) only.
var AEB = {};

AEB.q = function (s) {
    s = String(s);
    var out = '"';
    for (var i = 0; i < s.length; i++) {
        var c = s.charAt(i), code = s.charCodeAt(i);
        if (c === '"') out += '\\"';
        else if (c === '\\') out += '\\\\';
        else if (c === '\n') out += '\\n';
        else if (c === '\r') out += '\\r';
        else if (c === '\t') out += '\\t';
        else if (code < 0x20 || code === 0x2028 || code === 0x2029) {
            var h = code.toString(16);
            while (h.length < 4) h = '0' + h;
            out += '\\u' + h;
        } else out += c;
    }
    return out + '"';
};

AEB.json = function (v, depth) {
    depth = depth || 0;
    if (depth > 25) return '"<max depth>"';
    if (v === null || v === undefined) return 'null';
    var t = typeof v;
    if (t === 'number') return isFinite(v) ? String(v) : 'null';
    if (t === 'boolean') return String(v);
    if (t === 'string') return AEB.q(v);
    if (t === 'function') return 'null';
    if (v instanceof Array) {
        var a = [];
        for (var i = 0; i < v.length; i++) a.push(AEB.json(v[i], depth + 1));
        return '[' + a.join(',') + ']';
    }
    if (typeof TextDocument !== 'undefined' && v instanceof TextDocument) return AEB.q(v.text);
    if (v instanceof File || v instanceof Folder) return AEB.q(v.fsName);
    if (v.constructor === Object) {
        var parts = [];
        for (var k in v) {
            if (v.hasOwnProperty(k)) parts.push(AEB.q(k) + ':' + AEB.json(v[k], depth + 1));
        }
        return '{' + parts.join(',') + '}';
    }
    return AEB.q(String(v));
};

// comp: name (string), project item index (number), or null/undefined for the active comp.
AEB.comp = function (id) {
    var proj = app.project;
    if (id === null || id === undefined || id === '') {
        if (proj.activeItem instanceof CompItem) return proj.activeItem;
        throw new Error('No comp given and no active comp');
    }
    if (typeof id === 'number') {
        var it = proj.item(id);
        if (it instanceof CompItem) return it;
        throw new Error('Project item ' + id + ' is not a comp');
    }
    for (var i = 1; i <= proj.numItems; i++) {
        var c = proj.item(i);
        if (c instanceof CompItem && c.name === id) return c;
    }
    throw new Error('Comp not found: ' + id);
};

// item: name or index of any project item.
AEB.item = function (id) {
    var proj = app.project;
    if (typeof id === 'number') return proj.item(id);
    for (var i = 1; i <= proj.numItems; i++) if (proj.item(i).name === id) return proj.item(i);
    throw new Error('Project item not found: ' + id);
};

// layer: name or 1-based index.
AEB.layer = function (comp, id) {
    var l = (typeof id === 'number') ? comp.layer(id) : comp.layer(String(id));
    if (!l) throw new Error('Layer not found: ' + id + ' in comp ' + comp.name);
    return l;
};

// property path like "Transform/Position" or "ADBE Effect Parade/Gaussian Blur/Blurriness".
AEB.prop = function (layer, path) {
    var parts = String(path).split('/');
    var p = layer;
    for (var i = 0; i < parts.length; i++) {
        var next = p.property(parts[i]);
        if (!next) throw new Error('Property not found: "' + parts[i] + '" in path ' + path);
        p = next;
    }
    return p;
};

AEB.layerType = function (l) {
    if (l instanceof TextLayer) return 'text';
    if (l instanceof ShapeLayer) return 'shape';
    if (l instanceof CameraLayer) return 'camera';
    if (l instanceof LightLayer) return 'light';
    if (l instanceof AVLayer) {
        if (l.nullLayer) return 'null';
        if (l.source instanceof CompItem) return 'precomp';
        if (l.source && l.source.mainSource instanceof SolidSource) return 'solid';
        return 'footage';
    }
    return 'unknown';
};

AEB.itemType = function (it) {
    if (it instanceof CompItem) return 'comp';
    if (it instanceof FolderItem) return 'folder';
    if (it instanceof FootageItem) return 'footage';
    return 'item';
};
