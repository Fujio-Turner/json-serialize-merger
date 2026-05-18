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

    a = JsonMerge.JSONMERGE()
    
    data = None
    try:
        data = a.blindMerge(d,c)
    except:
        print("An exception occurred",data)
    print(data)