class Totaler:
    def __init__(self) -> None:
        self.val = 0

    def __str__(self) -> str:
        return str(self.val)

    def __repr__(self) -> str:
        return str(self.val)

    def incr(self) -> None:
        self.val += 1

    def decr(self) -> None:
        self.val -= 1

    def add(self, other: int) -> None:
        self.val += other

    def subtract(self, other: int) -> None:
        self.val -= other

    def copy(self) -> "Totaler":
        out = Totaler()
        out.val = self.val
        return out
