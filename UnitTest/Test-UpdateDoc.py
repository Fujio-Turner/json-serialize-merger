import json
import sys
sys.path.append('..')
import scrap

if __name__ == "__main__":

    with open('test-sample-json-data/OUTPUT-New-doc-made.json', 'r') as file1:
        d = json.load(file1)

    with open('test-sample-json-data/INPUT-Simple-doc-to-change.json', 'r') as file2:
        c = json.load(file2)

    with open('test-sample-json-data/INPUT-Simple-doc.json', 'r') as file3:
        e = json.load(file3)

    a = scrap.JSONMERGE()

    data = None
    try:
        data = a.updateDoc(d,c)
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