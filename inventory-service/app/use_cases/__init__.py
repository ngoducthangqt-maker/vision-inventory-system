"""Use-case layer (application business rules).

Use cases orchestrate domain entities through repository contracts. They are
the only place that decides *what* the application does, while leaving *how*
data is stored or transported to the outer layers.
"""

from app.use_cases.inventory_item_use_cases import (
    ConsumeExceedsStockError,
    InventoryItemUseCases,
)

__all__ = ["InventoryItemUseCases", "ConsumeExceedsStockError"]
