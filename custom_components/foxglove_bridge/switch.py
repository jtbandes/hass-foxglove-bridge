"""Switch entity to control recording."""
# ruff: noqa: D101, D102, D103, D107

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import FoxgloveBridge, FoxgloveBridgeConfigEntry
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


# This function is called as part of the __init__.async_setup_entry (via the
# hass.config_entries.async_forward_entry_setup call)
async def async_setup_entry(
    hass: HomeAssistant,
    entry: FoxgloveBridgeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([McapRecordingSwitch(entry.runtime_data, entry.entry_id)])


class McapRecordingSwitch(SwitchEntity):
    def __init__(self, bridge: FoxgloveBridge, entry_id: str) -> None:
        self._bridge = bridge
        self._attr_name = "MCAP Recording"
        self._attr_unique_id = f"{entry_id}-recording"
        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, entry_id)},
        )
        self._attr_is_on = False

    async def async_turn_on(self) -> None:
        self._bridge.start_recording()
        self._attr_is_on = True

    async def async_turn_off(self) -> None:
        self._bridge.stop_recording()
        self._attr_is_on = False
