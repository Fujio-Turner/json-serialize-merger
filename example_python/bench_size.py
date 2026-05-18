"""bench_size.py — measure the actual document-size impact of the
schemaV-3 changes (Option A) and the optional wire formats
(Option E columnar, Option D CBOR).

It builds a synthetic doc with many nested fields, runs make_new_doc,
then compares the JSON byte size of:

    raw           — user payload only (no _his)
    v2 (legacy)   — what _his looked like before (with redundant `v`)
    v3            — current in-memory shape (Option A: no `v`)
    v3 + cols     — Option E columnar JSON wire format
    v3 + cbor     — Option D CBOR blob (requires cbor2)

Run:   python3 bench_size.py
"""

import copy
import json
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)
import JsonMerge


def build_doc(n_lines: int = 50) -> dict:
    """Synthetic invoice-style doc with `n_lines` line items."""
    return {
        "docType": "invoice",
        "name": "Bob Smith",
        "address": {"city": "Lake Falls", "zip": "8000", "state": "MA"},
        "tags": ["vip", "net30", "wholesale"],
        "lines": [
            {"sku": f"SKU-{i:04d}", "qty": i, "price": i * 1.25, "note": "n/a"}
            for i in range(n_lines)
        ],
    }


def legacy_v2_his(doc: dict) -> dict:
    """Reconstruct what v2 _his looked like (with redundant `v`) for comparison."""
    out = copy.deepcopy(doc)
    flat = JsonMerge.flatten(out, skip=JsonMerge.RESERVED_KEYS)
    his = {}
    for path, val in flat.items():
        his[path] = {"v": val, "t": out["_his"][path]["t"], "h": out["_his"][path]["h"]}
    out["_his"] = his
    return out


def size(d: dict) -> int:
    return len(json.dumps(d, separators=(",", ":")))


def main() -> None:
    m = JsonMerge.JSONMERGE()
    sizes = []
    for n in (10, 50, 200):
        raw = build_doc(n)
        raw_size = size(raw)

        managed = m.make_new_doc(copy.deepcopy(raw))
        v3_size = size(managed)

        legacy = legacy_v2_his(managed)
        v2_size = size(legacy)

        cols = JsonMerge.pack_his(managed, fmt="cols")
        cols_size = size(cols)

        try:
            cbor = JsonMerge.pack_his(managed, fmt="cbor")
            cbor_size = size(cbor)
        except RuntimeError as e:
            cbor_size = None

        sizes.append((n, raw_size, v2_size, v3_size, cols_size, cbor_size))

    # Pretty table
    header = f"{'leaves':>7}  {'raw':>8}  {'v2(old)':>10}  {'v3(A)':>10}  {'v3+cols(E)':>12}  {'v3+cbor(D)':>12}"
    print(header)
    print("-" * len(header))
    for n, r, v2, v3, c, cb in sizes:
        cb_s = f"{cb:>12}" if cb is not None else f"{'n/a':>12}"
        # Each line entry = 4 leaves, plus 5 root scalars/nested
        approx_leaves = n * 4 + 7
        print(f"{approx_leaves:>7}  {r:>8}  {v2:>10}  {v3:>10}  {c:>12}  {cb_s}")

    print()
    print("Ratios vs raw user payload:")
    print(f"{'leaves':>7}  {'v2/raw':>8}  {'v3/raw':>8}  {'cols/raw':>10}  {'cbor/raw':>10}")
    print("-" * 50)
    for n, r, v2, v3, c, cb in sizes:
        approx_leaves = n * 4 + 7
        cb_r = f"{cb/r:>10.2f}" if cb is not None else f"{'n/a':>10}"
        print(f"{approx_leaves:>7}  {v2/r:>8.2f}  {v3/r:>8.2f}  {c/r:>10.2f}  {cb_r}")

    # Round-trip sanity for pack/unpack
    raw = build_doc(20)
    managed = m.make_new_doc(copy.deepcopy(raw))
    for fmt in ("cols", "cbor"):
        try:
            packed = JsonMerge.pack_his(managed, fmt=fmt)
        except RuntimeError as e:
            print(f"\n[skip] {fmt}: {e}")
            continue
        round_tripped = JsonMerge.unpack_his(packed)
        ok = round_tripped["_his"] == managed["_his"] and "_hisF" not in round_tripped
        print(f"\nround-trip {fmt:>4}: {'PASS' if ok else 'FAIL'}")


if __name__ == "__main__":
    main()
