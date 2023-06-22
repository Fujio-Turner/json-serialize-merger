import json
from datetime import datetime
class JSONMERGE():

	noCheck = {"cbHis", "docType"}
	addCrLoc = False
	addUpLoc = False
	addUpIso = False
	addCrIso  = False
	addCrEp = True
	qtyMath = True
	def __init__(self):
		self.addUpLoc = False

	def makeTime(self):
		now = datetime.utcnow()
		return {"ep":int(now.timestamp()),"utc":now,"iso":now.astimezone().isoformat()}

	def qtyMath(self,newestQty,oldestQty):

		if oldestQty - newestQty > 0:
			return {"qty": 0, "exceptionQty": False}
		if oldestQty - newestQty == 0:
			return {"qty":0,"exceptionQty":False}
		if oldestQty - newestQty < 0:
			return {"qty":0,"exceptionQty":True}

	def makeNewDoc(self,newDoc):
		docTime = self.makeTime()
		history = {}
		for k, v in newDoc.items():
			if k in self.noCheck:
				continue
			history[k] = {"v": v, "t": docTime["ep"]}

		newDoc["cbHis"] = history
		newDoc["upDtEp"] = docTime["ep"]
		if self.addUpIso:
			newDoc["upDt"] = docTime["iso"]
		if self.addCrIso:
			newDoc["upCr"] = docTime["iso"]
		if self.addCrEp:
			newDoc["upCrEp"] = docTime["ep"]
		return newDoc

	def updateDoc(self,doc, changes):
		docTime = self.makeTime()
		doc["upDtEp"] = docTime["ep"]
		if self.addUpIso:
			doc["upDt"] = docTime["iso"]

		for x in changes:
			if list(x)[0] in self.noCheck:
				continue
			a = doc["cbHis"].get(list(x)[0])
			if a:
				if list(x.values())[0] != a['v']:
					doc[list(x)[0]] = list(x.values())[0]
					doc["cbHis"][list(x)[0]] = {"t": docTime["ep"], "v": list(x.values())[0]}
			else:
				doc[list(x)[0]] = list(x.values())[0]
				doc["cbHis"][list(x)[0]] = {"t": docTime["ep"], "v": list(x.values())[0]}
		return doc

	def mergeDocReq(self,doc1,doc2):
		#which doc is newer
		mDoc = doc1
		upList = []
		for k,v in doc1["cbHis"].items():
			if k in doc2["cbHis"]:
				#are the same value
				if v["v"] != doc2["cbHis"][k]["v"]:
					if doc2["cbHis"][k]["t"] >= v["t"]:
						##print('doc2 is newer doc2Time: ',doc2["cbHis"][k]["t"],' doc1Time: ',v["t"])
						if k != "qty":
							upList.append({k: doc2["cbHis"][k]["v"]})
						else:
							if self.qtyMath == True:
								qty = self.qtyMath(v["v"],doc2["cbHis"][k]["v"])
								upList.append({k: qty["qty"]})
							else:
								upList.append({k: doc2["cbHis"][k]["v"]})
		if upList:
			mDoc = self.updateDoc(doc1,upList)
		return mDoc

	def mergeDocReal(self,doc1,doc2):
		#which doc is newer
		d1 = False
		d2 = False
		if doc1["upDtEp"] >= doc2["upDtEp"]:
			m1Doc = doc1
			m2Doc = doc2
			d1 = True
		else:
			m1Doc = doc2
			m2Doc = doc1
			d2 = True
		upList = []
		for k,v in m1Doc["cbHis"].items():
			#print(k,v)
			if k in m2Doc["cbHis"]:
				if m2Doc["cbHis"][k]["t"] >= v["t"]:
					print('m2 is newer',m2Doc["cbHis"][k]["t"],v["t"])
					upList.append({k:v["v"]})
				else:
					print('m1 is newer', m2Doc["cbHis"][k]["t"], v["t"])

		print(upList)
				#if m2Doc["cbHis"][k][t] >= v :
		return m1Doc



if __name__ == "__main__":

	a = JSONMERGE()

	doc1 = {
		"docType":"invoice",
		"fName":"fujio",
		"lName":"turner",
		"apples":20,
		"upDtEp":1687323105,
		"upDt":"2023-06-21T04:51:45.000Z",
		"cbHis":{
					"apples":{"t":1687323105,"v":20},
					"fName":{"t":1687323105,"v":"fujio"},
					"lName":{"t":1687323105,"v":"turner"}
					}
	}

	changes = [{"apples":10}]

	##makeChange = a.updateDoc(doc1,changes)
	##print(json.dumps(makeChange))


	doc2 = {
		"docType": "profile",
		"fName": "fujio",
		"lName": "turner",
		"email": "aaaa@aaaa.com"
	}

	#newDoc = a.makeNewDoc(doc2)
	#print(json.dumps(newDoc))



	doc3 = {
		"docType":"invoiceRequest",
		"fName":"cake",
		"lName":"turner",
		"apples":10,
		"upDtEp":1687404176,
		"cbHis":{
					"apples":{"t":1687404176,"v":10},
					"fName":{"t":1687404176,"v":"cake"},
					"lName":{"t":1687323105,"v":"turner"}
					}
	}

	merge = a.mergeDocReq(doc1,doc3)
	print(json.dumps(merge))