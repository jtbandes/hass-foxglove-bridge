"""The Foxglove Bridge integration."""
# ruff: noqa: D101, D102, D107

from __future__ import annotations

import asyncio
from collections.abc import Callable
from functools import partial
import json
import logging
from pathlib import Path
import time

from foxglove import (
    Channel,
    MCAPWriter,
    Schema,
    ServerListener,
    open_mcap,
    start_server,
)
from foxglove.websocket import (
    Capability,
    MessageSchema,
    Service,
    ServiceRequest,
    ServiceSchema,
)

from homeassistant.components.network import async_get_source_ip
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_API_KEY,
    CONF_DEVICE_ID,
    CONF_HOST,
    CONF_PORT,
    Platform,
)
from homeassistant.core import (
    Event,
    EventStateChangedData,
    HomeAssistant,
    SupportsResponse,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util.json import json_loads

from .const import DOMAIN
from .schemas import vol_to_jsonschema

_LOGGER = logging.getLogger(__name__)

_PLATFORMS: list[Platform] = [Platform.SWITCH]

type FoxgloveBridgeConfigEntry = ConfigEntry[FoxgloveBridge]

_STATE_SCHEMA = Schema(
    name="homeassistant.core.State",
    encoding="jsonschema",
    data=json.dumps(
        {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string"},
                "state": {"type": "string"},
                "attributes": {"type": "object"},
                "last_changed": {"type": "string"},
                "last_reported": {"type": "string"},
                "last_updated": {"type": "string"},
            },
        }
    ).encode(),
)


class FoxgloveBridge(ServerListener):
    channels_by_topic: dict[str, Channel]
    unsub_by_topic: dict[str, Callable[[], None]]
    services_by_name: dict[str, Service]
    mcap_writer: MCAPWriter | None
    mcap_path: Path | None

    def __init__(
        self,
        *,
        hass: HomeAssistant,
        entry: FoxgloveBridgeConfigEntry,
        host: str,
        port: int,
        api_key: str | None,
        device_id: str | None,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.server = start_server(
            name=f"Home Assistant {hass.config.location_name}",
            host=host,
            port=port,
            capabilities=[Capability.Services],
            server_listener=self,
            supported_encodings=["json"],
        )
        self.api_key = api_key
        self.device_id = device_id
        self.channels_by_topic = {}
        self.unsub_by_topic = {}
        self.services_by_name = {}
        self.mcap_writer = None
        self.mcap_path = None

        async def log_ip():
            server_ip = await async_get_source_ip(hass)
            _LOGGER.info(
                "Foxglove Bridge %s: listening on %s:%s",
                server_ip,
                host,
                port,
            )

        self.entry.async_create_task(self.hass, log_ip())
        self.refresh_channels_task = self.entry.async_create_background_task(
            self.hass, self._refresh_channels(), "_refresh_channels"
        )
        self.refresh_services_task = self.entry.async_create_background_task(
            self.hass, self._refresh_services(), "_refresh_services"
        )

    def stop(self):
        self.stop_recording()
        self.server.stop()
        self.refresh_channels_task.cancel()
        self.refresh_services_task.cancel()
        for chan in self.channels_by_topic.values():
            chan.close()
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
                    "Refreshed channels, adding %d, removing %d",
                    len(new_channels),
                    len(remove_channels),
                )
            for entity_id in remove_channels:
                chan = self.channels_by_topic.pop(entity_id)
                chan.close()
                if unsub := self.unsub_by_topic.pop(entity_id, None):
                    _LOGGER.debug(
                        "Unsubscribing from state changes for %s (entity disappeared)",
                        entity_id,
                    )
                    unsub()
            for entity_id in new_channels:
                self.channels_by_topic[entity_id] = Channel(
                    entity_id, message_encoding="json", schema=_STATE_SCHEMA
                )
            await asyncio.sleep(5)

    async def _refresh_services(self):
        while True:
            services_by_domain = self.hass.services.async_services()
            all_services_by_name = {
                f"{domain}.{service_name}": (domain, service_name, service)
                for domain, services in services_by_domain.items()
                for service_name, service in services.items()
            }
            new_services = all_services_by_name.keys() - self.services_by_name.keys()
            remove_services = self.services_by_name.keys() - all_services_by_name.keys()

            if new_services or remove_services:
                _LOGGER.debug(
                    "Refreshed services, adding %d, removing %d",
                    len(new_services),
                    len(remove_services),
                )
            for name in remove_services:
                _LOGGER.debug(
                    "Removing service %s (service disappeared)",
                    name,
                )
                del self.services_by_name[name]
            self.server.remove_services(list(remove_services))

            added_services = []
            for name in new_services:
                domain, service_name, service = all_services_by_name[name]
                _LOGGER.debug(
                    "Registering new service %s",
                    name,
                )
                assert name not in self.services_by_name
                schema = ServiceSchema(name=name)
                try:
                    if req_jsonschema := vol_to_jsonschema(name, service.schema):
                        schema.request = MessageSchema(
                            encoding="json",
                            schema=Schema(
                                name=f"{name}#request",
                                encoding="jsonschema",
                                data=json.dumps(req_jsonschema).encode(),
                            ),
                        )
                except Exception:
                    _LOGGER.exception("Failed to create service schema for %s", name)
                fg_service = Service(
                    name=name,
                    schema=schema,
                    handler=partial(
                        self._handle_service_request,
                        domain=domain,
                        service_name=service_name,
                        supports_response=service.supports_response,
                    ),
                )
                self.services_by_name[name] = fg_service
                added_services.append(fg_service)
            self.server.add_services(added_services)
            await asyncio.sleep(5)

    def _handle_service_request(
        self,
        request: ServiceRequest,
        *,
        domain: str,
        service_name: str,
        supports_response: SupportsResponse,
    ) -> bytes:
        try:
            return_response = supports_response != SupportsResponse.NONE
            response = self.hass.services.call(
                domain,
                service_name,
                json_loads(request.payload),
                blocking=True,
                return_response=return_response,
            )
            if not return_response:
                return b'{"success": true, "message": "(service does not support returning a response)"}'
            return json.dumps(response).encode()
        except Exception:
            _LOGGER.exception(
                "Error handling service request for %s.%s", domain, service_name
            )
            raise

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
        if state := event.data["new_state"]:
            channel.log(state.as_dict())

    def start_recording(self):
        if self.mcap_writer:
            _LOGGER.warning(
                "Warning: start_recording called but recording was already in progress"
            )
            return
        recording_dir = self.hass.config.media_dirs.get(
            "local", next(iter(self.hass.config.media_dirs.values()), None)
        )
        if recording_dir is None:
            raise FileNotFoundError("No media_dirs configured")
        recording_dir = Path(recording_dir) / DOMAIN
        recording_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.time_ns()
        path = recording_dir / f"home_assistant_{timestamp}.mcap"
        self.mcap_writer = open_mcap(path)
        self.mcap_path = path
        _LOGGER.info("Started recording to %s", path)

    def stop_recording(self):
        if not self.mcap_writer:
            return
        _LOGGER.info("Stopped recording")
        self.mcap_writer.close()
        self.mcap_writer = None
        if self.api_key and self.device_id:
            self.entry.async_create_background_task(
                self.hass,
                _upload_mcap(
                    async_get_clientsession(self.hass),
                    self.api_key,
                    self.device_id,
                    self.mcap_path,
                ),
                "_upload_mcap",
            )
        self.mcap_path = None


async def _upload_mcap(
    websession: asyncio.ClientSession,
    api_key: str,
    device_id: str,
    mcap_path: Path,
):
    """Upload a MCAP file and delete it once the upload completes."""
    try:
        req_json = {"filename": mcap_path.name, "deviceId": device_id}
        auth_headers = {"Authorization": f"Bearer {api_key}"}
        res = await websession.post(
            "https://api.foxglove.dev/v1/data/upload",
            json=req_json,
            headers=auth_headers,
        )
        upload_link = (await res.json())["link"]
        with mcap_path.open("rb") as f:
            await websession.put(upload_link, data=f)
        _LOGGER.info("Uploaded %s", mcap_path)
        mcap_path.unlink()
        _LOGGER.info("Deleted %s", mcap_path)
    except Exception:
        _LOGGER.exception("Failed to upload %s", mcap_path)
        raise


async def async_setup_entry(
    hass: HomeAssistant, entry: FoxgloveBridgeConfigEntry
) -> bool:
    """Set up Foxglove Bridge from a config entry."""

    entry.runtime_data = FoxgloveBridge(
        hass=hass,
        entry=entry,
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        api_key=entry.data.get(CONF_API_KEY),
        device_id=entry.data.get(CONF_DEVICE_ID),
    )

    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: FoxgloveBridgeConfigEntry
) -> bool:
    """Unload a config entry."""
    entry.runtime_data.stop()
    return await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
