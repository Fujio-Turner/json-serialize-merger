
from datetime import datetime


doc1 = {
	"docType":"invoice",
	"fName":"fujio",
	"lName":"turner",
	"apples":20,
	"updatedDt":1687323105,
	"cbHistory":{
				"apples":{"t":1687323105,"v":20},
				"fName":{"t":1687323105,"v":"fujio"},
				"lName":{"t":1687323105,"v":"turner"}
				}
}


changes = [{"apples":10}]

##proposed change function ###
## reserved JSON not to check
noCheck = {"cbHistory","docType"}
addLoc = False

def proChange(oldDoc,changes):
	now = datetime.now()
	dt = int(now.timestamp())
	doc = oldDoc

	doc["updatedDt"] = dt

	for x in changes:
		if list(x)[0] in noCheck:
			continue
		a = oldDoc["cbHistory"].get(list(x)[0])
		if a :
			if list(x.values())[0] != a['v']:
				doc[list(x)[0]] = list(x.values())[0]
				doc["cbHistory"][list(x)[0]] = {"t":dt,"v":list(x.values())[0]}
		else:
			doc[list(x)[0]] = list(x.values())[0]
			doc["cbHistory"][list(x)[0]] = {"t":dt,"v":list(x.values())[0]}
	return doc
	
makeChange = proChange(doc1,changes)

print(json.dumps(makeChange))
