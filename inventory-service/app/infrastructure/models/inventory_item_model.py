"""SQLAlchemy ORM model for the ``inventory_items`` table.

This model is a *persistence detail* belonging to the infrastructure layer.
It maps to the ``InventoryItem`` domain entity via explicit conversion
functions so the domain never references SQLAlchemy.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class InventoryItemModel(Base):
    """Persistence representation of an ``InventoryItem``."""

    __tablename__ = "inventory_items"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        nullable=False,
    )
    sku: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    price: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00")
    )
    category: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    low_stock_threshold: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_inventory_items_category_quantity", "category", "quantity"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return (
            f"<InventoryItemModel id={self.id} sku={self.sku!r} "
            f"qty={self.quantity}>"
        )
