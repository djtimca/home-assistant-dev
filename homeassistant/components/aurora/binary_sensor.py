"""Support for aurora forecast data sensor."""
from datetime import timedelta
import json
import logging
from math import floor

from aiohttp.hdrs import USER_AGENT
import requests
import voluptuous as vol

from homeassistant.components.binary_sensor import PLATFORM_SCHEMA, BinarySensorEntity
from homeassistant.const import ATTR_ATTRIBUTION, CONF_NAME
import homeassistant.helpers.config_validation as cv
from homeassistant.util import Throttle

_LOGGER = logging.getLogger(__name__)

ATTRIBUTION = "Data provided by the National Oceanic and Atmospheric Administration"
CONF_THRESHOLD = "forecast_threshold"

DEFAULT_DEVICE_CLASS = "visible"
DEFAULT_NAME = "Aurora Visibility"
DEFAULT_THRESHOLD = 75

HA_USER_AGENT = "Home Assistant Aurora Tracker v.0.2.0"

MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=5)

URL = "http://services.swpc.noaa.gov/json/ovation_aurora_latest.json"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_THRESHOLD, default=DEFAULT_THRESHOLD): cv.positive_int,
    }
)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the aurora sensor."""
    if None in (hass.config.latitude, hass.config.longitude):
        _LOGGER.error("Lat. or long. not set in Home Assistant config")
        return False

    name = config[CONF_NAME]
    threshold = config[CONF_THRESHOLD]

    try:
        aurora_data = AuroraData(hass.config.latitude, hass.config.longitude, threshold)
        aurora_data.update()
    except requests.exceptions.HTTPError as error:
        _LOGGER.error("Connection to aurora forecast service failed: %s", error)
        return False

    add_entities([AuroraSensor(aurora_data, name)], True)


class AuroraSensor(BinarySensorEntity):
    """Implementation of an aurora sensor."""

    def __init__(self, aurora_data, name):
        """Initialize the sensor."""
        self.aurora_data = aurora_data
        self._name = name

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{self._name}"

    @property
    def is_on(self):
        """Return true if aurora is visible."""
        return self.aurora_data.is_visible if self.aurora_data else False

    @property
    def device_class(self):
        """Return the class of this device."""
        return DEFAULT_DEVICE_CLASS

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        attrs = {}

        if self.aurora_data:
            attrs["visibility_level"] = self.aurora_data.visibility_level
            attrs["message"] = self.aurora_data.is_visible_text
            attrs[ATTR_ATTRIBUTION] = ATTRIBUTION
        return attrs

    def update(self):
        """Get the latest data from Aurora API and updates the states."""
        self.aurora_data.update()


class AuroraData:
    """Get aurora forecast."""

    def __init__(self, latitude, longitude, threshold):
        """Initialize the data object."""
        self.latitude = latitude
        self.longitude = longitude
        self.headers = {USER_AGENT: HA_USER_AGENT}
        self.threshold = int(threshold)
        self.is_visible = None
        self.is_visible_text = None
        self.visibility_level = None

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        """Get the latest data from the Aurora service."""
        try:
            result = self.get_aurora_forecast()
            if result is False:
                _LOGGER.error("Missing data for current location")
                return False

            self.visibility_level = result
            if int(self.visibility_level) > self.threshold:
                self.is_visible = True
                self.is_visible_text = "visible!"
            else:
                self.is_visible = False
                self.is_visible_text = "nothing's out"

        except requests.exceptions.HTTPError as error:
            _LOGGER.error("Connection to aurora forecast service failed: %s", error)
            return False

    def get_aurora_forecast(self):
        """Get forecast data and parse for given long/lat."""
        raw_data = requests.get(URL, headers=self.headers, timeout=5).text
        forecast_data = json.loads(raw_data)

        # Convert lat and long for data points in json
        converted_latitude = floor(self.latitude)
        converted_longitude = floor(self.longitude)

        # Find the forecast for the current location by walking through the one
        # dimensional list of forcasts
        for forecast in forecast_data["coordinates"]:
            if forecast[0] == converted_longitude and forecast[1] == converted_latitude:
                return str(forecast[2])

        return False
