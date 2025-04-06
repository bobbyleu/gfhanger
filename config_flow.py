import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

class GfHangerConfigFlow(config_entries.ConfigFlow, domain="gfhanger"):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(
                title="Gf Hanger",
                data={
                    "mobile": user_input["mobile"],
                    "password": user_input["password"],
                    "clientid": user_input["clientid"],
                },
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("mobile"): str,
                vol.Required("password"): str,
                vol.Required("clientid"): str,
            }),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return GfHangerOptionsFlowHandler(config_entry)

class GfHangerOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    "mobile": user_input["mobile"],
                    "password": user_input["password"],
                    "clientid": user_input["clientid"],
                },
            )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("mobile", default=self.config_entry.data.get("mobile")): str,
                vol.Required("password", default=self.config_entry.data.get("password")): str,
                vol.Required("clientid", default=self.config_entry.data.get("clientid")): str,
            }),
        )