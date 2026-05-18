import json
import os
import sys
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)
import JsonMerge

if __name__ == "__main__":

    with open(current_dir + '/test-sample-json-data/OUTPUT-New-doc-made.json', 'r') as file1:
        d = json.load(file1)

    with open(current_dir + '/test-sample-json-data/INPUT-Request-change-doc-different.json', 'r') as file2:
        c = json.load(file2)

    with open(current_dir + '/test-sample-json-data/INPUT-Simple-doc.json', 'r') as file3:
        e = json.load(file3)

    a = JsonMerge.JSONMERGE()

    data = None
    try:
        data = a.mergeDocReq(d,c)
    except Exception as ex:
        print("An exception occurred", ex)

    if data and "_his" in data:
        print("check merged doc has _his: PASS ")
    else:
        print("check merged doc has _his: FAIL")

    # doc1 ('invoice') and doc2 ('invoiceRequest') share the 'apples' field.
    # doc2's _his.apples.t (1687459654) is older than doc1's, so 'apples' must stay.
    if data and data.get("apples") == d["apples"]:
        print("check older-side field NOT overwritten: PASS ")
    else:
        print("check older-side field NOT overwritten: FAIL")

    # docType must remain 'invoice' (reserved, never merged)
    if data and data.get("docType") == "invoice":
        print("check docType preserved: PASS ")
    else:
        print("check docType preserved: FAIL")