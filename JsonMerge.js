/*
 * JsonMerge.js — browser port of example_python/JsonMerge.py
 * Field-level, timestamp-based JSON conflict resolution.
 * Used by ../index.html (DaisyUI demo).
 */
(function (root) {
  "use strict";

  const SCHEMA_VERSION = 2;
  const RESERVED_KEYS = new Set(["_his", "upDtEp", "crDtEp", "schemaV", "docType", "upDt", "crDt"]);
  const PATH_TOKEN = /([^.\[\]]+)|\[(\d+)\]/g;

  // ---------- time ----------
  function nowEpoch() { return Math.floor(Date.now() / 1000); }
  function epochToIso(ep) { return new Date(ep * 1000).toISOString().replace(/\.\d{3}Z$/, "Z"); }
  function isoToEpoch(iso) { return Math.floor(new Date(iso).getTime() / 1000); }

  // ---------- path ----------
  function parsePath(path) {
    if (!path) return [];
    const out = [];
    let m;
    PATH_TOKEN.lastIndex = 0;
    while ((m = PATH_TOKEN.exec(path)) !== null) {
      if (m[1] !== undefined) out.push(m[1]);
      else out.push(parseInt(m[2], 10));
    }
    return out;
  }
  function topSegment(path) {
    let end = path.length;
    const i = path.indexOf(".");
    if (i >= 0 && i < end) end = i;
    const j = path.indexOf("[");
    if (j >= 0 && j < end) end = j;
    return path.slice(0, end);
  }
  function isQtyPath(p) { return p === "qty" || p.endsWith(".qty"); }

  function getAtPath(doc, path) {
    let node = doc;
    for (const seg of parsePath(path)) node = node[seg];
    return node;
  }
  function hasPath(doc, path) {
    try { getAtPath(doc, path); return true; } catch (e) { return false; }
  }
  function setAtPath(doc, path, value) {
    const segs = parsePath(path);
    if (!segs.length) throw new Error("empty path");
    let node = doc;
    for (let i = 0; i < segs.length - 1; i++) {
      const seg = segs[i], nxt = segs[i + 1];
      if (typeof seg === "number") {
        while (node.length <= seg) node.push(typeof nxt === "string" ? {} : []);
        if (node[seg] == null) node[seg] = typeof nxt === "string" ? {} : [];
        node = node[seg];
      } else {
        if (!(seg in node) || node[seg] == null) node[seg] = typeof nxt === "string" ? {} : [];
        node = node[seg];
      }
    }
    const last = segs[segs.length - 1];
    if (typeof last === "number") {
      while (node.length <= last) node.push(null);
      node[last] = value;
    } else node[last] = value;
  }
  function delAtPath(doc, path) {
    const segs = parsePath(path);
    if (!segs.length) return;
    let node = doc;
    for (let i = 0; i < segs.length - 1; i++) {
      if (node == null) return;
      node = node[segs[i]];
    }
    if (node == null) return;
    const last = segs[segs.length - 1];
    if (Array.isArray(node) && typeof last === "number") node.splice(last, 1);
    else delete node[last];
  }

  function flatten(doc, skipSet) {
    skipSet = skipSet || new Set();
    const out = {};
    function walk(node, p) {
      if (node && typeof node === "object" && !Array.isArray(node)) {
        const keys = Object.keys(node);
        if (!keys.length) { out[p] = {}; return; }
        for (const k of keys) {
          if (!p && skipSet.has(k)) continue;
          walk(node[k], p ? `${p}.${k}` : k);
        }
      } else if (Array.isArray(node)) {
        if (!node.length) { out[p] = []; return; }
        node.forEach((v, i) => walk(v, `${p}[${i}]`));
      } else {
        out[p] = node;
      }
    }
    walk(doc, "");
    return out;
  }
  function unflatten(flat) {
    let root = {};
    const paths = Object.keys(flat);
    if (paths.length && typeof parsePath(paths[0])[0] === "number") root = [];
    for (const p of paths) {
      if (p === "") return flat[p];
      setAtPath(root, p, flat[p]);
    }
    return root;
  }

  // ---------- hash (short SHA-256-ish; uses simple FNV-1a + length for portability without subtle crypto) ----------
  // Note: this is a stable 8-char hex hash but NOT cryptographic. Mirrors only the "drift signal" intent of the Python port.
  function valueHash(value) {
    const j = JSON.stringify(sortKeysDeep(value));
    let h = 0x811c9dc5;
    for (let i = 0; i < j.length; i++) {
      h ^= j.charCodeAt(i);
      h = (h + ((h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24))) >>> 0;
    }
    let h2 = 0xdeadbeef ^ j.length;
    for (let i = 0; i < j.length; i++) {
      h2 = Math.imul(h2 ^ j.charCodeAt(i), 2654435761) >>> 0;
    }
    return (("00000000" + h.toString(16)).slice(-4)) + (("00000000" + h2.toString(16)).slice(-4));
  }
  function sortKeysDeep(v) {
    if (Array.isArray(v)) return v.map(sortKeysDeep);
    if (v && typeof v === "object") {
      const out = {};
      Object.keys(v).sort().forEach(k => { out[k] = sortKeysDeep(v[k]); });
      return out;
    }
    return v;
  }
  function hashDoc(doc) {
    const clean = {};
    for (const k of Object.keys(doc)) if (!RESERVED_KEYS.has(k)) clean[k] = doc[k];
    return valueHash(clean);
  }

  function deepCopy(v) { return JSON.parse(JSON.stringify(v)); }

  // ---------- JSON Pointer <-> dotted-path ----------
  function escapePtr(s) { return String(s).replace(/~/g, "~0").replace(/\//g, "~1"); }
  function unescapePtr(s) { return s.replace(/~1/g, "/").replace(/~0/g, "~"); }
  function toPointer(dotted) {
    const segs = parsePath(dotted);
    return "/" + segs.map(s => escapePtr(s)).join("/");
  }
  function fromPointer(ptr) {
    if (!ptr || ptr === "/") return "";
    const parts = ptr.replace(/^\//, "").split("/").map(unescapePtr);
    let out = "";
    for (const p of parts) {
      if (/^\d+$/.test(p)) out += `[${p}]`;
      else out = out ? `${out}.${p}` : p;
    }
    return out;
  }

  // ---------- class ----------
  class JSONMERGE {
    constructor(config) {
      this.noCheck = new Set(RESERVED_KEYS);
      this.debug = false;
      this.addCrEp = true;
      this.addCrIso = false;
      this.addUpIso = false;
      this.addHashes = true;
      this.qtyMath = true;
      this.schema_version = SCHEMA_VERSION;
      if (config) for (const k of Object.keys(config)) if (k in this) this[k] = config[k];
    }

    isManaged(doc) { return doc && typeof doc === "object" && "_his" in doc && "upDtEp" in doc; }

    makeNewDoc(doc) {
      const ep = nowEpoch();
      const flat = flatten(doc, this.noCheck);
      const history = {};
      for (const path of Object.keys(flat)) {
        const entry = { v: flat[path], t: ep };
        if (this.addHashes) entry.h = valueHash(flat[path]);
        history[path] = entry;
      }
      doc._his = history;
      doc.upDtEp = ep;
      doc.schemaV = this.schema_version;
      if (this.addCrEp) doc.crDtEp = ep;
      if (this.addCrIso) doc.crDt = epochToIso(ep);
      if (this.addUpIso) doc.upDt = epochToIso(ep);
      return doc;
    }
    make_new_doc(d) { return this.makeNewDoc(d); }

    _resolveQty(path, val) {
      if (!this.qtyMath || !isQtyPath(path) || typeof val !== "number") return val;
      return Math.max(0, val);
    }
    _clampQty(doc) {
      if (!this.qtyMath) return;
      const cb = doc._his || {};
      for (const path of Object.keys(cb)) {
        if (!isQtyPath(path)) continue;
        const rec = cb[path];
        if (typeof rec.v === "number" && rec.v < 0) {
          setAtPath(doc, path, 0);
          rec.v = 0;
          if ("h" in rec) rec.h = valueHash(0);
        }
      }
    }
    _stampChange(doc, cb, path, val, ep, prehash) {
      setAtPath(doc, path, val);
      const rec = { v: val, t: ep };
      if (this.addHashes) rec.h = prehash != null ? prehash : valueHash(val);
      cb[path] = rec;
    }

    updateDoc(doc, changes) {
      if (!changes) return doc;
      let flatChanges = {};
      if (Array.isArray(changes)) {
        for (const item of changes) {
          if (!item || typeof item !== "object") continue;
          const keys = Object.keys(item);
          if (keys.length === 1) {
            const k = keys[0], v = item[k];
            if (!(v && typeof v === "object")) { flatChanges[k] = v; continue; }
          }
          Object.assign(flatChanges, flatten(item, this.noCheck));
        }
      } else {
        flatChanges = flatten(changes, this.noCheck);
      }
      if (!doc._his) doc._his = {};
      const cb = doc._his;
      let ep = null;
      for (const path of Object.keys(flatChanges)) {
        if (this.noCheck.has(topSegment(path))) continue;
        const newVal = flatChanges[path];
        const old = cb[path];
        if (old && JSON.stringify(old.v) === JSON.stringify(newVal)) continue;
        if (ep == null) ep = nowEpoch();
        this._stampChange(doc, cb, path, newVal, ep);
      }
      if (ep != null) {
        doc.upDtEp = ep;
        if (this.addUpIso) doc.upDt = epochToIso(ep);
      }
      return doc;
    }
    update_doc(d, c) { return this.updateDoc(d, c); }

    diffDocs(a, b) {
      const fa = flatten(a, this.noCheck);
      const fb = flatten(b, this.noCheck);
      const ops = [];
      for (const path of Object.keys(fb)) {
        if (!(path in fa)) ops.push({ op: "add", path: toPointer(path), value: fb[path] });
        else if (JSON.stringify(fa[path]) !== JSON.stringify(fb[path]))
          ops.push({ op: "replace", path: toPointer(path), value: fb[path] });
      }
      for (const path of Object.keys(fa)) {
        if (!(path in fb)) ops.push({ op: "remove", path: toPointer(path) });
      }
      return ops;
    }
    diff_docs(a, b) { return this.diffDocs(a, b); }

    patchDoc(doc, ops) {
      const changes = [];
      const removals = [];
      for (const op of ops) {
        const ptr = fromPointer(op.path || "");
        if (op.op === "add" || op.op === "replace") changes.push({ [ptr]: op.value });
        else if (op.op === "remove") removals.push(ptr);
      }
      if (changes.length) this.updateDoc(doc, changes);
      for (const ptr of removals) {
        delAtPath(doc, ptr);
        if (doc._his) delete doc._his[ptr];
        doc.upDtEp = nowEpoch();
      }
      return doc;
    }
    patch_doc(d, o) { return this.patchDoc(d, o); }

    _ensureManaged(doc) { return this.isManaged(doc) ? doc : this.makeNewDoc(deepCopy(doc)); }

    mergeDocReq(doc1, doc2) {
      doc1 = this._ensureManaged(doc1);
      doc2 = this._ensureManaged(doc2);
      const cb1 = doc1._his, cb2 = doc2._his;
      const small = Object.keys(cb2).length <= Object.keys(cb1).length ? cb2 : cb1;
      let ep = null;
      for (const path of Object.keys(small)) {
        const r1 = cb1[path], r2 = cb2[path];
        if (!r1 || !r2) continue;
        if (JSON.stringify(r1.v) === JSON.stringify(r2.v)) continue;
        if ((r2.t || 0) <= (r1.t || 0)) continue;
        const val = this._resolveQty(path, r2.v);
        if (ep == null) ep = nowEpoch();
        const prehash = (val === r2.v) ? r2.h : undefined;
        this._stampChange(doc1, cb1, path, val, ep, prehash);
      }
      if (ep != null) {
        doc1.upDtEp = ep;
        if (this.addUpIso) doc1.upDt = epochToIso(ep);
      }
      this._clampQty(doc1);
      return doc1;
    }
    merge_doc_request(a, b) { return this.mergeDocReq(a, b); }

    blindMerge(doc1, doc2) {
      doc1 = this._ensureManaged(doc1);
      doc2 = this._ensureManaged(doc2);
      let base, other;
      if ((doc2.upDtEp || 0) > (doc1.upDtEp || 0)) { base = deepCopy(doc2); other = doc1; }
      else { base = deepCopy(doc1); other = doc2; }
      const cbBase = base._his, cbOther = other._his;
      let ep = null;
      for (const path of Object.keys(cbOther)) {
        const rO = cbOther[path];
        const rB = cbBase[path];
        let val;
        if (!rB) val = this._resolveQty(path, rO.v);
        else {
          if (JSON.stringify(rB.v) === JSON.stringify(rO.v)) continue;
          if ((rO.t || 0) <= (rB.t || 0)) continue;
          val = this._resolveQty(path, rO.v);
        }
        if (ep == null) ep = nowEpoch();
        const prehash = (val === rO.v) ? rO.h : undefined;
        this._stampChange(base, cbBase, path, val, ep, prehash);
      }
      if (ep != null) {
        base.upDtEp = ep;
        if (this.addUpIso) base.upDt = epochToIso(ep);
      }
      this._clampQty(base);
      return base;
    }
    blind_merge(a, b) { return this.blindMerge(a, b); }

    threeWayMerge(base, ours, theirs) {
      base = this._ensureManaged(base);
      ours = this._ensureManaged(ours);
      theirs = this._ensureManaged(theirs);
      const merged = deepCopy(ours);
      const cbB = base._his, cbO = ours._his, cbT = theirs._his;
      const conflicts = [];
      const all = new Set([...Object.keys(cbO), ...Object.keys(cbT), ...Object.keys(cbB)]);
      const changes = [];
      for (const path of all) {
        const b = cbB[path] ? cbB[path].v : null;
        const o = cbO[path] ? cbO[path].v : b;
        const t = cbT[path] ? cbT[path].v : b;
        const eq = (x, y) => JSON.stringify(x) === JSON.stringify(y);
        if (eq(o, t)) continue;
        if (eq(o, b) && !eq(t, b)) { changes.push({ [path]: t }); }
        else if (eq(t, b) && !eq(o, b)) { continue; }
        else {
          conflicts.push(path);
          const oRec = cbO[path] || { v: o, t: 0 };
          const tRec = cbT[path] || { v: t, t: 0 };
          const newer = (tRec.t || 0) > (oRec.t || 0) ? tRec : oRec;
          changes.push({ [path]: this._resolveQty(path, newer.v) });
        }
      }
      if (changes.length) this.updateDoc(merged, changes);
      this._clampQty(merged);
      return { merged, conflicts };
    }
    three_way_merge(b, o, t) { return this.threeWayMerge(b, o, t); }

    historyIso(doc) {
      const out = {};
      const cb = doc._his || {};
      for (const path of Object.keys(cb)) {
        const r = Object.assign({}, cb[path]);
        if ("t" in r) r.tIso = epochToIso(r.t);
        out[path] = r;
      }
      return out;
    }
    history_iso(d) { return this.historyIso(d); }

    listChangesSince(doc, sinceEp) {
      const out = [];
      const cb = doc._his || {};
      for (const path of Object.keys(cb)) {
        if ((cb[path].t || 0) >= sinceEp) out.push({ path, v: cb[path].v, t: cb[path].t });
      }
      return out.sort((a, b) => b.t - a.t);
    }

    validate(doc) {
      const issues = [];
      if (!this.isManaged(doc)) return ["doc is not managed (missing _his/upDtEp)"];
      const flat = flatten(doc, this.noCheck);
      const cb = doc._his;
      for (const path of Object.keys(flat)) {
        const rec = cb[path];
        if (!rec) { issues.push(`untracked field: ${path}`); continue; }
        if (JSON.stringify(rec.v) !== JSON.stringify(flat[path]))
          issues.push(`_his/value drift at ${path}`);
        if ("h" in rec && rec.h !== valueHash(flat[path]))
          issues.push(`hash mismatch at ${path} (tampered?)`);
      }
      for (const path of Object.keys(cb)) {
        if (!(path in flat)) issues.push(`_his references missing path: ${path}`);
      }
      return issues;
    }
  }

  const api = {
    JSONMERGE,
    nowEpoch, epochToIso, isoToEpoch,
    parsePath, getAtPath, setAtPath, hasPath, delAtPath,
    flatten, unflatten, valueHash, hashDoc,
    toPointer, fromPointer,
    SCHEMA_VERSION, RESERVED_KEYS
  };
  root.JsonMerge = api;
})(typeof window !== "undefined" ? window : globalThis);
