import json

import sys
sys.path.append('..')
import scrap

if __name__ == "__main__":

    with open('simple-doc.json', 'r') as file:
        d = json.load(file)

    a = scrap.JSONMERGE()

    data = a.makeNewDoc(d)

    ##Check if has 'cbHis' and not empty

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
        print("check if has upDtEp is INT: PASS ",data["upDtEp"])
    else:
        print("check if has upDtEp is INT : FAIL")

    with open("New-Doc-Made.json", "w") as file:
        json.dump(data, file)