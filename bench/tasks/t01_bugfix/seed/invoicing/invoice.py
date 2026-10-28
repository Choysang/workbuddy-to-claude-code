"""Simple invoice model used by the billing service."""
from dataclasses import dataclass, field


@dataclass
class LineItem:
    description: str
    unit_price: float
    quantity: int = 1

    def total(self):
        return self.unit_price * self.quantity


@dataclass
class Invoice:
    items: list = field(default_factory=list)
    discount_percent: float = 0.0

    def add(self, description, unit_price, quantity=1):
        self.items.append(LineItem(description, unit_price, quantity))

    def subtotal(self):
        return sum(item.total() for item in self.items)

    def total(self):
        subtotal = self.subtotal()
        discount = subtotal * self.discount_percent / 100
        return round(subtotal - discount, 2)

    def render(self):
        lines = [f"{i.description:<20}{i.quantity:>4} x {i.unit_price:>8}" for i in self.items]
        lines.append(f"{'TOTAL':<20}{self.total():>17}")
        return "\n".join(lines)
