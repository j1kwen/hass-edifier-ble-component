"""Entity lifecycle tests for the Edifier processor."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
import unittest

from homeassistant.components.bluetooth.passive_update_processor import (
    PassiveBluetoothDataUpdate,
    PassiveBluetoothEntityKey,
)
from homeassistant.helpers.entity import EntityDescription

from custom_components.edifier_ble.coordinator import EdifierBluetoothDataProcessor


class FakeEntity:
    """Minimal entity used to verify processor removal."""

    def __init__(self, processor, entity_key, description) -> None:
        self.entity_key = entity_key
        self.removed = False

    async def async_remove(self) -> None:
        """Mark the entity removed."""
        self.removed = True


def _data(*keys: str) -> PassiveBluetoothDataUpdate[None]:
    """Build processor data for the supplied entity keys."""
    return PassiveBluetoothDataUpdate(
        entity_descriptions={
            PassiveBluetoothEntityKey(key, None): EntityDescription(key=key)
            for key in keys
        },
        entity_data={
            PassiveBluetoothEntityKey(key, None): None for key in keys
        },
    )


class ProcessorLifecycleTest(unittest.IsolatedAsyncioTestCase):
    """Test dynamic entity removal."""

    async def test_entity_is_removed_when_description_disappears(self) -> None:
        """An unsupported D8 feature should remove its existing entity."""
        processor = EdifierBluetoothDataProcessor(lambda state: state)
        processor.coordinator = SimpleNamespace(
            hass=SimpleNamespace(
                async_create_task=lambda coro: asyncio.create_task(coro)
            )
        )
        added: list[FakeEntity] = []
        remove_listener = processor.async_add_entities_listener(
            FakeEntity, lambda entities: added.extend(entities)
        )

        processor.async_update_listeners(_data("one", "two"), was_available=False)
        self.assertEqual({entity.entity_key.key for entity in added}, {"one", "two"})

        processor.async_update_listeners(_data("one"), was_available=False)
        await asyncio.sleep(0)
        removed = [entity for entity in added if entity.removed]
        self.assertEqual([entity.entity_key.key for entity in removed], ["two"])

        remove_listener()


if __name__ == "__main__":
    unittest.main()
