from timestamp import MultiPartTimestamp
from service import Totaler
import dataclasses
import random
from copy import deepcopy
from typing import List, Tuple, Any


@dataclasses.dataclass
class ProcedureCall:
    name: str
    args: dict


@dataclasses.dataclass
class OperationInfo:
    pass
    # Invocation ID
    # cid: Any
    # Actual timestamp, for timeouts
    # time: datetime.datetime


@dataclasses.dataclass
class AckInfo(OperationInfo):
    pass


@dataclasses.dataclass
class UpdateInfo(OperationInfo):
    prev: MultiPartTimestamp
    op: ProcedureCall


@dataclasses.dataclass
class Record:
    # About the operation
    msg: OperationInfo
    # The node that originated the record
    rnode: int
    # Timestamp at rnode when the record was created
    ts: MultiPartTimestamp


class QueueFullException(Exception):
    pass


class GossipQueue:
    def __init__(self, capacity: int = 5000) -> None:
        self._queue: List[Record] = []
        self.capacity = capacity

    def __len__(self):
        return len(self._queue)

    @property
    def size(self):
        return len(self._queue)

    def push(self, r: Record) -> None:
        if self.size >= self.capacity:
            raise QueueFullException("Queue is full")
        self._queue.append(r)

    def pop(self) -> Record:
        return self._queue.pop()


class UpdateQueue:
    def __init__(self, capacity: int = 500) -> None:
        self._queue: List[Tuple] = []
        self.capacity = capacity

    def __len__(self):
        return len(self._queue)

    @property
    def size(self):
        return len(self._queue)

    def push(self, u: Tuple) -> None:
        if self.size >= self.capacity:
            raise QueueFullException("Queue is full")
        self._queue.append(u)

    def pop(self) -> UpdateInfo:
        return self._queue.pop()

    def lpop(self) -> UpdateInfo:
        return self._queue.pop(0)


class QueryQueue:
    def __init__(self, capacity: int = 500) -> None:
        self._queue: List[Tuple[int, MultiPartTimestamp]] = []
        self.capacity = capacity

    def __len__(self):
        return len(self._queue)

    @property
    def size(self):
        return len(self._queue)

    def push(self, q: MultiPartTimestamp) -> int:
        if self.size >= self.capacity:
            raise QueueFullException("Queue is full")
        uid = random.randint(0, 10000)
        self._queue.append((uid, q))
        return uid

    def pop(self) -> Tuple[int, MultiPartTimestamp]:
        return self._queue.pop()


@dataclasses.dataclass
class Node:
    # Identifies the node
    id: int
    log: List[Record]
    # Maintains knowledge of what updates this node has applied
    rep_ts: MultiPartTimestamp
    # Value that is updated
    val: Totaler
    # Timestamp of the value, not necessarily related to rep_ts
    val_ts: MultiPartTimestamp
    # List of CIDs for deduplication purposes
    inval: List[Any]
    # List of mpts's received from other nodes, used to evaluate whether
    # an update is "known everywhere"
    ts_table: List[MultiPartTimestamp]
    gossip_queue: GossipQueue
    update_queue: UpdateQueue
    query_queue: QueryQueue
    other_nodes: List["Node"] = dataclasses.field(default_factory=list)
    query_results: List[Tuple[int, Totaler]] = dataclasses.field(default_factory=list)

    def __post_init__(self):
        self.ts_table[self.id] = self.rep_ts

    def summarize(self) -> None:
        print(f"Node ({self.id})")
        print(f"  Log records: {len(self.log)}")
        print("  First 5 log records:")
        records_to_print = self.log[:5] if len(self.log) >= 5 else self.log
        for r in records_to_print:
            print("    " + str(r))

        print(f"  Replica TS: {self.rep_ts}")
        print(f"  Value: {self.val}")
        print(f"  Value TS: {self.val_ts}")
        print(f"  TS Table: {self.ts_table}")
        print(f"  Gossip queue length: {len(self.gossip_queue)}")
        print(f"  Update queue length: {len(self.update_queue)}")
        print(f"  Query queue length: {len(self.query_queue)}")
        print(f"  Query results length: {len(self.query_results)}")

    def clear_update_queue(self) -> None:
        # Set to an initial value that will never match len(update_queue)
        prev_uq_len = -1
        while True:
            if len(self.update_queue) == 0:
                print("Queue is empty, success!")
                break
            # Prevent infinite loops
            if len(self.update_queue) == prev_uq_len:
                print("Preventing an infinite loop!")
                break
            prev_uq_len = len(self.update_queue)
            op_map = {
                "add": self.val.add,
                "subtract": self.val.subtract,
                "incr": self.val.incr,
                "decr": self.val.decr,
            }
            update_info = self.update_queue.lpop()
            # If update is not ready to be applied, put it back in the queue
            if update_info.prev > self.val_ts:
                print("Update can't be applied! Need more gossip")
                print(update_info)
                self.update_queue.push(update_info)
                continue

            op = op_map[update_info.op.name]
            kwargs = update_info.op.args or {}
            op(**kwargs)
            # Increment self timestamp
            self.rep_ts.incr(self.id)
            # Update u.prev's timestamp for this node using self.rep_ts.get(self.id)
            current_rep_ts = self.rep_ts.get(self.id)
            prev_copy = update_info.prev.copy()
            prev_copy.set(self.id, current_rep_ts)
            update_info.prev = prev_copy
            # Create a record and save it in the log
            self.log.append(
                Record(msg=update_info, rnode=self.id, ts=update_info.prev.copy())
            )
            # Set the timestamp for the value by merging u.prev and val_ts
            self.val_ts = self.val_ts.merge(update_info.prev)

    def clear_query_queue(self) -> None:
        while True:
            if len(self.query_queue) == 0:
                break
            # For now, remove all queue elements and write val to results
            uid, ts = self.query_queue.pop()
            self.query_results.append((uid, self.val))

    def ack_query_result(self, id: int) -> None:
        self.query_results = [x for x in self.query_results if x[0] != id]

    def send_gossip(self) -> None:
        if not self.other_nodes:
            return
        # Send all of this node's log records to all other nodes
        for n in self.other_nodes:
            for r in self.log:
                if r.rnode == self.id:
                    n.gossip_queue.push(deepcopy(r))

    def clear_gossip_queue(self) -> None:
        # What to do here?
        pass


class FrontEnd:
    def __init__(self, id: int):
        self.id = id
        self.preferred_node = None
        self.prev = None
        self.nodes = dataclasses.field(default_factory=list)
        self.n_nodes = -1
        # Values seen so far (after successful polling)
        self.seen_vals = []
        # If True, waits for polling to complete
        self.blocked = False
        # A UID to poll self.preferred_node for
        self.poll_id = None
        # Current number of poll attempts
        self.poll_attempts = 0
        # Max attempts before giving up on a query
        self.max_poll_attempts = 5
        self.stats = {
            "updates": 0,
            "query_starts": 0,
            "query_completes": 0,
            "failed_polls": 0,
        }

    @property
    def last_seen_val(self) -> Totaler:
        return self.seen_vals[-1] if self.seen_vals else None

    def summarize(self) -> None:
        print(f"FrontEnd ({self.id})")
        print(f"  Preferred node: {self.preferred_node.id}")
        print(f"  Prev: {self.prev}")
        print(f"  Is blocked: {self.blocked}")
        print(f"  Last received value: {self.last_seen_val}")
        print(f"  Seen vals: {self.seen_vals}")
        print(f"  Stats: {self.stats}")

    def choose_node(self) -> None:
        self.n_nodes = len(self.nodes)
        self.prev = MultiPartTimestamp([0] * self.n_nodes)
        self.preferred_node = nodes[random.randint(0, len(self.nodes) - 1)]

    def choose_new_node(self) -> None:
        self.preferred_node = self.nodes[random.randint(0, len(self.nodes) - 1)]

    def update_val(self) -> bool:
        possible_calls = [
            ProcedureCall(name="incr", args={}),
            ProcedureCall(name="decr", args={}),
            ProcedureCall(name="add", args={"other": 5}),
            ProcedureCall(name="subtract", args={"other": 3}),
            # Poor man's weighting
            None,
            None,
            None,
            None,
        ]
        chosen_call = possible_calls[random.randint(0, len(possible_calls) - 1)]

        if not chosen_call:
            return False

        self.preferred_node.update_queue.push(
            UpdateInfo(prev=self.prev.copy(), op=chosen_call)
        )
        # TODO: need to get a new self.prev value by getting a response from
        #       the replica. Use polling like with queries.
        self.stats["updates"] += 1
        return True

    def query_val(self) -> None:
        self.stats["query_starts"] += 1
        self.poll_id = self.preferred_node.query_queue.push(self.prev)
        self.blocked = True

    def poll_for_val(self) -> bool:
        self.poll_attempts += 1
        if self.poll_attempts > self.max_poll_attempts:
            self.stats["failed_polls"] += 1
            self._clear_poll_state()

        for id, val in self.preferred_node.query_results:
            if self.poll_id == id:
                self.seen_vals.append(deepcopy(val))
                self.preferred_node.ack_query_result(self.poll_id)
                self.stats["query_completes"] += 1
                self._clear_poll_state()
                return

    def _clear_poll_state(self) -> None:
        self.poll_id = None
        self.blocked = False
        self.poll_attempts = 0


class Cluster:
    def __init__(self, nodes: List[Node], front_ends: List[FrontEnd]) -> None:
        self.t = 0
        self.nodes = nodes
        self.front_ends = front_ends
        self.stats = {
            "updates": 0,
        }
        for fe in self.front_ends:
            fe.choose_node()

    def summarize(self) -> None:
        n_nodes = len(self.nodes)
        n_fe = len(self.front_ends)
        print()
        print("======================")
        print("Summary")
        print(f"  Nodes: {n_nodes}")
        print(f"  Front ends: {n_fe}")
        print(f"  Current time: {self.t}")
        print(f"  Stats: {self.stats}")
        print("--------------------------")
        for fe in self.front_ends:
            fe.summarize()
        print("--------------------------")
        for node in self.nodes:
            node.summarize()
        print("======================")

    def run(self, n_ticks):
        for i in range(n_ticks):
            self.t = i
            for fe in self.front_ends:
                if fe.blocked:
                    fe.poll_for_val()
                    # Bugfix: only choose new node after finishing work
                    #         with current node
                    fe.choose_new_node()
                else:
                    if fe.update_val():
                        self.stats["updates"] += 1
                    fe.query_val()
            for be in self.nodes:
                be.clear_gossip_queue()
                be.clear_update_queue()
                be.clear_query_queue()
                be.send_gossip()


# Runtime stuff ------------------------------------------------------


def _generate_nodes(n: int):
    nodes = []
    for i in range(n):
        nodes.append(
            Node(
                id=i,
                log=[],
                rep_ts=MultiPartTimestamp([0] * n),
                val=Totaler(),
                val_ts=MultiPartTimestamp([0] * n),
                inval=[],
                ts_table=[MultiPartTimestamp([0] * n) for _ in range(n)],
                gossip_queue=GossipQueue(),
                update_queue=UpdateQueue(),
                query_queue=QueryQueue(),
            )
        )
    return nodes


def _generate_front_ends(n: int):
    fes = []
    for i in range(n):
        fes.append(FrontEnd(id=i))
    return fes


if __name__ == "__main__":
    nodes = _generate_nodes(3)
    front_ends = _generate_front_ends(10)
    # Tell FEs and nodes about other nodes
    for fe in front_ends:
        fe.nodes = nodes
    for node in nodes:
        id = node.id
        node.other_nodes = [x for x in nodes if x.id != id]
    cluster = Cluster(nodes=nodes, front_ends=front_ends)
    cluster.run(10)
    cluster.summarize()
