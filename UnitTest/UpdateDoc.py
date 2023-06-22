import json

import sys
sys.path.append('..')
import scrap

if __name__ == "__main__":

    with open('New-Doc-Made.json', 'r') as file1:
        d = json.load(file1)

    with open('Simple-doc-to-change.json', 'r') as file2:
        c = json.load(file2)

    with open('Simple-doc.json', 'r') as file3:
        e = json.load(file3)

    a = scrap.JSONMERGE()
    data = a.updateDoc(d,c)

    ### Check if new change took #####
    if e["apples"] != data["apples"]:
        print("check apples have changed : PASS   Old: ", e["apples"],' New: ' ,data["apples"])
    else:
        print("check apples have changed : FAIL")


    if data["cbHis"]:
        print("check if has cbHis : PASS ", data["cbHis"])
    else:
        print("check if has cbHis : FAIL")

    ### check if has upDtEp
    if data["upDtEp"]:
        print("check if has upDtEp : PASS ", data["upDtEp"])
    else:
        print("check if has upDtEp : FAIL")

    ### check if has upDtEp is epoch time

    if isinstance(data["upDtEp"], int):
        print("check if has upDtEp is INT: PASS ", data["upDtEp"])
    else:
        print("check if has upDtEp is INT : FAIL")