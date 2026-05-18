/*
 * JsonMerge.js — browser port of example_python/JsonMerge.py
 * Field-level, timestamp-based JSON conflict resolution.
 * Used by ../index.html (DaisyUI demo).
 */
(function (root) {
  "use strict";

  const SCHEMA_VERSION = 3;
  const RESERVED_KEYS = new Set(["_his", "_hisF", "upDtEp", "crDtEp", "schemaV", "docType", "upDt", "crDt"]);
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
        // schemaV-3 / Option A: no redundant `v` in _his — live value lives
        // in the document body at `path` and is fetched on demand.
        const entry = { t: ep };
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
        let v;
        try { v = getAtPath(doc, path); } catch (e) { continue; }
        if (typeof v === "number" && v < 0) {
          setAtPath(doc, path, 0);
          if ("h" in rec) rec.h = valueHash(0);
        }
      }
    }
    _stampChange(doc, cb, path, val, ep, prehash) {
      setAtPath(doc, path, val);
      const rec = { t: ep };
      if (this.addHashes) rec.h = prehash != null ? prehash : valueHash(val);
      cb[path] = rec;
    }

    updateDoc(doc, changes) {
      if (!changes) return doc;
      // Accept any wire form (dict / columnar / cbor) transparently.
      if (doc && doc._hisF != null) {
        const u = unpackHis(doc);
        for (const k of Object.keys(doc)) delete doc[k];
        Object.assign(doc, u);
      }
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
        // schemaV-3: compare against the live value, not _his[path].v
        let cur;
        try { cur = getAtPath(doc, path); } catch (e) { cur = undefined; }
        if (cb[path] && JSON.stringify(cur) === JSON.stringify(newVal)) continue;
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

    _ensureManaged(doc) {
      // Accept dict / columnar / cbor wire forms transparently.
      if (doc && doc._hisF != null) doc = unpackHis(doc);
      return this.isManaged(doc) ? doc : this.makeNewDoc(deepCopy(doc));
    }

    mergeDocReq(doc1, doc2) {
      doc1 = this._ensureManaged(doc1);
      doc2 = this._ensureManaged(doc2);
      const cb1 = doc1._his, cb2 = doc2._his;
      const small = Object.keys(cb2).length <= Object.keys(cb1).length ? cb2 : cb1;
      let ep = null;
      for (const path of Object.keys(small)) {
        const r1 = cb1[path], r2 = cb2[path];
        if (!r1 || !r2) continue;
        if ((r2.t || 0) <= (r1.t || 0)) continue;
        // schemaV-3: hash-equality fast path; fall back to live values.
        if (r1.h != null && r2.h != null && r1.h === r2.h) continue;
        let v1, v2;
        try { v1 = getAtPath(doc1, path); } catch (e) { v1 = undefined; }
        try { v2 = getAtPath(doc2, path); } catch (e) { continue; }
        if (JSON.stringify(v1) === JSON.stringify(v2)) continue;
        const val = this._resolveQty(path, v2);
        if (ep == null) ep = nowEpoch();
        const prehash = (val === v2) ? r2.h : undefined;
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
        let vO;
        try { vO = getAtPath(other, path); } catch (e) { continue; }
        let val;
        if (!rB) val = this._resolveQty(path, vO);
        else {
          if ((rO.t || 0) <= (rB.t || 0)) continue;
          if (rB.h != null && rO.h != null && rB.h === rO.h) continue;
          let vB;
          try { vB = getAtPath(base, path); } catch (e) { vB = undefined; }
          if (JSON.stringify(vB) === JSON.stringify(vO)) continue;
          val = this._resolveQty(path, vO);
        }
        if (ep == null) ep = nowEpoch();
        const prehash = (val === vO) ? rO.h : undefined;
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
      const live = (d, p, fb) => { try { return getAtPath(d, p); } catch (e) { return fb; } };
      for (const path of all) {
        const b = (path in cbB) ? live(base, path, null) : null;
        const o = (path in cbO) ? live(ours, path, b) : b;
        const t = (path in cbT) ? live(theirs, path, b) : b;
        const eq = (x, y) => JSON.stringify(x) === JSON.stringify(y);
        if (eq(o, t)) continue;
        if (eq(o, b) && !eq(t, b)) { changes.push({ [path]: t }); }
        else if (eq(t, b) && !eq(o, b)) { continue; }
        else {
          conflicts.push(path);
          const oRec = cbO[path] || { t: 0 };
          const tRec = cbT[path] || { t: 0 };
          const newerVal = (tRec.t || 0) > (oRec.t || 0) ? t : o;
          changes.push({ [path]: this._resolveQty(path, newerVal) });
        }
      }
      if (changes.length) this.updateDoc(merged, changes);
      this._clampQty(merged);
      return { merged, conflicts };
    }
    three_way_merge(b, o, t) { return this.threeWayMerge(b, o, t); }

    historyIso(doc) {
      if (doc && doc._hisF != null) doc = unpackHis(doc);
      const out = {};
      const cb = doc._his || {};
      for (const path of Object.keys(cb)) {
        const r = Object.assign({}, cb[path]);
        if ("t" in r) r.tIso = epochToIso(r.t);
        try { r.v = getAtPath(doc, path); } catch (e) { /* missing */ }
        out[path] = r;
      }
      return out;
    }
    history_iso(d) { return this.historyIso(d); }

    listChangesSince(doc, sinceEp) {
      if (doc && doc._hisF != null) doc = unpackHis(doc);
      const out = [];
      const cb = doc._his || {};
      for (const path of Object.keys(cb)) {
        if ((cb[path].t || 0) >= sinceEp) {
          let v; try { v = getAtPath(doc, path); } catch (e) { v = null; }
          out.push({ path, v, t: cb[path].t });
        }
      }
      return out.sort((a, b) => b.t - a.t);
    }

    validate(doc) {
      if (doc && doc._hisF != null) doc = unpackHis(doc);
      const issues = [];
      if (!this.isManaged(doc)) return ["doc is not managed (missing _his/upDtEp)"];
      const flat = flatten(doc, this.noCheck);
      const cb = doc._his;
      for (const path of Object.keys(flat)) {
        const rec = cb[path];
        if (!rec) { issues.push(`untracked field: ${path}`); continue; }
        // schemaV-3: only hash-mismatch detects tamper (no `v` to drift)
        if ("h" in rec && rec.h !== valueHash(flat[path]))
          issues.push(`hash mismatch at ${path} (tampered?)`);
      }
      for (const path of Object.keys(cb)) {
        if (!(path in flat)) issues.push(`_his references missing path: ${path}`);
      }
      return issues;
    }
  }

  // ---------------------------------------------------------------------------
  // _his wire-format helpers — Options D + E
  // ---------------------------------------------------------------------------
  // In-memory _his is a dict-of-dicts ({t,h} records). For storage you
  // can opt into a smaller wire layout via packHis() and reverse it with
  // unpackHis(). All library functions auto-unpack on entry, so once
  // you've packed a doc you can hand it back to the lib as-is.
  //
  //   fmt='cols' (Option E):  _his -> {p:[...],t:[...],h:[...]}, _hisF="c"
  //   fmt='cbor' (Option D):  _his -> {d:"<base64>", s:"<sha256>"}, _hisF="b"
  //
  // The CBOR encoder/decoder below is a minimal inline implementation
  // covering exactly the shapes we use (uint, string, array, map). It
  // avoids any external dependency in the browser.

  function _hisPackCols(his) {
    const paths = [], ts = [], hs = [];
    const keys = Object.keys(his);
    const hasH = keys.some(k => "h" in his[k]);
    for (const p of keys) {
      paths.push(p);
      ts.push((his[p].t | 0));
      if (hasH) hs.push(his[p].h || "");
    }
    const out = { p: paths, t: ts };
    if (hasH) out.h = hs;
    return out;
  }
  function _hisUnpackCols(packed) {
    const paths = packed.p || [], ts = packed.t || [], hs = packed.h;
    const out = {};
    for (let i = 0; i < paths.length; i++) {
      const rec = { t: ts[i] | 0 };
      if (hs && i < hs.length && hs[i] !== "") rec.h = hs[i];
      out[paths[i]] = rec;
    }
    return out;
  }

  // --- minimal CBOR (RFC 8949 subset: uint, tstr, array, map) ---
  function _cborEncode(v) {
    const out = [];
    const utf8 = new TextEncoder();
    function head(major, val) {
      if (val < 24) out.push((major << 5) | val);
      else if (val < 256) { out.push((major << 5) | 24); out.push(val); }
      else if (val < 65536) { out.push((major << 5) | 25); out.push((val >> 8) & 0xff, val & 0xff); }
      else { out.push((major << 5) | 26); out.push((val >>> 24) & 0xff, (val >>> 16) & 0xff, (val >>> 8) & 0xff, val & 0xff); }
    }
    function enc(x) {
      if (typeof x === "number" && Number.isInteger(x) && x >= 0) head(0, x);
      else if (typeof x === "string") {
        const bytes = utf8.encode(x);
        head(3, bytes.length);
        for (let i = 0; i < bytes.length; i++) out.push(bytes[i]);
      } else if (Array.isArray(x)) {
        head(4, x.length);
        for (const e of x) enc(e);
      } else if (x && typeof x === "object") {
        const ks = Object.keys(x);
        head(5, ks.length);
        for (const k of ks) { enc(k); enc(x[k]); }
      } else {
        throw new Error("cbor: unsupported value " + typeof x);
      }
    }
    enc(v);
    return new Uint8Array(out);
  }
  function _cborDecode(buf) {
    let i = 0;
    const utf8 = new TextDecoder();
    function readHead() {
      const b = buf[i++];
      const major = b >> 5, info = b & 0x1f;
      let val;
      if (info < 24) val = info;
      else if (info === 24) val = buf[i++];
      else if (info === 25) { val = (buf[i] << 8) | buf[i + 1]; i += 2; }
      else if (info === 26) { val = (buf[i] * 0x1000000) + (buf[i + 1] << 16) + (buf[i + 2] << 8) + buf[i + 3]; i += 4; }
      else throw new Error("cbor: unsupported length info " + info);
      return { major, val };
    }
    function dec() {
      const { major, val } = readHead();
      if (major === 0) return val;
      if (major === 3) { const s = utf8.decode(buf.subarray(i, i + val)); i += val; return s; }
      if (major === 4) { const a = []; for (let k = 0; k < val; k++) a.push(dec()); return a; }
      if (major === 5) { const o = {}; for (let k = 0; k < val; k++) { const key = dec(); o[key] = dec(); } return o; }
      throw new Error("cbor: unsupported major " + major);
    }
    return dec();
  }
  function _bytesToB64(bytes) {
    let s = "";
    for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
    return btoa(s);
  }
  function _b64ToBytes(b64) {
    const s = atob(b64);
    const out = new Uint8Array(s.length);
    for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i);
    return out;
  }
  // Use the same FNV-ish short hash for the integrity field (mirrors valueHash).
  function _bytesHash(bytes) {
    let s = "";
    for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
    return valueHash(s);
  }
  function _hisPackCbor(his) {
    const cols = _hisPackCols(his);
    const bytes = _cborEncode(cols);
    return { d: _bytesToB64(bytes), s: _bytesHash(bytes) };
  }
  function _hisUnpackCbor(packed) {
    const bytes = _b64ToBytes(packed.d);
    if (_bytesHash(bytes) !== packed.s) {
      throw new Error("_his cbor blob hash mismatch (tampered or corrupt)");
    }
    return _hisUnpackCols(_cborDecode(bytes));
  }

  /**
   * packHis(doc, fmt='cols'|'cbor')
   *   Returns a shallow copy of `doc` with `_his` re-encoded into a
   *   smaller wire layout. Sets `_hisF` so the format can be detected.
   *   No-op if `_hisF` is already set to the requested format.
   */
  function packHis(doc, fmt) {
    fmt = fmt || "cols";
    if (fmt !== "cols" && fmt !== "cbor") throw new Error("unknown packHis fmt: " + fmt);
    const out = deepCopy(doc);
    const his = out._his || {};
    // If already packed in some form, normalize first.
    if (out._hisF != null) {
      const tmp = unpackHis(out);
      for (const k of Object.keys(out)) delete out[k];
      Object.assign(out, tmp);
    }
    if (fmt === "cols") {
      out._his = _hisPackCols(out._his || his);
      out._hisF = "c";
    } else {
      out._his = _hisPackCbor(out._his || his);
      out._hisF = "b";
    }
    return out;
  }

  /**
   * unpackHis(doc)
   *   Returns a copy of `doc` with `_his` restored to dict-of-dicts.
   *   No-op when `_hisF` is absent (already unpacked).
   */
  function unpackHis(doc) {
    if (!doc || doc._hisF == null) return doc;
    const out = deepCopy(doc);
    if (out._hisF === "c") out._his = _hisUnpackCols(out._his);
    else if (out._hisF === "b") out._his = _hisUnpackCbor(out._his);
    else throw new Error("unknown _hisF marker: " + out._hisF);
    delete out._hisF;
    return out;
  }

  const api = {
    JSONMERGE,
    nowEpoch, epochToIso, isoToEpoch,
    parsePath, getAtPath, setAtPath, hasPath, delAtPath,
    flatten, unflatten, valueHash, hashDoc,
    toPointer, fromPointer,
    packHis, unpackHis,
    SCHEMA_VERSION, RESERVED_KEYS
  };
  root.JsonMerge = api;
})(typeof window !== "undefined" ? window : globalThis);
