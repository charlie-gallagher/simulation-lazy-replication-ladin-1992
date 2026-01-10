from typing import List


def new_timestamp(n_replicas: int) -> "MultiPartTimestamp":
    return MultiPartTimestamp([0] * n_replicas)


class MultiPartTimestamp:
    def __init__(self, parts: List[int]) -> None:
        self.parts = parts

    def __repr__(self):
        return str(self.parts)

    def __str__(self):
        return str(self.parts)

    def __len__(self):
        return len(self.parts)

    def __eq__(self, other) -> bool:
        if other.__class__ is self.__class__:
            return all([x == y for x, y in zip(self.parts, other.parts)])
        raise NotImplementedError()

    def __ne__(self, other) -> bool:
        if other.__class__ is self.__class__:
            return any([x != y for x, y in zip(self.parts, other.parts)])
        raise NotImplementedError()

    def __lt__(self, other) -> bool:
        if other.__class__ is self.__class__:
            return all([x <= y for x, y in zip(self.parts, other.parts)]) and any(
                [x < y for x, y in zip(self.parts, other.parts)]
            )
        raise NotImplementedError()

    def __le__(self, other) -> bool:
        if other.__class__ is self.__class__:
            return all([x <= y for x, y in zip(self.parts, other.parts)])
        raise NotImplementedError()

    def __gt__(self, other) -> bool:
        if other.__class__ is self.__class__:
            return all([x >= y for x, y in zip(self.parts, other.parts)]) and any(
                [x > y for x, y in zip(self.parts, other.parts)]
            )
        raise NotImplementedError()

    def __ge__(self, other) -> bool:
        if other.__class__ is self.__class__:
            return all([x >= y for x, y in zip(self.parts, other.parts)])
        raise NotImplementedError()

    def incr(self, part: int) -> None:
        self.parts[int(part)] += 1

    def get(self, part: int) -> int:
        return self.parts[int(part)]

    def set(self, part: int, t: int) -> None:
        self.parts[int(part)] = t

    def merge(self, other: "MultiPartTimestamp") -> "MultiPartTimestamp":
        """Merge timestamps by taking the component-wise maximum"""
        return MultiPartTimestamp(
            [max([x, y]) for x, y in zip(self.parts, other.parts)]
        )

    def copy(self) -> "MultiPartTimestamp":
        return MultiPartTimestamp(self.parts.copy())

    def compare(self, other: "MultiPartTimestamp") -> int | None:
        """
        Compare this clock with another.

        Returns:
            -1  if self < other   (happens-before)
             0  if self == other
             1  if self > other   (happens-after)
             None if concurrent
        """
        less = False
        greater = False
        for i in range(len(self)):
            if self.get(i) < other.get(i):
                less = True
            elif self.get(i) > other.get(i):
                greater = True

        if less and not greater:
            return -1
        if greater and not less:
            return 1
        if not less and not greater:
            return 0
        return None  # concurrent
