# example_data/

Sample JSON files used by the [index.html](../index.html) browser demo.

| File | Used for | Notes |
|------|----------|-------|
| `01-simple-plain-invoice.json`     | `makeNewDoc` | Plain, unmanaged document. |
| `02-nested-plain-invoice.json`     | `makeNewDoc` | Nested object + array doc — shows v2 path tracking. |
| `03-update-changes.json`           | `updateDoc`  | Legacy list-of-single-key changes. |
| `04-update-changes-nested.json`    | `updateDoc`  | Dotted/bracket paths (`address.city`, `tags[1]`, …). |
| `05-managed-invoice.json`          | input for all merge ops | Already has `_his`. |
| `06-merge-request-doc.json`        | `mergeDocReq` | Different `docType` (`invoiceRequest`), newer per-field timestamps, includes a negative `qty` to demo `qtyMath` clamping. |
| `07-blind-merge-doc1.json`         | `blindMerge` (left)  | Replica A. |
| `08-blind-merge-doc2.json`         | `blindMerge` (right) | Replica B (newer name + qty). |
| `09-three-way-base.json`           | `threeWayMerge` base   | Common ancestor. |
| `10-three-way-ours.json`           | `threeWayMerge` ours   | We changed `address.city` and `qty`. |
| `11-three-way-theirs.json`         | `threeWayMerge` theirs | They changed `name`, `address.city`, `address.zip`, `qty` → conflicts on `address.city`, `qty`. |
| `12-diff-doc-a.json`               | `diffDocs` (a) | |
| `13-diff-doc-b.json`               | `diffDocs` (b) | |
| `14-json-patch-ops.json`           | `patchDoc`   | RFC 6902 ops to apply to a managed doc. |
