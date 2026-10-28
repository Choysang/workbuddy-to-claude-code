"""FIFO stock lots with cost tracking."""

from dataclasses import dataclass, field
from decimal import Decimal

from .money import round_money, to_money


@dataclass
class Lot:
    qty: int
    unit_cost: Decimal


@dataclass
class Stock:
    lots: list = field(default_factory=list)

    def receive(self, qty: int, unit_cost) -> None:
        """Add a new lot at the end of the FIFO queue. qty must be positive."""
        if qty <= 0:
            raise ValueError("qty must be positive")
        self.lots.append(Lot(qty, to_money(unit_cost)))

    @property
    def on_hand(self) -> int:
        return sum(lot.qty for lot in self.lots)

    def consume(self, qty: int) -> Decimal:
        """Remove `qty` units oldest-lot-first and return their total cost, rounded
        to cents. Raises ValueError (and changes nothing) if there is not enough
        stock. Empty lots are dropped."""
        if qty > self.on_hand:
            raise ValueError("insufficient stock")
        need, cost = qty, Decimal("0")
        while need:
            lot = self.lots[0]
            take = min(lot.qty, need)
            cost += take * lot.unit_cost
            lot.qty -= take
            need -= take
            if lot.qty == 0:
                self.lots.pop(0)
        return round_money(cost)

    def average_cost(self) -> Decimal:
        """Weighted average unit cost of what is on hand (total cost / units),
        rounded to cents; 0 when empty."""
        if not self.on_hand:
            return Decimal("0")
        total = sum(lot.qty * lot.unit_cost for lot in self.lots)
        return round_money(total / self.on_hand)
