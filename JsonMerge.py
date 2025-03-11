import json
from datetime import datetime

class JSONMERGE:
    noCheck = {"_his", "docType", "upDtEp"}  # Changed "cbHis" to "_his"
    debug = False

    addCrEp = False
    addCrIso = False
    addCrLoc = False

    addUpLoc = False
    addUpIso = False

    qtyMathEnabled = True

    def __init__(self, config={}):
        self.addUpLoc = False

    def makeTime(self):
        now = datetime.utcnow()
        return {"ep": int(now.timestamp()), "utc": now, "iso": now.astimezone().isoformat()}

    def qtyMath(self, newestQty, oldestQty):
        if oldestQty - newestQty > 0:
            return {"qty": 0, "exceptionQty": False}
        if oldestQty - newestQty == 0:
            return {"qty": 0, "exceptionQty": False}
        if oldestQty - newestQty < 0:
            return {"qty": 0, "exceptionQty": True}

    def create_history(self, value, timestamp):
        if isinstance(value, dict):
            return {k: self.create_history(v, timestamp) for k, v in value.items()}
        elif isinstance(value, list):
            return [self.create_history(item, timestamp) for item in value]
        else:
            return {"v": value, "t": timestamp}

    def update_history(self, history, path, new_value, timestamp):
        keys = path.split(".")
        current = history
        for i, key in enumerate(keys[:-1]):
            if key.isdigit():
                idx = int(key)
                while len(current) <= idx:
                    current.append({})
                current = current[idx]
            else:
                if key not in current:
                    current[key] = {}
                current = current[key]
        last_key = keys[-1]
        if last_key.isdigit():
            idx = int(last_key)
            while len(current) <= idx:
                current.append({})
            current[idx] = self.create_history(new_value, timestamp)
        else:
            current[last_key] = self.create_history(new_value, timestamp)

    def merge_histories(self, his1, his2):
        if isinstance(his1, dict) and "v" in his1 and isinstance(his2, dict) and "v" in his2:
            return his1 if his1["t"] >= his2["t"] else his2
        elif isinstance(his1, dict) and isinstance(his2, dict):
            merged = his1.copy()
            for k, v2 in his2.items():
                if k in merged:
                    merged[k] = self.merge_histories(merged[k], v2)
                else:
                    merged[k] = v2
            return merged
        elif isinstance(his1, list) and isinstance(his2, list):
            merged = his1.copy()
            for i in range(max(len(his1), len(his2))):
                if i < len(his2):
                    if i < len(merged):
                        merged[i] = self.merge_histories(merged[i], his2[i])
                    else:
                        merged.append(his2[i])
            return merged
        return his1

    def makeNewDoc(self, newDoc):
        docTime = self.makeTime()
        history = {}
        for k, v in newDoc.items():
            if k in self.noCheck:
                continue
            history[k] = self.create_history(v, docTime["ep"])
        newDoc["_his"] = history  # Changed "cbHis" to "_his"
        newDoc["upDtEp"] = docTime["ep"]
        if self.addUpIso:
            newDoc["upDt"] = docTime["iso"]
        if self.addCrIso:
            newDoc["upCr"] = docTime["iso"]
        if self.addCrEp:
            newDoc["upCrEp"] = docTime["ep"]
        return newDoc

    def updateDoc(self, doc, changes):
        if not changes:
            return doc
        docTime = self.makeTime()
        doc["upDtEp"] = docTime["ep"]
        if self.addUpIso:
            doc["upDt"] = docTime["iso"]
        for change in changes:
            key, value = list(change.items())[0]
            if key in self.noCheck:
                continue
            keys = key.split(".")
            current = doc
            for i, k in enumerate(keys[:-1]):
                if k.isdigit():
                    idx = int(k)
                    while len(current) <= idx:
                        current.append({})
                    current = current[idx]
                else:
                    if k not in current:
                        current[k] = {}
                    current = current[k]
            last_key = keys[-1]
            if isinstance(current, list):
                idx = int(last_key)
                if idx < len(current):
                    current[idx] = value
                elif idx == len(current):
                    current.append(value)
                else:
                    raise IndexError(f"List index out of range: {idx} > {len(current)}")
            elif isinstance(current, dict):
                current[last_key] = value
            else:
                raise ValueError(f"Unsupported type for current: {type(current)}")
            self.update_history(doc["_his"], key, value, docTime["ep"])  # Changed "cbHis" to "_his"
        return doc

    def mergeDocReq(self, doc1, doc2):
        mDoc = doc1.copy()
        upList = []
        for k, v1 in doc1["_his"].items():  # Changed "cbHis" to "_his"
            if k in doc2["_his"]:  # Changed "cbHis" to "_his"
                v2 = doc2["_his"][k]  # Changed "cbHis" to "_his"
                merged = self.merge_histories(v1, v2)
                if merged != v1:
                    if k == "qty" and self.qtyMathEnabled:
                        qty = self.qtyMath(merged["v"], v1["v"])
                        upList.append({k: qty["qty"]})
                    else:
                        upList.append({k: merged["v"]})
        if upList:
            mDoc = self.updateDoc(doc1, upList)
        return mDoc

    def blindMerge(self, doc1, doc2):
        m1Doc = doc1 if doc1["upDtEp"] >= doc2["upDtEp"] else doc2
        m2Doc = doc2 if m1Doc is doc1 else doc1
        upList = []
        for k, v1 in m1Doc["_his"].items():  # Changed "cbHis" to "_his"
            if k in m2Doc["_his"]:  # Changed "cbHis" to "_his"
                v2 = m2Doc["_his"][k]  # Changed "cbHis" to "_his"
                merged = self.merge_histories(v1, v2)
                if merged != v1:
                    upList.append({k: merged["v"]})
        if upList:
            m1Doc = self.updateDoc(m1Doc, upList)
        return m1Doc