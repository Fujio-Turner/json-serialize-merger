import json
import sys
sys.path.append('..')
import scrap

if __name__ == "__main__":

    with open('test-sample-json-data/OUTPUT-New-doc-made.json', 'r') as file1:
        d = json.load(file1)

    with open('test-sample-json-data/INPUT-request-doc.json', 'r') as file2:
        c = json.load(file2)

    with open('test-sample-json-data/INPUT-Simple-doc.json', 'r') as file3:
        e = json.load(file3)

    a = scrap.JSONMERGE()

    data = None
    try:
        data = a.mergeDocReq(d,c)
    except:
        print("An exception occurred",data)