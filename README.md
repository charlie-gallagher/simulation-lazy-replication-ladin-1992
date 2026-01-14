# Providing high availability using lazy replication

Original paper: https://www.cs.princeton.edu/courses/archive/spr24/cos418/papers/lazy.pdf

This repo contains a simulated version of the paper "Providing high availability
using lazy replication" by Ladin et al. (1992). The goal is only to help me
learn about the system proposed in the paper and to try to implement it myself.

The paper describes a distributed system of replicated servers with eventual
consistency through _causal_ relationships between events. Each client node sees
a consistent view of the system (read-your-writes, preserved session order,
etc.). This is done through the use of vector clocks (see `timestamp.py`). The
idea with vector clocks is that each server node keeps track of all other nodes
in the system and how it relates to them. Vector clocks are vectors of
monotonically increasing integers, where `x[i]` represents the number of
operations processed at server `i`.

The article does a better job explaining vector clocks concisely than I can. But
a few interesting bits to note. In the Ladin et al. system, there are a number
of vector clocks in play.

- `rep_ts` is the "time" as this server node understands it. This timestamp
  represents all of the events that it knows about personally via direct actions
from the user and gossip messages (in my system, I actually use broadcast
messages).
- `val_ts` is the set of events that have contributed to the data (the "value").
  This is updated when the value is modified either by a user or by applying
events received via gossip. The relationship between `rep_ts` and `val_ts` is
subtle.
- `ts_table` contains various `rep_ts` values for each node in the cluster, so
  that `ts_table[i]` is equal to the latest timestamp from server `i` that was
received by the current server via gossip. It's used to decide when a change is
"known everywhere".
- The client maintains its own timestamp to represent its understanding of the
  system, and consequently the changes that it expects to have already taken
effect when it makes requests. So, if a client sends an update to server node
`i` and then queries server node `j`, the latter will see that this client
expects to see changes made at `i` in the query result.

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

I have not developed these last two, more interesting operation types, only
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

- The log grows without bound.
- Front ends have guaranteed message delivery, so there is no concept of a `cid`
  (invocation id), and front end messages are never rejected on the basis of a
timestamp.
- I have not implemented forced or immediate operations.
- Servers always wait to receive gossip; they are never proactive about
  requesting it.
- The simulated communication environment is a little too synthetic in my
  opinion, but it works -- in the end, all servers have the same value.

I'm planning on adding a bound to the log some time soon, but the others are
probably not going to make it into the simulation.

## Configuration
How do you tweak the system? There are a few levers. First, you can change the
number of clients and servers, or the number of ticks. More interestingly, you
can choose the ratio of queries to updates that each front end makes, and when
the front end decides to move to another server.

Each server also has a configurable likelihood that they will miss gossip
messages during this tick, which makes the system more interesting and a little
less predictable and lock-step.

There's no central config, that's a to-do. If you're interested in the system,
you'll just have to read the code.

---

Charlie Gallagher, January 2026
