"""Tests for the dependency-injection composition root."""

from __future__ import annotations

from app.dependencies import get_inventory_item_repository, get_inventory_item_use_cases
from app.infrastructure.repositories.inventory_item_repository_impl import (
    SqlAlchemyInventoryItemRepository,
)
from app.use_cases.inventory_item_use_cases import InventoryItemUseCases


async def test_repository_is_bound_to_the_request_session(sqlite_session):
    repository = await get_inventory_item_repository(sqlite_session)
    assert isinstance(repository, SqlAlchemyInventoryItemRepository)
    assert repository._session is sqlite_session  # noqa: SLF001


async def test_use_cases_are_bound_to_the_repository(fake_repository):
    use_cases = await get_inventory_item_use_cases(fake_repository)
    assert isinstance(use_cases, InventoryItemUseCases)
    assert use_cases._repo is fake_repository  # noqa: SLF001
