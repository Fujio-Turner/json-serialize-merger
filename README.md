### DATA/JSON IN CONFLICTS
In a JSON databases ,like Couchbase and in particular Couchbase Mobile, when you have a document(s) were two or more people change the same piece of information you get conflicts.

### CUSTOM CONFLICT RESOLUTION (MERGE)
This project will cover timebased stitching/serialzing i.e. merging a document based on field level timestamps.


#### TIMEBASED
A common conflict resolution method is timestamp. The "newest" timestamp between two documents wins. Example on the field BELOW `updated`
```json
{
  "docType":"invoice",
  "name":"Bob Smith",
  "address":"123 Fake St. Lake Falls, MA 8000",
  "apples":10,
  "updated":"2022-01-30T16:52:11.515Z",
  "updatedBy":"customerRep-12345"
}
```
##### FINE GRAIN?

Ok the document has a timestamp ,but what field(s) changed from the update and when did each change happen?

##### FIELD LEVEL TIMESTAMPS
The only way to know what field(s) changed and when is to track / assign a timestamp for the field(s) that changed. Example the JSON ABOVE when you change the field `"name":` FROM `"Robert Smith"` TO `"Bob Smith"` we put inside the document something like `{"field":"name","time":"some date"}` too.

##### USEAGE
In this project its designed to do the bookkeeping information and the merging of two documents with the embedded bookkeeping information to a serialzed or stitch "time correct"<sup>1.</sup> version of documents. 

There are four main methods:
+ 1 `makeNewDoc(JSON)`

This creates and puts the bookkeeping field names & timestamps information document and stores it the document. Just put in a plain JSON document in and out comes the same JSON but with more stuff (bookkeeping data). Now just store that output into the database.

| Input | Output |
|--------|-------|
|```{"docType":"invoice","name":"Bob Smith","address":"123 Fake St. Lake Falls, MA 8000","apples":"red"}```|```{"docType": "invoice", "name": "Bob Smith", "address": "123 Fake St. Lake Falls, MA 8000", "apples": "red", "cbHis": {"name": {"v": "Bob Smith", "t": 1687515677}, "address": {"v": "123 Fake St. Lake Falls, MA 8000", "t": 1687515677}, "apples": {"v": "red", "t": 1687515677}}, "upDtEp": 1687515677}```|

<br/><br/>
+ 2 `updateDoc(JSON,array_of_changes)`

Ok you have a document w/ bookeeping data from the ABOVE, but you want to update/change the document. Just pass that document into the function Plus an array of changes you want to apply `[{"name":"Bob M. Smith"},{"paid":true}]` and it will output the changes in the document with updated bookkeeping information.

|Input: Doc w/ History | Input: Change List |
|--------|-------|
|```{"docType": "invoice", "name": "Bob Smith", "address": "123 Fake St. Lake Falls, MA 8000", "apples": "red", "cbHis": {"name": {"v": "Bob Smith", "t": 1687515677}, "address": {"v": "123 Fake St. Lake Falls, MA 8000", "t": 1687515677}, "apples": {"v": "red", "t": 1687515677}}, "upDtEp": 1687515677}```| ```[{"apples":"blue"},{"nickName":"the guy"}]```|
<br/><br/>
+ 3 `mergeRequest(Your_JSON,Changes_JSON)`

This is a special function because it lets you apply changes from a second document but from another Doc Id and/or docType. Example:   
1st document (Your_JSON): `"docType":"invoice"` <= apply changes from 2nd document to it(Changes_JSON): `"docType":"invoiceUpdates"`
and the function will spit out merged "time correct"<sup>1.</sup> document `"docType":"invoice"` with changes. 
<br/><br/>
+ 4 `blindMerge(JSON_1,JSON_2)`

Lets say you have two documents. In fact the exact same `docType` and docId/Key but with changed/conflicting data. Just put in both of the document/JSON and this function will figure it out and spit out a "time correct"<sup>1.</sup> single document. 


***BONUS***
In the above functions if you have a field called `qty` with an integer as a value when the functions do a merge the output will never be negative the lowest it will go is 0 (zero). You can turn it off if you like chaos :smirk:
<br/><br/>

##### LIMITS
 JSON root level and single field timetracking only.
+ **YES:** `"name":"Bob Smith"` 
+ **NO:** `"zipCode":["111","222"]` , `"address":{"city":"Lake Falls"}`


##### FUTURE
+ non-root level document , array and object merging. Right now only root level single elements can be merged based on timestamp.
+ storing `cbHis` inside Couchbase's [xattrs](https://docs.couchbase.com/server/current/learn/data/extended-attributes-fundamentals.html#3.0@java-sdk:concept-docs:xattr.adoc)
+ AI friendly Source Code for converting the Python code to your favorite programming language.
<br/><br/>

### COMMON OTHER CONFLICT POLICIES
There are many types but most do:
+ **Highest Revision Wins** 
Everytime a document is update a counter ,hidden or not hidden in the document, increases. The Document with the highest counter value wins.
+ **Newest Timestamp Wins**
There is hidden or not hidden value in the document that has a timestamp. So hhe document with the newest one wins.
+ **Vector Clocks**
Click to read more: 
[Vector clocks algorithm is based on vector of tuples ...](https://www.waitingforcode.com/big-data-algorithms/conflict-resolution-distributed-applications-vector-clocks/read)
<br/><br/>
##### NOTES
Personally time based conflict resolution is not my favorite way to resolve conflicts , but some people like the simplicity. 

<sup>1.</sup> You can get clock drift and/or different NPT servers that are off a few seconds or more off. On consumer facing mobile apps users can root their phones and set the system time in the future or the past too.