import asyncio
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .gf_client import GfClient

_LOGGER = logging.getLogger(__name__)

# 假设 host 和 port 在这里硬编码，实际可根据需求调整
HOST = "main.ortron.cn"
PORT = 13015

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    if entry.domain != "gfhanger":
        return False

    client = GfClient(HOST, PORT)

    mobile = entry.data.get("mobile")
    password = entry.data.get("password")
    clientid = entry.data.get("clientid")

    try:
        connected = await client.connect()
        if not connected:
            return False

        logged_in = await client.login(mobile, password, clientid)
        if not logged_in:
            return False

        hass.data.setdefault(entry.entry_id, {})
        hass.data[entry.entry_id]["client"] = client

        await hass.config_entries.async_forward_entry_setups(entry, ["cover"])

        return True
    except Exception as e:
        _LOGGER.error(f"设置 Gf Hanger 时出错: {e}")
        return False

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["cover"])
    if unload_ok:
        client = hass.data[entry.entry_id]["client"]
        client.close()
        hass.data.pop(entry.entry_id)
    return unload_ok