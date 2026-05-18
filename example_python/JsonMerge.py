"""
JsonMerge.py
============

Field-level, timestamp-based conflict resolution for JSON documents.

Storage model (the "_his" sidecar) — schemaV 3
----------------------------------------------
Every managed document carries a top-level bookkeeping object named
``_his``. It maps a **path** (dotted/bracket notation, see below) to a
record describing only the epoch timestamp when the field was last set
and a short content hash for tamper / drift detection. The *value*
itself lives in the user document at ``path`` and is read on demand –
this is the schemaV-3 "Option A" size win:

    {
      "_his": {
        "name":              {"t": 1700000000, "h": "a1b2c3d4"},
        "address.city":      {"t": 1700000000, "h": "..."},
        "tags[0]":           {"t": 1700000000, "h": "..."},
        "lines[2].sku":      {"t": 1700000000, "h": "..."}
      },
      "upDtEp":   1700000000,
      "crDtEp":   1700000000,
      "schemaV":  3
    }

For wire-format size reductions see ``pack_his`` / ``unpack_his`` which
expose two opt-in wire layouts:

* ``'cols'`` – columnar JSON ``{"p":[...], "t":[...], "h":[...]}``
* ``'cbor'`` – the columnar payload encoded as CBOR and base64-wrapped
  with a sha256 integrity hash (requires the ``cbor2`` package).

* Timestamps are stored as **integer Unix epoch seconds** (UTC). Helpers
  ``epoch_to_iso`` / ``iso_to_epoch`` convert to/from ISO-8601 on demand.
* Paths use **dotted + bracket** notation: ``a.b[0].c``. This is converted
  internally to a list of segments.

Public API (snake_case canonical, camelCase aliases kept for back-compat)
-------------------------------------------------------------------------
Time helpers       : now_epoch, now_iso, epoch_to_iso, iso_to_epoch, makeTime
Path helpers       : parse_path, get_at_path, set_at_path, has_path, del_at_path,
                     flatten, unflatten
Hash helpers       : value_hash, hash_doc
Doc lifecycle      : make_new_doc / makeNewDoc
                     update_doc   / updateDoc
                     diff_docs
                     patch_doc                (RFC 6902 JSON Patch)
Merging            : merge_doc_request / mergeDocReq
                     blind_merge       / blindMerge
                     three_way_merge
History / inspect  : history_iso, list_changes_since, is_managed, validate

Reserved (non-tracked) top-level keys
-------------------------------------
``_his``, ``upDtEp``, ``crDtEp``, ``schemaV``, ``docType``. Anything in
``self.noCheck`` is also skipped.

Recommendations / future hooks
------------------------------
* ``hash_doc`` + per-field ``h`` lets you detect silent corruption /
  out-of-band edits that bypass the merger.
* ``three_way_merge`` (base, ours, theirs) is the building block for
  CRDT-like or Git-style flows when you can persist a "base" snapshot.
* ``patch_doc`` accepts RFC 6902 JSON Patch ops, so you can import diffs
  produced by tools like ``jsondiffpatch`` or ``deepdiff``.
* Vector-clock style metadata could be added by extending each _his
  record with a ``clk`` dict ``{nodeId: counter}`` — the merger already
  isolates the "is newer?" decision in one place (``_pick_newer``).
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 3

# Top-level keys that are part of the bookkeeping itself and must never
# be tracked as user fields.
RESERVED_KEYS = {"_his", "_hisF", "upDtEp", "crDtEp", "schemaV", "docType"}

_PATH_TOKEN = re.compile(r"([^.\[\]]+)|\[(\d+)\]")

# Singleton sentinel for "key absent"; lets diff_docs avoid double-lookups.
_MISSING: Any = object()


def _top_segment(path: str) -> str:
    """Return the first dotted/bracket segment of a path string.

    Cheap O(len) string scan; avoids the cost of ``parse_path`` when the
    caller only needs the first segment (e.g. reserved-key checks).
    """
    end = len(path)
    i = path.find(".")
    if 0 <= i < end:
        end = i
    j = path.find("[")
    if 0 <= j < end:
        end = j
    return path[:end]


def _is_qty_path(path: str) -> bool:
    """True if the leaf segment of ``path`` is the literal name 'qty'."""
    return path == "qty" or path.endswith(".qty")


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def now_epoch() -> int:
    """Current UTC time as integer Unix epoch seconds."""
    return int(datetime.now(timezone.utc).timestamp())


def now_iso() -> str:
    """Current UTC time as ISO-8601 string with 'Z' suffix."""
    return epoch_to_iso(now_epoch())


def epoch_to_iso(ep: int) -> str:
    """Convert integer epoch seconds to ISO-8601 UTC string."""
    return datetime.fromtimestamp(int(ep), tz=timezone.utc).isoformat().replace("+00:00", "Z")


def iso_to_epoch(iso: str) -> int:
    """Parse an ISO-8601 string and return integer Unix epoch seconds."""
    s = iso.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return int(datetime.fromisoformat(s).timestamp())


# ---------------------------------------------------------------------------
# Path helpers (dotted + bracket notation: a.b[0].c)
# ---------------------------------------------------------------------------

def parse_path(path: str) -> List[Union[str, int]]:
    """Parse 'a.b[0].c' -> ['a', 'b', 0, 'c']."""
    if path == "" or path is None:
        return []
    parts: List[Union[str, int]] = []
    for m in _PATH_TOKEN.finditer(path):
        key, idx = m.group(1), m.group(2)
        if key is not None:
            parts.append(key)
        else:
            parts.append(int(idx))
    return parts


def _join_path(segments: List[Union[str, int]]) -> str:
    out = ""
    for s in segments:
        if isinstance(s, int):
            out += f"[{s}]"
        else:
            out = s if not out else f"{out}.{s}"
    return out


def has_path(doc: Any, path: str) -> bool:
    """Return True if path exists in doc."""
    try:
        get_at_path(doc, path)
        return True
    except (KeyError, IndexError, TypeError):
        return False


def get_at_path(doc: Any, path: str) -> Any:
    """Read the value at a dotted/bracket path."""
    node = doc
    for seg in parse_path(path):
        if isinstance(seg, int):
            node = node[seg]
        else:
            node = node[seg]
    return node


def set_at_path(doc: Any, path: str, value: Any) -> None:
    """Set the value at a dotted/bracket path, creating intermediates as needed."""
    segs = parse_path(path)
    if not segs:
        raise ValueError("Cannot set empty path")
    node = doc
    for i, seg in enumerate(segs[:-1]):
        nxt = segs[i + 1]
        if isinstance(seg, int):
            while len(node) <= seg:
                node.append({} if isinstance(nxt, str) else [])
            if node[seg] is None:
                node[seg] = {} if isinstance(nxt, str) else []
            node = node[seg]
        else:
            if seg not in node or node[seg] is None:
                node[seg] = {} if isinstance(nxt, str) else []
            node = node[seg]
    last = segs[-1]
    if isinstance(last, int):
        while len(node) <= last:
            node.append(None)
        node[last] = value
    else:
        node[last] = value


def del_at_path(doc: Any, path: str) -> None:
    """Remove a value at the given path. No-op if missing."""
    segs = parse_path(path)
    if not segs:
        return
    parent_segs, last = segs[:-1], segs[-1]
    try:
        parent = get_at_path(doc, _join_path(parent_segs)) if parent_segs else doc
    except (KeyError, IndexError, TypeError):
        return
    try:
        del parent[last]
    except (KeyError, IndexError, TypeError):
        pass


def flatten(doc: Any, prefix: str = "", skip: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """Flatten a JSON tree into ``{path: scalar_value}``.

    Only leaf values appear; dicts and lists are recursed into. Empty
    dicts/lists are recorded as their literal value so they round-trip.
    """
    skip_set = set(skip or [])
    out: Dict[str, Any] = {}

    def _walk(node: Any, p: str) -> None:
        if isinstance(node, dict):
            if not node:
                out[p] = {}
                return
            for k, v in node.items():
                if not p and k in skip_set:
                    continue
                child = k if not p else f"{p}.{k}"
                _walk(v, child)
        elif isinstance(node, list):
            if not node:
                out[p] = []
                return
            for i, v in enumerate(node):
                child = f"{p}[{i}]"
                _walk(v, child)
        else:
            out[p] = node

    _walk(doc, prefix)
    return out


def unflatten(flat: Dict[str, Any]) -> Any:
    """Inverse of ``flatten``. Builds dicts/lists from a {path: value} map."""
    # Determine root type by inspecting first segment of any path.
    root: Any = {}
    for path, value in flat.items():
        if path == "":
            return value
        segs = parse_path(path)
        if isinstance(segs[0], int) and root == {}:
            root = []
        set_at_path(root, path, value)
    return root


# ---------------------------------------------------------------------------
# Hash helpers
# ---------------------------------------------------------------------------

def value_hash(value: Any) -> str:
    """Stable short SHA-256 (first 8 hex chars) of a JSON-serialisable value."""
    j = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(j.encode("utf-8")).hexdigest()[:8]


def hash_doc(doc: Dict[str, Any]) -> str:
    """Hash of the user-data portion of a doc (excludes the _his sidecar)."""
    clean = {k: v for k, v in doc.items() if k not in RESERVED_KEYS}
    return value_hash(clean)


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class JSONMERGE:
    """Field-level merger for JSON documents.

    Configure via constructor or by setting attributes:

        m = JSONMERGE({"qtyMath": True, "addUpIso": True})
        m.debug = True
    """

    # Default reserved keys (mutable for customization). Copies RESERVED_KEYS
    # so per-instance changes don't leak into the module constant.
    noCheck = set(RESERVED_KEYS)

    debug = False

    addCrEp = True       # write crDtEp on makeNewDoc
    addCrIso = False     # write crDt (ISO) on makeNewDoc
    addUpIso = False     # write upDt (ISO) on every update
    addHashes = True     # store per-field content hash 'h'
    qtyMath = True       # clamp 'qty'-suffixed merges so they never go negative
    schema_version = SCHEMA_VERSION

    # --------------------------- construction ----------------------------

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        if config:
            for k, v in config.items():
                if hasattr(self, k):
                    setattr(self, k, v)

    # --------------------------- time/util -------------------------------

    def makeTime(self) -> Dict[str, Any]:
        """Backwards-compatible time helper (returns ep / utc / iso)."""
        ep = now_epoch()
        return {"ep": ep, "utc": datetime.fromtimestamp(ep, tz=timezone.utc), "iso": epoch_to_iso(ep)}

    # --------------------------- lifecycle -------------------------------

    def make_new_doc(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Stamp a plain doc with _his + timestamps. Mutates and returns ``doc``.

        schemaV-3: ``_his[path]`` no longer stores ``v`` (the live value is
        read on demand from ``doc`` at ``path``). Only ``{t}`` and the
        optional content hash ``h`` are kept.
        """
        ep = now_epoch()
        flat = flatten(doc, skip=self.noCheck)
        history: Dict[str, Dict[str, Any]] = {}
        for path, val in flat.items():
            entry: Dict[str, Any] = {"t": ep}
            if self.addHashes:
                entry["h"] = value_hash(val)
            history[path] = entry

        doc["_his"] = history
        doc["upDtEp"] = ep
        doc["schemaV"] = self.schema_version
        if self.addCrEp:
            doc["crDtEp"] = ep
        if self.addCrIso:
            doc["crDt"] = epoch_to_iso(ep)
        if self.addUpIso:
            doc["upDt"] = epoch_to_iso(ep)
        return doc

    # back-compat alias
    makeNewDoc = make_new_doc

    def update_doc(self, doc: Dict[str, Any], changes: Union[List[Dict[str, Any]], Dict[str, Any]]) -> Dict[str, Any]:
        """Apply a list of changes to ``doc``.

        ``changes`` may be:
          * legacy: ``[{"name": "Bob"}, {"qty": 5}]``  (list of single-key dicts)
          * dotted: ``[{"address.city": "LF"}, {"tags[0]": "vip"}]``
          * nested: ``{"address": {"city": "LF"}, "qty": 5}``  (deep merge)
        """
        if not changes:
            return doc

        # Accept packed wire forms transparently — _his is library-only meta.
        if doc.get("_hisF") is not None:
            unpacked = unpack_his(doc)
            doc.clear()
            doc.update(unpacked)

        # Normalize to a flat {path: value} dict. Hot path: legacy single-key
        # dicts skip the flatten() overhead entirely.
        flat_changes: Dict[str, Any] = {}
        if isinstance(changes, dict):
            flat_changes = flatten(changes, skip=self.noCheck)
        else:
            for item in changes:
                if not isinstance(item, dict):
                    continue
                if len(item) == 1:
                    k, v = next(iter(item.items()))
                    if not isinstance(v, (dict, list)):
                        flat_changes[k] = v
                        continue
                flat_changes.update(flatten(item, skip=self.noCheck))

        cb = doc.setdefault("_his", {})
        ep: Optional[int] = None  # lazy: only allocate a timestamp if we write

        for path, new_val in flat_changes.items():
            if _top_segment(path) in self.noCheck:
                continue
            old = cb.get(path)
            if old is not None and old.get("v") == new_val:
                continue
            if ep is None:
                ep = now_epoch()
            self._stamp_change(doc, cb, path, new_val, ep)

        if ep is not None:
            doc["upDtEp"] = ep
            if self.addUpIso:
                doc["upDt"] = epoch_to_iso(ep)
        return doc

    updateDoc = update_doc

    # --------------------------- diff / patch ----------------------------

    def diff_docs(self, a: Dict[str, Any], b: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Return an RFC 6902-ish JSON Patch of differences from ``a`` to ``b``.

        Operates over user data (_his ignored). Ops emitted: add, remove, replace.
        Single pass over ``fb`` + a set difference for removals — no second
        full scan of ``fa``.
        """
        fa = flatten(a, skip=self.noCheck)
        fb = flatten(b, skip=self.noCheck)
        ops: List[Dict[str, Any]] = []
        for path, val in fb.items():
            old = fa.get(path, _MISSING)
            if old is _MISSING:
                ops.append({"op": "add", "path": _to_pointer(path), "value": val})
            elif old != val:
                ops.append({"op": "replace", "path": _to_pointer(path), "value": val})
        for path in fa.keys() - fb.keys():
            ops.append({"op": "remove", "path": _to_pointer(path)})
        return ops

    def patch_doc(self, doc: Dict[str, Any], ops: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Apply an RFC 6902 JSON Patch (subset: add/replace/remove) and update _his."""
        changes: List[Dict[str, Any]] = []
        removals: List[str] = []
        for op in ops:
            kind = op.get("op")
            ptr = _from_pointer(op.get("path", ""))
            if kind in ("add", "replace"):
                changes.append({ptr: op.get("value")})
            elif kind == "remove":
                removals.append(ptr)
        if changes:
            self.update_doc(doc, changes)
        for ptr in removals:
            del_at_path(doc, ptr)
            doc.get("_his", {}).pop(ptr, None)
            doc["upDtEp"] = now_epoch()
        return doc

    # --------------------------- merge core ------------------------------

    def _resolve_qty(self, path: str, val: Any) -> Any:
        """Inventory-safe rule: when qtyMath is enabled, a 'qty' leaf can't go below 0."""
        if not self.qtyMath or not _is_qty_path(path) or not isinstance(val, (int, float)):
            return val
        return max(0, val)

    def _clamp_qty_fields(self, doc: Dict[str, Any]) -> None:
        """Walk _his once; clamp any '...qty' leaf to >= 0 (when qtyMath is on).

        schemaV-3: reads the live value via ``get_at_path`` since the
        ``v`` field no longer lives inside ``_his``.
        """
        if not self.qtyMath:
            return
        cb = doc.get("_his", {})
        for path, rec in cb.items():
            if not _is_qty_path(path):
                continue
            try:
                v = get_at_path(doc, path)
            except (KeyError, IndexError, TypeError):
                continue
            if isinstance(v, (int, float)) and v < 0:
                set_at_path(doc, path, 0)
                if "h" in rec:
                    rec["h"] = value_hash(0)

    def _stamp_change(
        self,
        doc: Dict[str, Any],
        cb: Dict[str, Dict[str, Any]],
        path: str,
        val: Any,
        ep: int,
        prehash: Optional[str] = None,
    ) -> None:
        """Write ``val`` at ``path`` and refresh its _his entry.

        Reuses ``prehash`` when supplied to avoid re-hashing during merges.
        Caller is responsible for having decided the value actually changed.
        """
        set_at_path(doc, path, val)
        rec: Dict[str, Any] = {"t": ep}
        if self.addHashes:
            rec["h"] = prehash if prehash is not None else value_hash(val)
        cb[path] = rec

    def merge_doc_request(self, doc1: Dict[str, Any], doc2: Dict[str, Any]) -> Dict[str, Any]:
        """Apply newer fields from ``doc2`` into ``doc1`` (asymmetric).

        ``doc2`` may have a different ``docType``; only shared _his paths are
        considered. Writes inline (no intermediate change list / re-hashing).
        """
        doc1 = self._ensure_managed(doc1)
        doc2 = self._ensure_managed(doc2)
        cb1, cb2 = doc1["_his"], doc2["_his"]
        # Iterate the smaller side; merge only touches the intersection.
        small = cb2 if len(cb2) <= len(cb1) else cb1
        ep: Optional[int] = None
        for path in small:
            rec1 = cb1.get(path)
            rec2 = cb2.get(path)
            if rec1 is None or rec2 is None:
                continue
            if rec2.get("t", 0) <= rec1.get("t", 0):
                continue
            # schemaV-3: hash equality is the cheap "values identical?" test.
            # Fall back to live get_at_path when either hash is missing.
            h1, h2 = rec1.get("h"), rec2.get("h")
            if h1 is not None and h2 is not None:
                if h1 == h2:
                    continue
            elif has_path(doc1, path) and has_path(doc2, path) \
                    and get_at_path(doc1, path) == get_at_path(doc2, path):
                continue
            try:
                src_val = get_at_path(doc2, path)
            except (KeyError, IndexError, TypeError):
                continue
            val = self._resolve_qty(path, src_val)
            if ep is None:
                ep = now_epoch()
            # Reuse rec2's precomputed hash when the value passed through unchanged.
            prehash = rec2.get("h") if val == src_val else None
            self._stamp_change(doc1, cb1, path, val, ep, prehash=prehash)
        if ep is not None:
            doc1["upDtEp"] = ep
            if self.addUpIso:
                doc1["upDt"] = epoch_to_iso(ep)
        self._clamp_qty_fields(doc1)
        return doc1

    mergeDocReq = merge_doc_request

    def blind_merge(self, doc1: Dict[str, Any], doc2: Dict[str, Any]) -> Dict[str, Any]:
        """Reconcile two full copies of the same logical doc (symmetric).

        Writes inline so the merge is one pass over ``cb_other`` (no
        intermediate change list, no re-hashing of values whose hash we
        already have).
        """
        doc1 = self._ensure_managed(doc1)
        doc2 = self._ensure_managed(doc2)
        # base = doc with newer upDtEp (deepcopy to keep caller's input intact)
        if doc2.get("upDtEp", 0) > doc1.get("upDtEp", 0):
            base, other = copy.deepcopy(doc2), doc1
        else:
            base, other = copy.deepcopy(doc1), doc2

        cb_base = base["_his"]
        cb_other = other["_his"]
        ep: Optional[int] = None
        for path, rec_o in cb_other.items():
            try:
                src_val = get_at_path(other, path)
            except (KeyError, IndexError, TypeError):
                continue
            rec_b = cb_base.get(path)
            if rec_b is None:
                # 'other' has a field 'base' doesn't know about — take it.
                val = self._resolve_qty(path, src_val)
            else:
                if rec_o.get("t", 0) <= rec_b.get("t", 0):
                    continue
                # Hash-equality short-circuit (Option A); live fallback when missing.
                h_b, h_o = rec_b.get("h"), rec_o.get("h")
                if h_b is not None and h_o is not None:
                    if h_b == h_o:
                        continue
                elif has_path(base, path) and get_at_path(base, path) == src_val:
                    continue
                val = self._resolve_qty(path, src_val)
            if ep is None:
                ep = now_epoch()
            prehash = rec_o.get("h") if val == src_val else None
            self._stamp_change(base, cb_base, path, val, ep, prehash=prehash)
        if ep is not None:
            base["upDtEp"] = ep
            if self.addUpIso:
                base["upDt"] = epoch_to_iso(ep)
        self._clamp_qty_fields(base)
        return base

    blindMerge = blind_merge

    def three_way_merge(
        self,
        base: Dict[str, Any],
        ours: Dict[str, Any],
        theirs: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[str]]:
        """Git-style three-way merge.

        Returns ``(merged_doc, conflicting_paths)``. A conflict is any path
        changed in BOTH ``ours`` and ``theirs`` with different values.
        Non-conflicting changes are applied automatically; conflicts default
        to the newer timestamp (with ``qtyMath`` applied where relevant).
        """
        base = self._ensure_managed(base)
        ours = self._ensure_managed(ours)
        theirs = self._ensure_managed(theirs)
        merged = copy.deepcopy(ours)
        cb_base, cb_ours, cb_theirs = base["_his"], ours["_his"], theirs["_his"]
        conflicts: List[str] = []
        all_paths = set(cb_ours) | set(cb_theirs) | set(cb_base)
        changes: List[Dict[str, Any]] = []

        def _live(doc: Dict[str, Any], path: str, default: Any) -> Any:
            """schemaV-3: pull the value from the doc body, not _his."""
            try:
                return get_at_path(doc, path)
            except (KeyError, IndexError, TypeError):
                return default

        for path in all_paths:
            b = _live(base, path, None) if path in cb_base else None
            o = _live(ours, path, b) if path in cb_ours else b
            t = _live(theirs, path, b) if path in cb_theirs else b
            if o == t:
                continue
            if o == b and t != b:
                changes.append({path: t})
            elif t == b and o != b:
                # already in 'ours'
                continue
            else:
                # Both sides changed from base -> conflict
                conflicts.append(path)
                ours_rec = cb_ours.get(path, {"t": 0})
                their_rec = cb_theirs.get(path, {"t": 0})
                if their_rec.get("t", 0) > ours_rec.get("t", 0):
                    newer_val = t
                else:
                    newer_val = o
                val = self._resolve_qty(path, newer_val)
                changes.append({path: val})
        if changes:
            self.update_doc(merged, changes)
        self._clamp_qty_fields(merged)
        return merged, conflicts

    # --------------------------- introspection ---------------------------

    def is_managed(self, doc: Dict[str, Any]) -> bool:
        return isinstance(doc, dict) and "_his" in doc and "upDtEp" in doc

    def validate(self, doc: Dict[str, Any]) -> List[str]:
        """Return a list of warnings (empty = healthy).

        schemaV-3: there is no `_his[path].v` to drift against, so drift is
        detected purely via the per-field hash ``h`` (when ``addHashes``
        is on). Untracked fields and dead ``_his`` paths are still flagged.
        """
        issues: List[str] = []
        if not self.is_managed(doc):
            return ["doc is not managed (missing _his/upDtEp)"]
        flat = flatten(doc, skip=self.noCheck)
        cb = doc["_his"]
        for path, val in flat.items():
            rec = cb.get(path)
            if rec is None:
                issues.append(f"untracked field: {path}")
                continue
            if "h" in rec and rec["h"] != value_hash(val):
                issues.append(f"hash mismatch at {path} (tampered?)")
        for path in cb:
            if path not in flat:
                issues.append(f"_his references missing path: {path}")
        return issues

    def history_iso(self, doc: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Return _his with epoch timestamps expanded to ISO-8601 strings.

        schemaV-3: ``v`` is hydrated from the live doc body for callers
        that still expect to see the value alongside the timestamp.
        """
        out: Dict[str, Dict[str, Any]] = {}
        for path, rec in doc.get("_his", {}).items():
            r = dict(rec)
            if "t" in r:
                r["tIso"] = epoch_to_iso(r["t"])
            try:
                r["v"] = get_at_path(doc, path)
            except (KeyError, IndexError, TypeError):
                pass
            out[path] = r
        return out

    def list_changes_since(self, doc: Dict[str, Any], since_epoch: int) -> List[Dict[str, Any]]:
        """Fields whose last-modified time is >= ``since_epoch``."""
        out: List[Dict[str, Any]] = []
        for path, rec in doc.get("_his", {}).items():
            if rec.get("t", 0) >= since_epoch:
                try:
                    v = get_at_path(doc, path)
                except (KeyError, IndexError, TypeError):
                    v = None
                out.append({"path": path, "v": v, "t": rec.get("t")})
        return sorted(out, key=lambda x: x["t"], reverse=True)

    # --------------------------- internals -------------------------------

    def _ensure_managed(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a doc so the merge ops see the canonical in-memory form.

        Accepts any of the three wire shapes:
          * dict-of-dicts (default in-memory)
          * columnar JSON  (``_hisF == "c"``)  — Option E
          * CBOR blob      (``_hisF == "b"``)  — Option D
        Auto-calls ``unpack_his`` when the marker is set, so callers don't
        have to: ``_his`` becomes "library-only" metadata.
        """
        if doc.get("_hisF") is not None:
            doc = unpack_his(doc)
        if not self.is_managed(doc):
            return self.make_new_doc(copy.deepcopy(doc))
        return doc


# ---------------------------------------------------------------------------
# JSON Pointer <-> dotted-path conversion (RFC 6901 helpers)
# ---------------------------------------------------------------------------

def _to_pointer(dotted: str) -> str:
    """Convert 'a.b[0].c' -> '/a/b/0/c' (RFC 6901)."""
    segs = parse_path(dotted)
    return "/" + "/".join(_escape_ptr(str(s)) for s in segs)


def _from_pointer(ptr: str) -> str:
    """Convert '/a/b/0/c' -> 'a.b[0].c'."""
    if not ptr or ptr == "/":
        return ""
    parts = [_unescape_ptr(p) for p in ptr.lstrip("/").split("/")]
    out = ""
    for p in parts:
        if p.isdigit():
            out += f"[{p}]"
        else:
            out = p if not out else f"{out}.{p}"
    return out


def _escape_ptr(s: str) -> str:
    return s.replace("~", "~0").replace("/", "~1")


def _unescape_ptr(s: str) -> str:
    return s.replace("~1", "/").replace("~0", "~")


# ---------------------------------------------------------------------------
# Wire-format helpers — Options D + E
# ---------------------------------------------------------------------------
#
# In-memory ``_his`` is a dict-of-dicts (schemaV-3 ``{t,h}`` records). For
# storage / transport you can opt into a smaller wire layout via
# ``pack_his(doc, fmt=...)`` and reverse it with ``unpack_his(doc)``.
#
#   fmt='cols' (Option E):
#       _his  -> {"p":["...",...], "t":[...], "h":["...",...]}
#       _hisF -> "c"
#
#   fmt='cbor' (Option D):
#       _his  -> {"d":"<base64-cbor>", "s":"<sha256 of bytes>"}
#       _hisF -> "b"
#
# All other library functions expect the dict-of-dicts shape; call
# ``unpack_his(doc)`` immediately after loading from storage.

import base64 as _b64


def _his_pack_cols(his: Dict[str, Dict[str, Any]]) -> Dict[str, List[Any]]:
    """Dict-of-dicts ``_his`` -> columnar ``{"p":[...],"t":[...],"h":[...]}``."""
    paths: List[str] = []
    ts: List[int] = []
    hs: List[str] = []
    has_h = any("h" in r for r in his.values())
    for p, r in his.items():
        paths.append(p)
        ts.append(int(r.get("t", 0)))
        if has_h:
            hs.append(r.get("h", ""))
    out: Dict[str, List[Any]] = {"p": paths, "t": ts}
    if has_h:
        out["h"] = hs
    return out


def _his_unpack_cols(packed: Dict[str, List[Any]]) -> Dict[str, Dict[str, Any]]:
    """Columnar -> dict-of-dicts."""
    paths = packed.get("p", [])
    ts = packed.get("t", [])
    hs = packed.get("h")
    out: Dict[str, Dict[str, Any]] = {}
    for i, p in enumerate(paths):
        rec: Dict[str, Any] = {"t": int(ts[i])}
        if hs is not None and i < len(hs) and hs[i] != "":
            rec["h"] = hs[i]
        out[p] = rec
    return out


def _his_pack_cbor(his: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
    """Dict-of-dicts -> ``{"d":"<base64>", "s":"<sha256>"}`` via CBOR.

    Requires the optional ``cbor2`` dependency. Stores the columnar form
    as a CBOR blob, base64-wrapped so the outer wire format can stay
    JSON. The sha256 in ``s`` covers the *raw bytes* and is verified on
    unpack to give the integrity-check guarantee the design called for.
    """
    try:
        import cbor2  # type: ignore
    except ImportError as e:  # pragma: no cover - depends on user env
        raise RuntimeError(
            "pack_his(fmt='cbor') requires the 'cbor2' package; "
            "install it with `pip install cbor2`."
        ) from e
    blob: bytes = cbor2.dumps(_his_pack_cols(his))
    return {
        "d": _b64.b64encode(blob).decode("ascii"),
        "s": hashlib.sha256(blob).hexdigest(),
    }


def _his_unpack_cbor(packed: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
    """Inverse of ``_his_pack_cbor``. Raises if the integrity hash fails."""
    try:
        import cbor2  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "unpack_his of cbor format requires the 'cbor2' package."
        ) from e
    blob = _b64.b64decode(packed["d"])
    if hashlib.sha256(blob).hexdigest() != packed["s"]:
        raise ValueError("_his cbor blob hash mismatch (tampered or corrupt)")
    return _his_unpack_cols(cbor2.loads(blob))


def pack_his(doc: Dict[str, Any], fmt: str = "cols") -> Dict[str, Any]:
    """Return a *copy* of ``doc`` with ``_his`` re-encoded for storage.

    Parameters
    ----------
    doc : dict
        A managed document with the schemaV-3 dict-of-dicts ``_his``.
    fmt : {'cols', 'cbor'}
        Wire format. ``'cols'`` is pure JSON columnar; ``'cbor'`` is a
        base64-wrapped CBOR blob with an integrity sha256.

    Adds a ``_hisF`` marker so ``unpack_his`` can sniff the format.
    """
    if fmt not in ("cols", "cbor"):
        raise ValueError(f"unknown pack_his fmt: {fmt!r}")
    out = copy.deepcopy(doc)
    his = out.get("_his") or {}
    if fmt == "cols":
        out["_his"] = _his_pack_cols(his)
        out["_hisF"] = "c"
    else:  # cbor
        out["_his"] = _his_pack_cbor(his)
        out["_hisF"] = "b"
    return out


def unpack_his(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Return a *copy* of ``doc`` with ``_his`` restored to dict-of-dicts.

    No-op when ``_hisF`` is absent (doc is already unpacked).
    """
    fmt = doc.get("_hisF")
    if fmt is None:
        return doc
    out = copy.deepcopy(doc)
    packed = out.get("_his") or {}
    if fmt == "c":
        out["_his"] = _his_unpack_cols(packed)
    elif fmt == "b":
        out["_his"] = _his_unpack_cbor(packed)
    else:
        raise ValueError(f"unknown _hisF marker: {fmt!r}")
    out.pop("_hisF", None)
    return out
