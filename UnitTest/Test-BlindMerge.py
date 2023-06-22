import json
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)
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
        data = a.blindMerge(d,c)
    except:
        print("An exception occurred",data)