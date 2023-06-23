# json-serialize-merger


#### DATA/JSON IN CONFLICTS
In a JSON databases ,like Couchbase and in particular Couchbase Mobile, when you have a document(s) were two or more people change the same piece of information you get conflicts.

### CUSTOM CONFLICT RESOLUTION (MERGE)
This project will cover timebased stitching/serialzing i.e. merging a document based on field level timestamps.


#### TIMEBASED
A common conflict resovle is timestamp. The "newest" timestamp between two documents wins/saved. `updated`
```
{
  "docType":"invoice",
  "name":"Bob Smith",
  "address":"123 Fake St. Lake Falls, MA 8000",
  "apples":10,
  "updated":"2022-01-30T16:52:11.515Z",
  "updatedBy":"customerRep-12345"
}
```
#####FINE GRAIN?

Many times a JSON document will have a timestamp to tell you when the document was last updated. But what changes and when was each change?

###CUSTOM CONFLICT RESOLUTION (MERGE)
This project will cover Timebased Stitching/serialzing.


<br/><br/>

### COMMON/DEFAULT CONFLICT WIN POLICIES
There are many types but most do:
+ **Highest Revision Wins** 
Everytime a document is update a counter ,hidden or not hidden in the document, increases. The Document with the highest counter value wins.
+ **Newest Timestamp Wins**
There is hidden or not hidden value in the document that has a timestamp. So hhe document with the newest one wins.
+ **Vector Clocks**
Click to read more: 
[Vector clocks algorithm is based on vector of tuples ...](https://www.waitingforcode.com/big-data-algorithms/conflict-resolution-distributed-applications-vector-clocks/read)


<br/><br/>

##### NOTE
Personally time based conflict resolution is not my favorite way to resolve conflicts , but some people like the simplicity. You can get clock drift and/or different NPT servers that are off a few seconds or more. On consumer facing mobile apps users can root their phones setting the system time in the future or the past too.