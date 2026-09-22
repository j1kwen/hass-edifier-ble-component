"""Config flow for Edifier BLE."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import (
    CONF_MODEL,
    DOMAIN,
    EDIFIER_COMPANY_ID,
    MODELS_BY_SERVICE_UUID,
    model_from_service_uuid,
)
from .models import EdifierModel


def _model_from_discovery(
    discovery_info: BluetoothServiceInfoBleak,
) -> EdifierModel | None:
    """Return a supported model from a discovery event."""
    for service_uuid in discovery_info.service_uuids:
        if model := model_from_service_uuid(service_uuid):
            return model

    if EDIFIER_COMPANY_ID in discovery_info.manufacturer_data:
        # Manufacturer matching is intentionally limited to the case where the
        # mapping is unambiguous. Future models should advertise their UUID.
        models = list(MODELS_BY_SERVICE_UUID.values())
        if len(models) == 1:
            return models[0]
    return None


class EdifierBleConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle Edifier BLE config and discovery flows."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._model: EdifierModel | None = None
        self._discovered_devices: dict[str, tuple[str, EdifierModel]] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a discovered Edifier BLE device."""
        model = _model_from_discovery(discovery_info)
        if model is None:
            return self.async_abort(reason="not_supported")

        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery_info = discovery_info
        self._model = model
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm discovery of an Edifier BLE device."""
        if self._discovery_info is None or self._model is None:
            return self.async_abort(reason="not_supported")

        title = f"{self._model.manufacturer} {self._model.model}"
        if user_input is not None:
            return self.async_create_entry(
                title=title,
                data={
                    CONF_ADDRESS: self._discovery_info.address,
                    CONF_MODEL: self._model.model_code,
                },
            )

        self._set_confirm_only()
        placeholders = {"name": title}
        self.context["title_placeholders"] = placeholders
        return self.async_show_form(
            step_id="bluetooth_confirm", description_placeholders=placeholders
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow manual selection from currently discovered Edifier devices."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            title, model = self._discovered_devices[address]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=title,
                data={CONF_ADDRESS: address, CONF_MODEL: model.model_code},
            )

        current_addresses = self._async_current_ids()
        for discovery_info in async_discovered_service_info(self.hass, True):
            address = discovery_info.address
            if address in current_addresses or address in self._discovered_devices:
                continue
            if model := _model_from_discovery(discovery_info):
                self._discovered_devices[address] = (
                    f"{model.manufacturer} {model.model}",
                    model,
                )

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(
                        {
                            address: title
                            for address, (title, _) in self._discovered_devices.items()
                        }
                    )
                }
            ),
        )
