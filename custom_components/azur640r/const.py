"""Constants for the Azur 640R integration."""

import logging

from homeassistant.config_entries import ConfigEntry

from .client import AzurClient

DOMAIN = "azur640r"
LOGGER = logging.getLogger(__package__)

CONF_PORT_NAME = "port_name"
CONF_KEY = "key"

type Azur640RConfigEntry = ConfigEntry[AzurClient]
