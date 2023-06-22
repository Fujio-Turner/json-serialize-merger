import json
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)
import JsonMerge

if __name__ == "__main__":

    with open(current_dir + '/test-sample-json-data/INPUT-Simple-doc.json', 'r') as file:
        d = json.load(file)

    a = JsonMerge.JSONMERGE()

    data = None
    try:
        data = a.makeNewDoc(d)
    except:
        print("An exception occurred",data)
    
    ##Check if has 'cbHis' and not empty
    if data["cbHis"]:
        print("check if has cbHis exists: PASS ")
    else:
        print("check if has cbHis exists: FAIL")

    if len(data["cbHis"].keys()) > 0:
        print("check if has cbHis not empty: PASS ")
    else:
        print("check if has cbHis not empty: FAIL")

    ### check if has upDtEp
    if data["upDtEp"]:
        print("check if has upDtEp exists: PASS ")
    else:
        print("check if has upDtEp exists: FAIL")

    ### check if has upDtEp is epoch time
    if isinstance(data["upDtEp"], int):
        print("check if has upDtEp is INT: PASS ")
    else:
        print("check if has upDtEp is INT : FAIL")

    with open(current_dir + "/test-sample-json-data/OUTPUT-New-doc-made.json", "w") as file:
        json.dump(data, file)