"""Exercises the v2 features: nested fields, arrays, hashes, diff, JSON
Patch, three-way merge, ISO helpers and validation."""

import copy
import os
import sys
import time

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)
import JsonMerge


def check(name: str, cond: bool, extra: str = "") -> None:
    print(f"{name}: {'PASS' if cond else 'FAIL'} {extra}")


if __name__ == "__main__":
    m = JsonMerge.JSONMERGE()

    # --- 1. Nested doc with arrays + objects ---------------------------------
    doc = {
        "docType": "invoice",
        "name": "Bob",
        "address": {"city": "Lake Falls", "zip": "8000"},
        "tags": ["vip", "net30"],
        "lines": [
            {"sku": "A-1", "qty": 5},
            {"sku": "B-2", "qty": 3},
        ],
    }
    managed = m.make_new_doc(doc)
    cb = managed["_his"]
    check("nested path tracked (address.city)", "address.city" in cb)
    check("nested path tracked (address.zip)", "address.zip" in cb)
    check("array path tracked (tags[0])", "tags[0]" in cb)
    check("deep path tracked (lines[1].qty)", "lines[1].qty" in cb)
    check("per-field hash recorded", "h" in cb["address.city"])
    check("docType NOT tracked (reserved)", "docType" not in cb)

    # --- 2. Update via mixed shapes ------------------------------------------
    time.sleep(1)  # ensure timestamp differs
    m.update_doc(managed, [
        {"address.city": "Lake Falls West"},   # dotted-path single
        {"tags[1]": "net60"},                   # array index
        {"lines[0].qty": 9},                    # deep
    ])
    check("city updated", managed["address"]["city"] == "Lake Falls West")
    check("tag[1] updated", managed["tags"][1] == "net60")
    check("line qty updated", managed["lines"][0]["qty"] == 9)
    check("_his hash refreshed", cb["address.city"]["h"] == JsonMerge.value_hash("Lake Falls West"))

    # nested-dict shape too
    m.update_doc(managed, {"address": {"zip": "8001"}})
    check("nested-dict update applied", managed["address"]["zip"] == "8001")

    # --- 3. Time helpers ------------------------------------------------------
    ep = JsonMerge.now_epoch()
    iso = JsonMerge.epoch_to_iso(ep)
    rt = JsonMerge.iso_to_epoch(iso)
    check("epoch <-> iso round-trip", ep == rt, f"({ep} -> {iso} -> {rt})")

    hist_iso = m.history_iso(managed)
    check("history_iso adds tIso", "tIso" in hist_iso["address.city"])

    # --- 4. Diff + JSON Patch -------------------------------------------------
    a = m.make_new_doc({"name": "A", "tags": ["x"], "address": {"city": "C1"}})
    b = m.make_new_doc({"name": "B", "tags": ["x", "y"], "address": {"city": "C2"}})
    ops = m.diff_docs(a, b)
    paths = {(o["op"], o["path"]) for o in ops}
    check("diff: replace /name", ("replace", "/name") in paths)
    check("diff: add /tags/1", ("add", "/tags/1") in paths)
    check("diff: replace /address/city", ("replace", "/address/city") in paths)

    patched = m.patch_doc(a, ops)
    check("patch applies replace", patched["name"] == "B")
    check("patch applies add (array)", patched["tags"] == ["x", "y"])

    # --- 5. blind_merge across nested fields ---------------------------------
    d1 = m.make_new_doc({"docType": "x", "name": "Alice", "address": {"city": "Old"}})
    time.sleep(1)
    d2 = m.make_new_doc({"docType": "x", "name": "Alice2", "address": {"city": "New"}})
    merged = m.blind_merge(d1, d2)
    check("blind_merge picks newer name", merged["name"] == "Alice2")
    check("blind_merge picks newer nested city", merged["address"]["city"] == "New")

    # --- 6. qtyMath clamp (never negative) -----------------------------------
    inv = m.make_new_doc({"docType": "stock", "qty": 5})
    time.sleep(1)
    other = m.make_new_doc({"docType": "stock", "qty": -3})
    merged = m.blind_merge(inv, other)
    check("qtyMath clamps to >= 0", merged["qty"] >= 0, f"(got {merged['qty']})")

    # --- 7. three_way_merge with conflict ------------------------------------
    base = m.make_new_doc({"docType": "x", "title": "v0", "body": "body0"})
    time.sleep(1)
    ours = copy.deepcopy(base)
    m.update_doc(ours, [{"title": "ours-title"}])
    theirs = copy.deepcopy(base)
    time.sleep(1)
    m.update_doc(theirs, [{"title": "theirs-title"}, {"body": "body-from-theirs"}])
    merged, conflicts = m.three_way_merge(base, ours, theirs)
    check("3way: non-conflicting change auto-applied", merged["body"] == "body-from-theirs")
    check("3way: conflict reported on title", "title" in conflicts)
    check("3way: newer (theirs) wins title", merged["title"] == "theirs-title")

    # --- 8. validate / tamper detection --------------------------------------
    good = m.make_new_doc({"docType": "x", "name": "ok"})
    check("validate clean doc -> no issues", m.validate(good) == [])
    good["name"] = "TAMPERED"  # bypass updateDoc -> hash should mismatch
    issues = m.validate(good)
    check("validate detects tamper", any("hash mismatch" in i or "drift" in i for i in issues),
          f"(issues={issues})")

    # --- 9. flatten/unflatten round-trip -------------------------------------
    sample = {"a": 1, "b": [{"c": 2}, {"c": 3}], "d": {"e": {"f": "g"}}}
    flat = JsonMerge.flatten(sample)
    rebuilt = JsonMerge.unflatten(flat)
    check("flatten/unflatten round-trip", rebuilt == sample, f"(flat={flat})")
