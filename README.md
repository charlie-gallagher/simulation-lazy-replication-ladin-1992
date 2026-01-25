# Providing high availability using lazy replication

## Quick start
The simulation is pure Python. The entry point is the `node.py` script.

```
python3 node.py
```

## Overview
Original paper: https://www.cs.princeton.edu/courses/archive/spr24/cos418/papers/lazy.pdf

This repo contains a simulated version of the paper "Providing high availability
using lazy replication" by Ladin et al. (1992). The goal is only to help me
learn about the system proposed in the paper and to try to implement it myself,
and more broadly to start building an intuition for vector clocks for dependency
tracking.

The paper describes a distributed system of replicated servers with eventual
consistency through _causal_ relationships between events. The system is
composed of front end code at each client that interacts with any of a set of
replicas. Replicas are symmetric; there is no master. The client makes updates
and occasionally observes the system through queries.

The replication strategy guarantees that the client sees a causally consistent
view of the system regardless of which replica it talks to. If the client makes
an update, it expects to see that update in all future queries. If the client
makes a query, it expects its following updates to take place "after" the view
of the system according to the query. In other words, the client may not see the
most up-to-date view of the system, but time never goes backwards.

Nothing is guaranteed about how quickly updates will propogate through the
system. In the event of a network partition, it's possible for a client to
interact with a replica for a long time without receiving updates from any other
client or replica. But the front end may change replicas, and a query on the new
replica will trigger the replica to wait for (or seek out) gossip about what the
user did and saw with their previous replica.

The system guarantees that the client will see a causally consistent view of the
system, not an up-to-date view. This is more useful in some contexts than
others. The example given in the paper is a mail client, where you don't
necessarily need the most up to date view, but you expect emails you send to be
in your "Sent" mailbox.

Gossip messages are exchanged between replicas to ensure all replicas make
progress towards consistency. WIth no updates, it's practically guaranteed that
all replicas agree on the state of the system.

Causality is ensured through the use of vector clocks for dependency tracking.
Vector clocks represent the set of updates applied to some data `val`; put
differently, they represent exactly one state of the system. In practice, a
vector clock is an array of monotonically increasing integers, where `ts[i]`
represents the number of updates applied at replica `i`.

In the Ladin et al. system, there are a number of vector clocks.

- `rep_ts` is the "time" as this server node understands it. This timestamp
  represents all of the events that it knows about personally via direct actions
from the user and gossip messages. It applies updates in dependency order, and
it may not immediately apply all updates it receives.
- `val_ts` is the set of events that have contributed to the data (the "value").
  This is updated when the value is modified either by a user or by applying
events received via gossip. Where `rep_ts` represents the updates that the
replica knows about, `val_ts` represents the updates that have actually been
applied to `val`.
- `ts_table` contains various `rep_ts` values for each node in the cluster, so
  that `ts_table[i]` is equal to the latest timestamp from server `i` that was
received by the current server via gossip. It's used to decide when a change is
"known everywhere".
- The client (ie a user who makes queries and updates) maintains its own
  timestamp to represent its understanding of the system, and consequently the
changes that it expects to have already taken effect when it makes requests. So,
if a client sends an update to server node `i` and then queries server node `j`,
the latter will see that this client expects to see changes made at `i` in the
query result.

The most basic version of the system is composed of simple, CRDT operations
applied with causality restrictions. The paper also develops stricter operation
types that have better guarantees about how the change is reflected throughout
the system.

- **Causal operations** take into account all previous updates known at the
  client.
- **Forced operations** are performed in the same order at all replicas relative
  to each other.
- **Immediate operations** are performed in the same order at all replicas
  relative to all events in the system.

I have not developed these last two more interesting operation types, only
causal operations.

## Python environment
I decided to try to simulate calculating a simple running total across a set of
nodes. Clients submit updates (increment, decrement, add _n_, subtract _n_) and
queries, and at the end the hope is that all server nodes will contain the same
value.

The program is a single-threaded simulation where time moves in ticks.
Communication between clients and servers occurs via queues.

At each tick:

- Every non-blocked front end decides to submit an update, query the value, or
  choose a new server to communicate with. There's no routing; each front end
has direct access to a list of available server nodes. If the front end submits
an update or query, it sets itself as blocked and prepares to poll for the
result.
- Every server node clears its queues. First, it processes updates, then
  queries, and finally it exchanges (via broadcast, not gossip) "gossip"
messages with the other servers. Queues are all FIFO.

The system proceeds like this in a sort of lock-step rhythm until N ticks have
passed, then the server nodes exchange gossip one more time. Finally, a summary
of the system is printed.

## Comparison to the paper
I did not follow the paper very closely. In particular:

- Front ends have guaranteed message delivery, so there is no concept of a `cid`
  (invocation id), and front end messages are never rejected on the basis of a
timestamp.
- I have implemented neither forced nor immediate operations.
- Servers always wait to receive gossip; they are never proactive about
  requesting it.
- The simulated communication environment is a little too synthetic in my
  opinion.
- I'm using a CRDT update operation (running total), so I haven't worried as
  much about the order in which updates are applied. Normally, this matters.
- I haven't faked the whole architecture. There are no clients, just front ends
  and replicas. The client/front end boundary isn't that interesting (the front
end hides replication and timestamp management from the client), so I dropped
it.

I've recently fixed a few bugs, and now the replicas always agree at the end (as
expected). There may be some other sorting bugs, but like I said, this doesn't
matter with the running total service.

## Configuration
There are a few levers. First, you can change the number of clients and servers,
or the number of ticks. More interestingly, you can choose the ratio of queries
to updates that each front end makes, and when the front end decides to move to
another server.

There's no central config, that's a to-do. If you're interested in the system,
you'll just have to read the code.

---

Charlie Gallagher, January 2026
