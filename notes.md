# Distributed computing simulation
I'm imagining a simulation where you have a cluster of nodes that all try to get
in sync using some sort of eventual consistency algorithm, maybe taking notes
from the system designed in the paper I'm reading (Ladin, et al. 1992).

A cluster of nodes and a front end that receives requests.

# Lazy replication
Nodes are connected by a communication network. Occasional failures, but for now
assume none. Service is a set of replicas, hidden from clients by a front end
that runs at client nodes. The FE picks a replica to communicate with. Replicas
communicate through gossip messages.

Update operations modify but don't read; query operations read but don't update.
Assume fixed replicas and correct routing from FE to some appropriate replica.

There are 3 types of operation:

- Causal
- Forced
- Immediate

Causal operations respect causality. Forced operations are performed in the same
order with respect to each other at all replicas. Immediate operations are
performed at all replicas in teh same order relative all other operations.

When you submit an update message, the response contains a _uid_. This names the
invocation. Every operation takes a set of of uids as an argument, called the
_label_. This identifies the updates whose execution must precede the execution
of the operation. Query operations tell you both the answer you queried for and
the updates that were active when that query was evaluated.

Here's my attempt at a small version of this:

```
Node 1
--------------
label=[]
update(label, insert 1) -> 001
label.append(001)
update(label, insert 2) -> 002
label.append(002)

Node 2
--------------
label=[]
update(label, insert 3) -> 003
label.append(003)

(Nodes 1 and 2 exchange updates)

Node 1 again
--------------
query(label, sum) -> newl[001, 002, 003], sum=6
label=newl
```

The service (nodes) is defined as a sequence of events "one event for each
update and query operation performed by a front end on behalf of a client." At
some point between invocation and return of the service procedure, an event is
appended to the sequence. Queries are defined by the input label, operation,
result value, and result label. Updates are defined by the input label,
operation, and uid returned for that operation.

e is an event, E is an execution sequence, and P(e) is the set of events that
precede e. For some set S of events, S.label defines the set of uids of update
events in S.

Operations not constrained by `dep` are performed in arbitrary order.

"Note that this clause guaranteess that if the returned label is used later as
input to another query, the result of that query will reflect the effects of all
updates observed in the earlier query." This seems to say that reads within a
session are monotonically increasing.

The front end maintains the label. It sends its label in every call message and
merges new uids in the response via union. This one's more interesting. "The
front end intercepts all messages exchanged between its clients and other
clients. It adds its label to each message its client sends and merges the label
in each message received by its client with its label." The front end seems like
a bottleneck here, but its workload is very light, so that's acceptable.

"During normal operation a front end will always contact the same 'preferred'
replica." Then there are failure modes that get handled through retries, and
there's some special handling of this. "In spite of these duplicates, update
operations must be performed at most once at each replica." Each request gets a
unique cid attached to it, even for multiple copies of the same request.

Need: compact representation of a label, a fast way to determine when an
operation is "ready to be executed." Independent generation of UIDs. This paper
uses a multi-part timestamp

```
t = <t1, t2, ..., tn>
```

Where `n` is the number of replicas. Nonnegative integer counter, initially all
set to 0. Compare by looking at the value of each element. Merge by taking the
component-wise maximum. "Every update operation is assigned a unique multipart
timestamp as its uid. A label is created by merging timestamps; a label
timestamp _t_ identifies the updates whose timestamps are less than or equal to
_t_."

Let me see if I understand correctly. For now, I'll assume that all operations
have distinct timestamps.

```
User
----
insert 1

FE
--------------
label=[0, 0]
(node 1) update(label, insert 1)
label[1] = NOW()  # label=[001, 0]

User
----
insert 2

FE
--------------
label=[001, 0]
(node 1) update(label, insert 2)
label[1] = NOW()  # label=[004, 0]


User
----
insert 3

FE
--------------
label=[004, 0]
(node 2) update(label, insert 3)
label[2] = NOW()  # label=[004, 005]



(Nodes 1 and 2 exchange updates)
FE
--------------
Intercepts message from 1 to 2, 2 to 1, and does what? Adds its label to it.
Then, there's also 1 FE per client, right? "A replica receives call messages
from front ends..." That's plural, front ends.



User
----
query sum

FE
--------------
label=[004, 005]
(node 1) query(label,sum)
```

Things aren't totally clear yet. Let me keep reading.

A replica receives call messages from FEs and gossip messages from other
replicas. For a call message, it assigns the update a timestamp and appends
information about it to its log. The log also includes gossip -- reported
updates from other replicas that were propogated to this one. "A replica
maintains a local timestamp, `rep_ts`, that identifies the set of records in its
log and thus expresses the extent of its knowledge about updates. It increments
its part of the timestamp each time it processes an update call message;
therefore, the value of the replica's part of `rep_ts` corresponds to the number
of updates it has processed. It increments other parts of `rep_ts` when it
receives gossip from other replicas. The value of any other part i of `rep_ts`
counts the number of updates processed at replica i that have propagated to this
replica via gossip." That's a block quote because it seems important.

A timestamp is just a counter, kinda.

Ok, so what does this get you? It's a vector clock. Is that different from a
label? This is maintained by the _replica_ not a front end. The replica is the
one that actually has to apply updates and keep track of what is has and hasn't
done. The front end, I think, has to maintain causality. But it only sees what
happens in its session, right? The log is a set of updates. `rep_ts` identifies
the set of records in its log. "It increments its part of the timestamp each
time it processes an update call message." So call it a monotonically increasing
number, and I'm not sure how causality works here, but seems like it doesn't
matter _when_ an update is applied, or the order of application. If two nodes
have the same updates, they'll have the same value for `rep_ts`, but the reverse
isn't true.

Updates come from either a call or gossip; the replica knows about all calls
that it handles itself, but only knows about some of the calls other replicas
have handled. So, is the state of the system uniquely defined by the set of
clocks across all nodes? If the timestamp is monotonically increasing, then it
uniquely identifies a state of a replica. So, yes, this works. Interesting. You
can fully determine the updates in a replica's log through the set of timestamps
it knows about. Let me work through a case.

Suppose A gets updates 1 and 2 (t=2), B gets 3 and 5 (t=2), and C gets 4 (t=1).
Without any communication between nodes, the clocks look like this.

```
A=(2, 0, 0)
B=(0, 2, 0)
C=(0, 0, 1)
```

If A and B exchange gossip, then you get:

```
A=(2, 2, 0)
B=(2, 2, 0)
C=(0, 0, 1)
```

By consulting B, you can now tell that A has processed events 3 and 5; by
consulting A, you can tell that B has processed 1 and 2. Neither has processed
an event by C, which is still set to the default.

This makes sense! And it only took me a few tries to understand it. I found this
youtube video that I'd like to watch to see if I still feel like I understand: 
https://www.youtube.com/watch?v=o4lnE5yI6Po

Now, dependency tracking. "A replica executes updates in dependency order and
maintains its current state in `val`. When an update is executed, its uid
timestamp is merged into the timestamp `val_ts`, which is used to determine
whether an update or query is ready to execute; an operation op is ready if its
label `op.prev <= val_ts`."

Here's a summary of state.

- node ID
- Set of log records
- `rep_ts`, which is a mpts
- `val_ts`, another mpts
- `val` "replica's view of service state", the object being tracked
- `inval`, set of cids, updates that participated in computing val
- `ts_table`, sequence of mpts. `ts_table(p)` is the latest multipart timestamp
  received from p. (What's p? Another replica? Yes, replica.)

Adding complication, we need to control the size of the log and `inval`. "An
update record can be discarded from the log as soon as it is known everywhere
adn has been reflected in `val`." An update u is known to be everywhere if the
replica received gossip messages from everyone else about u. "Each gossip
message includes enough of the sender's log to guarantee that when the receiver
receives record u from replica i, it has also received... all records processed
at i before u. Therefore, if a replica has heard about u from all other
replicas, it will know about all updates that u depends on, since these must
have been performed before u... Therefore, u will be ready to execute."

So replicas exchange log records, it seems like. And replicas are responsible
for ensuring that if they tell another replica about u, they also already told
that replica about all records that u depends on. Is that the gist here? I mean,
that's not an easy problem by any means -- gossip messages are occasional and
might get lost, so I'm not sure how replicas guarantee that if it sends update
`u`, it also sends its dependencies.

The `ts_table` is used to figure out what updates have been received everywhere.
This is a sequence of multipart timestamps, and in it you can access the latest
received mpts from replica i. "Every record r contains the identity of the
replica that created it in field r.node." The author is referring to log records
here. To figure out whether an update has been processed everywhere, you simply
have to check if the mpts entry for that replica in all received gossip messages
is at least as great as the entry noted by the record (r.ts).

I think I have the intuition here before the words; let me try again.

A record `r` is known everywhere if for all replicas `j`, `ts_table(j)[r.node]
>= r.ts[r.node]`. This is pretty concise but it's easy enough to understand. The
state of replica `j` is completely determined by its own entry in the multipart
timestamp (and there are abundant instances of this data structure). The log
record `r` identifies the node that created it originally and the mpts of that
node when it was created. Thus, `r.ts[r.node]` represents the exact state of the
replica that processed `r`, and if there exists a replica `j` where
`ts_table(j)[r.node] < r.ts[r.node]`, then the current replica has not yet
received enough updates from that replica -- the communication between these
replicas is lagging.

Remember that this is just about pruning the log to its essential parts, not
about consistency checks. But it's also good for that, I'd guess.

There's another log of cids that must be kept in check over time. A cid is added
to `inval` so that duplicates can be ignored, and that means there needs to be
an upper limit on how late a record can be received and still be processed.
Imagine getting a copy of request R at t=0, then at t=5 you get another, and so
on every 5 seconds. They all have the same cid. If you successfully processed R
at t=0, then all future updates are duplicates and should be ignored. You have
to set a timeout on R such that you can tell _even without a record in inval_
that you shouldn't process it.

Replicas use acks to acknowledge receipt of a cid. Acks are logged and
gossipped. There's an important refinement here for crashes, but I'm going to
ignore it for now. Each ack and update message has a time at which is was
created (in the form of a mpts). The ack's timestamp must be later than the
update's timestamp, and you can time out an update if its timestamp is too old.

"A replica can discard a cid c from inval as soon as an ack for c's update is in
the log and all records for c's update have been discarded from the log." The
first (ack is in the log) "guarantees a duplicate call message will not be
accepted; the latter guarantees a duplicate will not be accepted from gossip."

How does gossipping (sp?) manage acks and updates? An ack might stay in the log
while the update is dropped, and this inconsistent state can inform you that the
update was already applied and that all replicas have it.

Let me work on this for a second. There's room for a conflict if replicas A and
B both receive an update an apply it before learning that the other received the
same request. Updates and acks are the two types of log message. An ack only
contains (in the log) the cid and the timestamp. Meanwhile an update record
contains the previous mpts, op, cid, and timestamp. Both have cid, which
uniquely identifies a request, but doesn't uniquely identify the _receipt_ of a
request at a particular replica; that's done by the timestamp associated with
this message. "Acks are added to the log when they arrive at a replica and are
propagated to other replicas in gossip." If our two replicas both apply cid `c`,
then they're more or less consistent, although they might've applied the update
under different circumstances. CRDTs help. Oh! I had something backwards. "The
front end does this by sending an acknowledgment message _ack_ containing the
cid of the update to one or more of the replicas." It's the front end that sends
an ack.

Here's what's happening. A FE sends an update, and keeps sending it until it
receives a reply. A replica replies (or maybe multiple replicas reply) and then
the FE sends an ack. I'm not sure what purposes the ack serves in total -- it
definitely helps put an upper limit on the inval list entries, but does it also
help with conflict resolution? Seems like it might, though not entirely. What if
multiple replicas receive an ack for the same cid, both log it? They'll have
different timestamps, but the updates will be duplicated across replicas, no?
This is a fundamental feature of the approach, but I'm still not sure how it's
resolved in practice.

Acks and updates are accompanied by the current FE node's clock, to order the
messages (messages may arrive out of order, so FE clock is authority on order).
If mulitple updates are sent for a single cid, they all have different
timestamps; you can probaly use LWW (last write wins) in this case to solve
conflicts.

### Implementation and processing
Log and inval are hash tables on `cid`. Initially, all timestamps are 0'd and
`val` is some initial value.

When an update message is received, it may be discarded (late or duplicate). If
not discarded, then:

1. Advance local timestamp `rep_ts[i]`.
2. Compute timestamp for the update, `ts`, by updating `u.prev` with
   `rep_ts[i]`.
3. Construct the update record `r`. Add it to the local log.
4. Execute u.op if all the updates that u depends on have already been
   incorporated into val. This is the case if `u.prev <= val_ts`. Apply, then
merge `val_ts` and `r.ts`. Add cid to inval.
5. Return update's timestamp `r.ts` in a reply message.

There's definitely some subtlety here. The local timestamp `rep_ts[i]` is
updated, and it stays isolated. To calculate the timestamp for the update, you
use `u.prev`, and you don't know a lot about this timestamp. Even still, you
update `u.prev[i] = rep_ts[i]` and leave the other parts (`!= i`) alone. This is
why the text says "The `rep_ts` and the timestamp `r.ts`... are not necessarily
comparable." The whole timestamp for `u.prev` may include updates that were made
at another replica that have not been applied here, and updates made here may
not be a dependency of u, so it could go either way. If you compared the
timestamps, some fields may be higher at the replica, others higher at the
update, and so you get a mixed result. But you can compare `u.prev` to `val_ts`,
apparently. We haven't modified `val_ts` when the comparison happens, so if it's
not driven by updates, it must be driven by gossip. If `u.prev` is 0 and
`val_ts` is default (0), you're good to go. If this is a new node, it has to get
up to date, and any non-zero `u.prev` will force the node to wait for updates
that `u` depends on.

`r.ts[i]` is set to the same value as `rep_ts[i]`. The rest of the timestamp
comes from `u.prev`, so in pseduocode:

```py
# Init
n_replicas = 5
i = 1  # Me
rep_ts = new_timestamp(n_replicas)
val_ts = new_timestamp(n_replicas)
ts_table = [new_timestamp(n_replicas)]
val = 0
log = {}
inval = {}

# Generate log record
rep_ts.incr(i)
ts = u.prev.copy()
ts.set(i, rep_ts.get(i))
r = make_record(u, i, ts)
log.append(r)

# Perform action (if able)
if u.prev <= val_ts:
    val = apply(val, u.op)
    val_ts = val_ts.merge(r.ts)
    # Also: update inval

respond(r.ts)
```

- `rep_ts` is updated in two ways: gossip and increments during updates.
- `val_ts` is apparently always comparable with `r.ts`. This seems to be because
  `val_ts` is only modified by merging with `r.ts`. `r.ts` represents the
update's previous multipart timestamp, plus the recently incremented tick for
the current replica's slot.
- The log records timestamp is defined _mostly_ by `u.prev`, but with an update
  equivalent to `u.prev.set(i, rep_ts.get(i))`.

Why does the replica maintain `rep_ts`? Why is the log record defined by
`u.prev`? Are `u.prev` and `val_ts` always comparable?

`rep_ts` maintains the state of the replica. It's used to track gossip and it
stores the current value of the local replica's timestamp part. `u.prev`
contains the timestamp as known by the FE that sent the record. It represents
causality for the update -- it's possible that `u.prev` contains some updates
that replica `i` does not know about yet, but the update depends on them. Note
that it's also possible for `rep_ts` to contain a later timestamp for some
replicas than `u.prev`, so they are not always comparable. The log entry for `u`
is the `u.prev` plus an updated timestamp for replica `i`, which fully describes
the system _after_ applying this update at replica `i`. The record also notes
that it was made at replica `i`, which gives you traceability.

_However_, even though the record contains the right version number for replica
`i`, it does not contain the current version of `rep_ts`. Rather, it represents
the state of the system **as the FE knows it**, and so presents a consistent
view to the FE. It's closer to the "correct" view of the system. This is also
the timestamp that feeds `val_ts` (if we are allowed to proceed with updating
`val`).

I've learned... Most importantly, I've learned that `ts_table` is a table of
multi-part timestamps, with (I believe) one entry for each node in the system. I
read through the rest of the paper, and some things are clearer, while others
are not. For example, what if an update is not ready to be applied? Do you wait
to apply it, reject it, what? The authors also mentioned an implementation but I
did not find one. It's also still unclear to me how the front end interacts with
the nodes, and all its "intercept" business.

The goal of the system is to provide consistency while also enabling parallel
work. I believe the system is partially ordered rather than wholly ordered --
but I still need to clarify some of the semantics here.

In any case, I have nearly enough to start an implementation.

## Once more from the top!
Some interesting quotes:

"Consistency of replicated state can be guaranteed by forcing service operations
to occur in the same order at all sites. However, some applications can preserve
consistency with a weaker, causal ordering, leading to better performance."
There's a reference here to Lamport's _Time, clocks, and the ordering of events
in a distributed system_.

The `ts_table` _is_ a list of other nodes' timestamps. Also the whole
client-to-client communication part (where the front end intercepts all
client-to-client message) is just plain confusing. It refers to _clients_ not
replicas, and what happens when clients directly communicate. I haven't found an
explanation for why that happens or when.

There's more detail about what happens when updates are and are not ready to be
applied, and how updates are applied to `val` in the right order. "A replica
executes updates in dependency order and maintains its current state in _val_.
When an update is executed, its uid timestamp is merged into the timestamp of
`val_ts`, which is used to determine whether an update or query is ready to
execute; an operation _op_ is ready if its label `op.prev <= val_ts`."

The pieces are really starting to fit together now. The user is never exposed to
an inconsistent view of the world. They make claims about how the world should
be by using their label (timestamp), and they get informed about the state of
the _whole_ world when they receive information about a query. After a query,
they get a timestamp that precisely identifies the information they were shown.
Causality is maintained because a user is exposed to things they have either
done themselves or have seen before (plus some other things). They don't lose
their own updates. I'm interested in some of the proofs that the system makes
progress, and I'm not sure how the system works under partition conditions. I'm
also not sure about conflicts -- when I update X and so does someone else. What
operation types are allowed? Still some things I have to learn, clearly.




---

Charlie Gallagher, December 2025
