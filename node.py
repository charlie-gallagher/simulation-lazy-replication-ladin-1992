from timestamp import new_timestamp, MultiPartTimestamp
from service import Totaler
import dataclasses
import datetime
import random

@dataclasses.dataclass
class ProcedureCall:
        # Name of the procedure
        name: str
        # Arguments to the procedure
        args: dict


@dataclasses.dataclass
class OperationInfo:
    # Invocation ID
    cid: Any
    # Actual timestamp, for timeouts
    time: datetime.datetime


@dataclasses.dataclass
class UpdateInfo(OperationInfo):
    # Previous timestamp before update was made
    prev: MultiPartTimestamp
    # Information about the update call
    op: ProcedureCall


@dataclasses.dataclass
class AckInfo(OperationInfo):
    pass


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
    def __init__(self, capacity: int = 500) -> None:
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

class QueryQueue:
    def __init__(self, capacity: int = 500) -> None:
        self._queue: List[QueryInfo] = []
        self.capacity = capacity

    def __len__(self):
        return len(self._queue)
    
    @property
    def size(self):
        return len(self._queue)

    def push(self, q: QueryInfo) -> None:
        if self.size >= self.capacity:
            raise QueueFullException("Queue is full")
        self._queue.append(q)

    def pop(self) -> QueryInfo:
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

    def __post_init__(self):
        self.ts_table[self.id] = self.rep_ts

    def summarize(self) -> None:
        print(f"Node ({self.id})")
        print(f"  Log records: {len(self.log)}")
        print(f"  Replica TS: {self.rep_ts}")
        print(f"  Value: {self.val}")
        print(f"  Value TS: {self.val_ts}")
        print(f"  TS Table: {self.ts_table}")
        print(f"  Gossip queue length: {len(self.gossip_queue)}")
        print(f"  Update queue length: {len(self.update_queue)}")
        print(f"  Query queue length: {len(self.query_queue)}")

    def clear_update_queue(self) -> None:
        while True:
            if len(self.update_queue) == 0:
                break
            op_map = {
                "add": self.val.add,
                "subtract": self.val.subtract,
                "incr": self.val.incr,
                "decr": self.val.decr
            }
            op_info, ts = self.update_queue.pop()
            op = op_map[op_info[0]]
            kwargs = op_info[1]
            if kwargs:
                op(**kwargs)
            else:
                op()
            self.rep_ts.incr(self.id)
            current_rep_ts = self.rep_ts.get(self.id)
            ts.set(self.id, current_rep_ts)
            self.val_ts = self.val_ts.merge(ts)


    def process_update(self, update: UpdateInfo) -> Any:
        pass


    def process_query(self, query: QueryInfo) -> Any:
        # TODO: implement QueryInfo
        pass

class FrontEnd:
    def __init__(self, id: int):
        self.id = id
        self.preferred_node = None
        self.prev = None
        self.n_nodes = -1

    def summarize(self) -> None:
        print(f"FrontEnd ({self.id})")
        print(f"  Preferred node: {self.preferred_node.id}")
        print(f"  Prev: {self.prev}")

    def choose_node(self, nodes: List[Node]) -> None:
        self.nodes = nodes
        self.n_nodes = len(self.nodes)
        self.prev = MultiPartTimestamp([0] * self.n_nodes)
        self.preferred_node = nodes[random.randint(0, len(self.nodes) - 1)]

    def choose_new_node(self) -> None:
        self.preferred_node = self.nodes[random.randint(0, len(self.nodes) - 1)]

    def update_val(self) -> bool:
        possible_calls = [
            ("incr", None),
            ("decr", None),
            ("add", {"other": 5}),
            ("subtract", {"other": 3}),
            # Poor man's weighting
            None,
            None,
            None,
            None,
        ]
        chosen_call = possible_calls[random.randint(0, len(possible_calls) - 1)]
        if not chosen_call:
            return False
        # TODO: What should this format be?
        self.preferred_node.update_queue.push((chosen_call, self.prev))
        return True
        


class Cluster:
    def __init__(self, nodes: List[Node], front_ends: List[FrontEnd]) -> None:
        self.t = 0
        self.nodes = nodes
        self.front_ends = front_ends
        self.stats = {
            "updates": 0,
        }
        for fe in self.front_ends:
            fe.choose_node(self.nodes)

    def summarize(self) -> None:
        n_nodes = len(self.nodes)
        n_fe = len(self.front_ends)
        print()
        print("======================")
        print("Summary")
        print(f"  Nodes: {n_nodes}")
        print(f"  Front ends: {n_fe}")
        print(f"  Current time: {self.t}")
        print(self.stats)
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
                if fe.update_val():
                    self.stats["updates"] += 1
                fe.choose_new_node()
            for be in self.nodes:
                be.clear_update_queue()


# Runtime stuff ------------------------------------------------------

def _generate_nodes(n: int = 10):
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
                query_queue=QueryQueue()
            )
        )
    return nodes

def _generate_front_ends(n: int = 25):
    fes = []
    for i in range(n):
        fes.append(FrontEnd(id=i))
    return fes

if __name__ == "__main__":
    nodes = _generate_nodes()
    front_ends = _generate_front_ends()
    cluster = Cluster(nodes=nodes, front_ends=front_ends)
    cluster.run(50)
    cluster.summarize()


