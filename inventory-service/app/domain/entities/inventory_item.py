"""InventoryItem domain entity.

This is the core business object. It knows nothing about databases, HTTP or
serialization frameworks. It only expresses the *business rules* of an
inventory item.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4


@dataclass
class InventoryItem:
    """A single stock-keeping unit tracked by the inventory service.

    Attributes:
        id: Unique identifier of the item.
        sku: Human-readable, unique stock-keeping unit code.
        name: Display name of the item.
        description: Optional long-form description.
        quantity: Number of units currently in stock (>= 0).
        price: Unit price expressed as a ``Decimal`` for exact arithmetic.
        category: Optional categorization label.
        low_stock_threshold: When ``quantity`` drops at or below this value the
            item is considered "low stock".
        created_at: Creation timestamp (UTC).
        updated_at: Last modification timestamp (UTC).
    """

    sku: str
    name: str
    quantity: int
    price: Decimal
    id: UUID = field(default_factory=uuid4)
    description: str | None = None
    category: str | None = None
    low_stock_threshold: int = 10
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # ------------------------------------------------------------------ #
    # Business rules / domain methods                                     #
    # ------------------------------------------------------------------ #
    def is_low_stock(self) -> bool:
        """Return ``True`` when the available quantity is at/below threshold."""
        return self.quantity <= self.low_stock_threshold

    def is_in_stock(self) -> bool:
        """Return ``True`` when there is at least one unit available."""
        return self.quantity > 0

    def restock(self, amount: int) -> None:
        """Increase the stock level by ``amount`` units."""
        if amount < 0:
            raise ValueError("Restock amount must be non-negative.")
        self.quantity += amount
        self.touch()

    def consume(self, amount: int) -> None:
        """Decrease the stock level by ``amount`` units.

        Raises:
            ValueError: If ``amount`` is negative or exceeds available stock.
        """
        if amount < 0:
            raise ValueError("Consume amount must be non-negative.")
        if amount > self.quantity:
            raise ValueError(
                f"Cannot consume {amount} units: only {self.quantity} in stock."
            )
        self.quantity -= amount
        self.touch()

    def touch(self) -> None:
        """Refresh the ``updated_at`` timestamp to the current UTC time."""
        self.updated_at = datetime.now(timezone.utc)
