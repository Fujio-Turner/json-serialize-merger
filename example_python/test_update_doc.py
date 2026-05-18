import json
import os
import sys
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)
import JsonMerge

if __name__ == "__main__":

    with open(current_dir + '/test-sample-json-data/OUTPUT-New-doc-made.json', 'r') as file1:
        d = json.load(file1)

    with open(current_dir + '/test-sample-json-data/INPUT-Simple-doc-to-change.json', 'r') as file2:
        c = json.load(file2)

    with open(current_dir + '/test-sample-json-data/INPUT-Simple-doc.json', 'r') as file3:
        e = json.load(file3)

    a = JsonMerge.JSONMERGE()

    data = None
    try:
        data = a.updateDoc(d,c)
    except:
        print("An exception occurred",data)


    ##Check if has '_his' and not empty
    if data["_his"]:
        print("check if has _his exists: PASS ")
    else:
        print("check if has _his exists: FAIL")

    if len(data["_his"].keys()) > 0:
        print("check if has _his not empty: PASS ")
    else:
        print("check if has _his not empty: FAIL")

    ### Check if new change took #####
    if e["apples"] != data["apples"]:
        print("check apples have changed: PASS   Old: ", e["apples"],' New: ' ,data["apples"])
    else:
        print("check apples have changed: FAIL")

    ### Check new second item in the list took #####
    for key, value in c[1].items():
        kName = key
    if kName in data:
        print("check if new second change took: PASS ")
    else:
        print("check if new second change took: FAIL")
   
    ### check if has upDtEp
    if data["upDtEp"]:
        print("check if has upDtEp exists: PASS ")
    else:
        print("check if has upDtEp exists: FAIL")

    ### check if has upDtEp is epoch time

    if isinstance(data["upDtEp"], int):
        print("check if has upDtEp is INT: PASS ")
    else:
        print("check if has upDtEp is INT: FAIL")