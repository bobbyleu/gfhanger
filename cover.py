import logging
from homeassistant.components.cover import (
    CoverEntity,
    CoverEntityFeature,
    ATTR_POSITION,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .gf_client import GfClient

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    client = hass.data[entry.entry_id]["client"]
    entities = []
    for device_info in client.devices_info:
        entities.append(GfCover(device_info, client, entry.data))
    async_add_entities(entities)

class GfCover(CoverEntity):
    def __init__(self, device_info, client, config_data):
        self._attr_unique_id = device_info["_id"]
        self._attr_name = device_info["e_name"]
        self._device_info = device_info
        self._client = client
        self._config_data = config_data
        self._attr_supported_features = (
            CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
        )

    @property
    def is_closed(self):
        return self._device_info["status"] == "closed"

    @property
    def current_cover_position(self):
        return self._device_info["position"]

    async def async_open_cover(self, **kwargs):
        await self._client.remote_control(
            self._config_data["mobile"],
            self._config_data["password"],
            self._config_data["clientid"],
            self._device_info["_id"],
            2
        )

    async def async_close_cover(self, **kwargs):
        await self._client.remote_control(
            self._config_data["mobile"],
            self._config_data["password"],
            self._config_data["clientid"],
            self._device_info["_id"],
            1
        )

    async def async_stop_cover(self, **kwargs):
        await self._client.remote_control(
            self._config_data["mobile"],
            self._config_data["password"],
            self._config_data["clientid"],
            self._device_info["_id"],
            3
        )

    async def async_update(self):
        # 可添加更新设备状态的逻辑
        pass