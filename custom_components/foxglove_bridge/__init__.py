"""The Foxglove Bridge integration."""
# ruff: noqa: D101, D102, D107

from __future__ import annotations

import asyncio
from collections.abc import Callable
from functools import partial
import logging

from foxglove import Channel, ServerListener, start_server

from homeassistant.components.network import async_get_source_ip
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import Event, EventStateChangedData, HomeAssistant
from homeassistant.helpers.event import async_track_state_change_event

_LOGGER = logging.getLogger(__name__)

_PLATFORMS: list[Platform] = [Platform.LIGHT]

type FoxgloveBridgeConfigEntry = ConfigEntry[FoxgloveBridge]


class FoxgloveBridge(ServerListener):
    channels_by_topic: dict[str, Channel]
    unsub_by_topic: dict[str, Callable[[], None]]

    def __init__(
        self,
        *,
        hass: HomeAssistant,
        entry: FoxgloveBridgeConfigEntry,
        host: str,
        port: int,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.server = start_server(
            name=f"Home Assistant {hass.config.location_name}",
            host=host,
            port=port,
            server_listener=self,
        )
        self.channels_by_topic = {}
        self.unsub_by_topic = {}

        async def log_ip():
            server_ip = await async_get_source_ip(hass)
            _LOGGER.info(
                "Foxglove Bridge %s: listening on %s:%s",
                server_ip,
                host,
                port,
            )

        self.entry.async_create_task(self.hass, log_ip())
        self.refresh_task = self.entry.async_create_background_task(
            self.hass, self._refresh_channels(), "_refresh_channels"
        )

        # self.event_listener = hass.bus.async_listen(MATCH_ALL,self._handle_event)

    def stop(self):
        self.server.stop()
        self.refresh_task.cancel()
        self.channels_by_topic.clear()
        for unsub in self.unsub_by_topic.values():
            unsub()
        self.unsub_by_topic.clear()

    async def _refresh_channels(self):
        while True:
            entity_ids = set(self.hass.states.async_entity_ids())
            new_channels = entity_ids - self.channels_by_topic.keys()
            remove_channels = self.channels_by_topic.keys() - entity_ids
            if new_channels or remove_channels:
                _LOGGER.debug(
                    "Refreshed channels, added %d, removed %d",
                    len(new_channels),
                    len(remove_channels),
                )
            for entity_id in remove_channels:
                del self.channels_by_topic[entity_id]
                if unsub := self.unsub_by_topic.pop(entity_id, None):
                    _LOGGER.debug(
                        "Unsubscribing from state changes for %s (entity disappeared)",
                        entity_id,
                    )
                    unsub()
            for entity_id in new_channels:
                self.channels_by_topic[entity_id] = Channel(
                    entity_id, message_encoding="json"
                )
            await asyncio.sleep(5)

    def on_subscribe(self, client, channel) -> None:
        self.hass.loop.call_soon_threadsafe(
            self._threadsafe_on_subscribe, client, channel
        )

    def _threadsafe_on_subscribe(self, client, channel) -> None:
        _LOGGER.debug("Subscribing to state changes for %s", channel.topic)
        self.hass.verify_event_loop_thread("expected to be called from main thread")
        # assert channel.topic not in self.unsub_by_topic  # FG-10872
        if channel.topic in self.unsub_by_topic:
            _LOGGER.warning("Duplicate subscription to %s", channel.topic)
            return
        chan = self.channels_by_topic[channel.topic]
        if state := self.hass.states.get(channel.topic):
            chan.log(state.as_dict())
        self.unsub_by_topic[channel.topic] = async_track_state_change_event(
            self.hass, channel.topic, partial(self._handle_state_change, chan)
        )

    def on_unsubscribe(self, _client, channel) -> None:
        self.hass.loop.call_soon_threadsafe(
            self._threadsafe_on_unsubscribe, _client, channel
        )

    def _threadsafe_on_unsubscribe(self, _client, channel) -> None:
        _LOGGER.debug("Unsubscribing from state changes for %s", channel.topic)
        self.hass.verify_event_loop_thread("expected to be called from main thread")
        unsub = self.unsub_by_topic.pop(channel.topic)
        unsub()

    def _handle_state_change(
        self, channel: Channel, event: Event[EventStateChangedData]
    ):
        channel.log(event.data["new_state"].as_dict())


async def async_setup_entry(
    hass: HomeAssistant, entry: FoxgloveBridgeConfigEntry
) -> bool:
    """Set up Foxglove Bridge from a config entry."""

    entry.runtime_data = FoxgloveBridge(
        hass=hass,
        entry=entry,
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
    )

    # await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: FoxgloveBridgeConfigEntry
) -> bool:
    """Unload a config entry."""
    entry.runtime_data.stop()
    # return await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)


# async def async_setup(hass, config):
#     hass.states.async_set("foxglove_bridge.hello_world", "Test")

#     # Return boolean to indicate that initialization was successful.
#     return True
