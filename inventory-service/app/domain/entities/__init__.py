"""Domain entities package.

Entities are pure Python objects that encapsulate enterprise-wide business
rules. They must NOT depend on any framework (no SQLAlchemy, no Pydantic,
no FastAPI) so the core of the application stays portable and testable.
"""

from app.domain.entities.inventory_item import InventoryItem

__all__ = ["InventoryItem"]
