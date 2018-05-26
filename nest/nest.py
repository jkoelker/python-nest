# -*- coding:utf-8 -*-

import collections
import copy
import datetime
import hashlib
import threading
import time
import os
import uuid
import weakref

from dateutil.parser import parse as parse_time

import requests
from requests import auth
from requests import adapters
from requests.compat import json

import sseclient

ACCESS_TOKEN_URL = 'https://api.home.nest.com/oauth2/access_token'
AUTHORIZE_URL = 'https://home.nest.com/login/oauth2?client_id={0}&state={1}'
API_URL = 'https://developer-api.nest.com'
LOGIN_URL = 'https://home.nest.com/user/login'
SIMULATOR_SNAPSHOT_URL = \
    'https://developer.nest.com' \
    '/simulator/api/v1/nest/devices/camera/snapshot'
SIMULATOR_SNAPSHOT_PLACEHOLDER_URL = \
    'https://media.giphy.com/media/WCwFvyeb6WJna/giphy.gif'

AWAY_MAP = {'on': 'away',
            'away': 'away',
            'off': 'home',
            'home': 'home',
            True: 'away',
            False: 'home'}

FAN_MAP = {'auto on': False,
           'on': True,
           'auto': False,
           '1': True,
           '0': False,
           1: True,
           0: False,
           True: True,
           False: False}

LowHighTuple = collections.namedtuple('LowHighTuple', ('low', 'high'))

DEVICES = 'devices'
METADATA = 'metadata'
STRUCTURES = 'structures'
THERMOSTATS = 'thermostats'
SMOKE_CO_ALARMS = 'smoke_co_alarms'
CAMERAS = 'cameras'

# https://developers.nest.com/documentation/api-reference/overview#targettemperaturef
MINIMUM_TEMPERATURE_F = 50
MAXIMUM_TEMPERATURE_F = 90
# https://developers.nest.com/documentation/api-reference/overview#targettemperaturec
MINIMUM_TEMPERATURE_C = 9
MAXIMUM_TEMPERATURE_C = 32


class APIError(Exception):
    def __init__(self, response, msg=None):
        try:
            response_content = response.content
        except AttributeError:
            response_content = response.data

        if response_content != b'':
            if isinstance(response, requests.Response):
                message = response.json()['error']
        else:
            message = "API Error Occured"

        if msg is not None:
            message = "API Error Occured: " + msg

        # Call the base class constructor with the parameters it needs
        super(APIError, self).__init__(message)

        self.response = response


class AuthorizationError(Exception):
    def __init__(self, response, msg=None):
        try:
            response_content = response.content
        except AttributeError:
            response_content = response.data

        if response_content != b'':
            if isinstance(response, requests.Response):
                message = response.json().get(
                    'error_description',
                    "Authorization Failed")
        else:
            message = "Authorization failed"

        if msg is not None:
            message = "Authorization Failed: " + msg

        # Call the base class constructor with the parameters it needs
        super(AuthorizationError, self).__init__(message)

        self.response = response


class NestAuth(auth.AuthBase):
    def __init__(self, auth_callback=None, session=None,
                 client_id=None, client_secret=None,
                 access_token=None, access_token_cache_file=None):
        self._res = {}
        self.auth_callback = auth_callback
        self.pin = None
        self._access_token_cache_file = access_token_cache_file
        self._client_id = client_id
        self._client_secret = client_secret
        self._access_token = access_token

        if (access_token_cache_file is not None and
                access_token is None and
                os.path.exists(access_token_cache_file)):
            with open(access_token_cache_file, 'r') as f:
                self._res = json.load(f)
                self._callback(self._res)

        if session is not None:
            session = weakref.ref(session)

        self._session = session
        self._adapter = adapters.HTTPAdapter()

    def _cache(self):
        if self._access_token_cache_file is not None:
            with os.fdopen(os.open(self._access_token_cache_file,
                                   os.O_WRONLY | os.O_CREAT, 0o600),
                           'w') as f:
                json.dump(self._res, f)

    def _callback(self, res):
        if self.auth_callback is not None and isinstance(self.auth_callback,
                                                         collections.Callable):
            self.auth_callback(res)

    def login(self, headers=None):
        data = {'client_id': self._client_id,
                'client_secret': self._client_secret,
                'code': self.pin,
                'grant_type': 'authorization_code'}

        post = requests.post

        if self._session:
            session = self._session()
            post = session.post

        response = post(ACCESS_TOKEN_URL, data=data, headers=headers)
        if response.status_code != 200:
            raise AuthorizationError(response)
        self._res = response.json()

        self._cache()
        self._callback(self._res)

    @property
    def access_token(self):
        return self._res.get('access_token', self._access_token)

    def __call__(self, r):
        if self.access_token:
            r.headers['Authorization'] = 'Bearer ' + self.access_token

        return r


class NestBase(object):
    def __init__(self, serial, nest_api):
        self._serial = serial
        self._nest_api = nest_api

    def __repr__(self):
        return '<%s: %s>' % (self.__class__.__name__, self._repr_name)

    def _set(self, what, data):
        path = '/%s/%s' % (what, self._serial)

        response = self._nest_api._put(path=path, data=data)

        return response

    @property
    def _weather(self):
        raise NotImplementedError("Deprecated Nest API")
        # merge_code = self.postal_code + ',' + self.country_code
        # return self._nest_api._weather[merge_code]

    @property
    def weather(self):
        raise NotImplementedError("Deprecated Nest API")
        # return Weather(self._weather, self._local_time)

    @property
    def serial(self):
        return self._serial

    @property
    def _repr_name(self):
        return self.serial


class Device(NestBase):
    @property
    def _device(self):
        raise NotImplementedError("Implemented by subclass")

    @property
    def _devices(self):
        return self._nest_api._devices

    @property
    def _repr_name(self):
        if self.name:
            return self.name

        return self.where

    @property
    def name(self):
        return self._device.get('name')

    @name.setter
    def name(self, value):
        raise NotImplementedError("Needs updating with new API")
        # self._set('shared', {'name': value})

    @property
    def name_long(self):
        return self._device.get('name_long')

    @property
    def device_id(self):
        return self._device.get('device_id')

    @property
    def online(self):
        return self._device.get('is_online')

    @property
    def structure(self):
        return Structure(self._device['structure_id'],
                         self._nest_api)

    @property
    def where(self):
        if self.where_id is not None:
            # This name isn't always present due to upstream bug in the API
            # https://nestdevelopers.io/t/missing-where-name-from-some-devices/1202
            if self.where_id in self.structure.wheres:
                return self.structure.wheres[self.where_id]['name']
            else:
                return self.where_id

    @property
    def where_id(self):
        return self._device.get('where_id')

    @where.setter
    def where(self, value):
        value = value.lower()
        ident = self.structure.wheres.get(value)

        if ident is None:
            self.structure.add_where(value)
            ident = self.structure.wheres[value]

        self._set('device', {'where_id': ident})

    @property
    def description(self):
        return self._device['name_long']

    @property
    def is_thermostat(self):
        return False

    @property
    def is_camera(self):
        return False

    @property
    def is_smoke_co_alarm(self):
        return False


class Thermostat(Device):
    @property
    def is_thermostat(self):
        return True

    @property
    def _device(self):
        return self._devices[THERMOSTATS][self._serial]

    @property
    def _shared(self):
        raise NotImplementedError("Deprecated Nest API")
        # return self._nest_api._status['shared'][self._serial]

    @property
    def _track(self):
        raise NotImplementedError("Deprecated Nest API")
        # return self._nest_api._status['track'][self._serial]

    @property
    def software_version(self):
        return self._device['software_version']

    @property
    def fan(self):
        # FIXME confirm this is the same as old havac_fan_state
        return self._device.get('fan_timer_active')

    @fan.setter
    def fan(self, value):
        mapped_value = FAN_MAP.get(value, False)
        if mapped_value is None:
            raise ValueError("Only True and False supported")

        self._set('devices/thermostats', {'fan_timer_active': mapped_value})

    @property
    def fan_timer(self):
        return self._device.get('fan_timer_duration')

    @fan_timer.setter
    def fan_timer(self, value):
        self._set('devices/thermostats', {'fan_timer_duration': value})

    @property
    def humidity(self):
        return self._device.get('humidity')

    @property
    def target_humidity(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['target_humidity']

    @target_humidity.setter
    def target_humidity(self, value):
        raise NotImplementedError("No longer available in Nest API")
    #    if value == 'auto':

    #        if self._weather['current']['temp_c'] >= 4.44:
    #            hum_value = 45
    #        elif self._weather['current']['temp_c'] >= -1.11:
    #            hum_value = 40
    #        elif self._weather['current']['temp_c'] >= -6.67:
    #            hum_value = 35
    #        elif self._weather['current']['temp_c'] >= -12.22:
    #            hum_value = 30
    #        elif self._weather['current']['temp_c'] >= -17.78:
    #            hum_value = 25
    #        elif self._weather['current']['temp_c'] >= -23.33:
    #            hum_value = 20
    #        elif self._weather['current']['temp_c'] >= -28.89:
    #            hum_value = 15
    #        elif self._weather['current']['temp_c'] >= -34.44:
    #            hum_value = 10
    #    else:
    #        hum_value = value

    #    if float(hum_value) != self._device['target_humidity']:
    #        self._set('device', {'target_humidity': float(hum_value)})

    @property
    def mode(self):
        # FIXME confirm same as target_temperature_type
        return self._device.get('hvac_mode')

    @mode.setter
    def mode(self, value):
        self._set('devices/thermostats', {'hvac_mode': value.lower()})

    @property
    def has_leaf(self):
        return self._device.get('has_leaf')

    @property
    def hvac_ac_state(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._shared['hvac_ac_state']

    @property
    def hvac_cool_x2_state(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._shared['hvac_cool_x2_state']

    @property
    def hvac_heater_state(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._shared['hvac_heater_state']

    @property
    def hvac_aux_heater_state(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._shared['hvac_aux_heater_state']

    @property
    def hvac_heat_x2_state(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._shared['hvac_heat_x2_state']

    @property
    def hvac_heat_x3_state(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._shared['hvac_heat_x3_state']

    @property
    def hvac_alt_heat_state(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._shared['hvac_alt_heat_state']

    @property
    def hvac_alt_heat_x2_state(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._shared['hvac_alt_heat_x2_state']

    @property
    def hvac_emer_heat_state(self):
        raise NotImplementedError(
            "No longer available in Nest API. See "
            "is_using_emergency_heat instead")
        # return self._shared['hvac_emer_heat_state']

    @property
    def is_using_emergency_heat(self):
        return self._device.get('is_using_emergency_heat')

    @property
    def label(self):
        return self._device.get('label')

    @property
    def local_ip(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['local_ip']

    @property
    def last_ip(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._track['last_ip']

    @property
    def last_connection(self):
        # TODO confirm this does get set, or if the API documentation is wrong
        return self._device.get('last_connection')

    @property
    def error_code(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['error_code']

    @property
    def battery_level(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['battery_level']

    @property
    def battery_health(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['battery_health']

    @property
    def postal_code(self):
        return self.structure.postal_code
        # return self._device['postal_code']

    def _temp_key(self, key):
        return "%s_%s" % (key, self.temperature_scale.lower())

    def _round_temp(self, temp):
        if self.temperature_scale == 'C':
            return round(temp * 2) / 2
        else:
            # F goes to nearest degree
            return int(round(temp))

    @property
    def temperature_scale(self):
        return self._device['temperature_scale']

    @property
    def is_locked(self):
        return self._device.get('is_locked')

    @property
    def locked_temperature(self):
        low = self._device.get(self._temp_key('locked_temp_min'))
        high = self._device.get(self._temp_key('locked_temp_max'))
        return LowHighTuple(low, high)

    @property
    def temperature(self):
        return self._device.get(self._temp_key('ambient_temperature'))

    @property
    def min_temperature(self):
        if self.is_locked:
            return self.locked_temperature[0]
        else:
            if self.temperature_scale == 'C':
                return MINIMUM_TEMPERATURE_C
            else:
                return MINIMUM_TEMPERATURE_F

    @property
    def max_temperature(self):
        if self.is_locked:
            return self.locked_temperature[1]
        else:
            if self.temperature_scale == 'C':
                return MAXIMUM_TEMPERATURE_C
            else:
                return MAXIMUM_TEMPERATURE_F

    @temperature.setter
    def temperature(self, value):
        self.target = value

    @property
    def target(self):
        if self.mode == 'heat-cool':
            low = self._device[self._temp_key('target_temperature_low')]
            high = self._device[self._temp_key('target_temperature_high')]
            return LowHighTuple(low, high)

        return self._device[self._temp_key('target_temperature')]

    @target.setter
    def target(self, value):
        data = {}

        if self.mode == 'heat-cool':
            rounded_low = self._round_temp(value[0])
            rounded_high = self._round_temp(value[1])

            data[self._temp_key('target_temperature_low')] = rounded_low
            data[self._temp_key('target_temperature_high')] = rounded_high
        else:
            rounded_temp = self._round_temp(value)
            data[self._temp_key('target_temperature')] = rounded_temp

        self._set('devices/thermostats', data)

    @property
    def away_temperature(self):
        # see https://nestdevelopers.io/t/new-things-for-fall/226
        raise NotImplementedError(
            "Deprecated Nest API, use eco_temperature instead")

    @away_temperature.setter
    def away_temperature(self, value):
        # see https://nestdevelopers.io/t/new-things-for-fall/226
        raise NotImplementedError(
                "Deprecated Nest API, use eco_temperature instead")

    @property
    def eco_temperature(self):
        # use get, since eco_temperature isn't always filled out
        low = self._device.get(self._temp_key('eco_temperature_low'))
        high = self._device.get(self._temp_key('eco_temperature_high'))

        return LowHighTuple(low, high)

    @eco_temperature.setter
    def eco_temperature(self, value):
        low, high = value
        data = {}

        if low is not None:
            data[self._temp_key('eco_temperature_low')] = low

        if high is not None:
            data[self._temp_key('eco_temperature_high')] = high

        self._set('devices/thermostats', data)

    @property
    def can_heat(self):
        return self._device.get('can_heat')

    @property
    def can_cool(self):
        return self._device.get('can_cool')

    @property
    def has_humidifier(self):
        return self._device.get('has_humidifier')

    @property
    def has_dehumidifier(self):
        return self._device.get('has_dehumidifier')

    @property
    def has_fan(self):
        return self._device.get('has_fan')

    @property
    def has_hot_water_control(self):
        return self._device.get('has_hot_water_control')

    @property
    def hot_water_temperature(self):
        return self._device.get('hot_water_temperature')

    @property
    def hvac_state(self):
        return self._device.get('hvac_state')

    @property
    def eco(self):
        raise NotImplementedError("Deprecated Nest API")
        # eco_mode = self._device['eco']['mode']
        # # eco modes can be auto-eco or manual-eco
        # return eco_mode.endswith('eco')

    @eco.setter
    def eco(self, value):
        raise NotImplementedError("Deprecated Nest API")
        # data = {'eco': self._device['eco']}
        # if value:
        #     data['eco']['mode'] = 'manual-eco'
        # else:
        #     data['eco']['mode'] = 'schedule'
        # data['eco']['mode_update_timestamp'] = time.time()
        # self._set('device', data)

    @property
    def previous_mode(self):
        return self._device.get('previous_hvac_mode')

    @property
    def time_to_target(self):
        return self._device.get('time_to_target')

    @property
    def time_to_target_training(self):
        return self._device.get('time_to_target_training')


class SmokeCoAlarm(Device):
    @property
    def is_smoke_co_alarm(self):
        return True

    @property
    def _device(self):
        return self._devices[SMOKE_CO_ALARMS][self._serial]

    @property
    def auto_away(self):
        raise NotImplementedError("No longer available in Nest API.")
        # return self._device['auto_away']

    @property
    def battery_health(self):
        return self._device.get('battery_health')

    @property
    def battery_health_state(self):
        raise NotImplementedError("use battery_health instead")

    @property
    def battery_level(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['battery_level']

    @property
    def capability_level(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['capability_level']

    @property
    def certification_body(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['certification_body']

    @property
    def co_blame_duration(self):
        raise NotImplementedError("No longer available in Nest API")
        # if 'co_blame_duration' in self._device:
        #     return self._device['co_blame_duration']

    @property
    def co_blame_threshold(self):
        raise NotImplementedError("No longer available in Nest API")
        # if 'co_blame_threshold' in self._device:
        #     return self._device['co_blame_threshold']

    @property
    def co_previous_peak(self):
        raise NotImplementedError("No longer available in Nest API")
        # if 'co_previous_peak' in self._device:
        #     return self._device['co_previous_peak']

    @property
    def co_sequence_number(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['co_sequence_number']

    @property
    def co_status(self):
        # TODO deprecate for new name
        return self._device.get('co_alarm_state')

    @property
    def color_status(self):
        return self._device.get('ui_color_state')

    @property
    def component_als_test_passed(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['component_als_test_passed']

    @property
    def component_co_test_passed(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['component_co_test_passed']

    @property
    def component_heat_test_passed(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['component_heat_test_passed']

    @property
    def component_hum_test_passed(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['component_hum_test_passed']

    @property
    def component_led_test_passed(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['component_led_test_passed']

    @property
    def component_pir_test_passed(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['component_pir_test_passed']

    @property
    def component_smoke_test_passed(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['component_smoke_test_passed']

    @property
    def component_temp_test_passed(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['component_temp_test_passed']

    @property
    def component_us_test_passed(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['component_us_test_passed']

    @property
    def component_wifi_test_passed(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['component_wifi_test_passed']

    @property
    def creation_time(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['creation_time']

    @property
    def device_external_color(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['device_external_color']

    @property
    def device_locale(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['device_locale']

    @property
    def fabric_id(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['fabric_id']

    @property
    def factory_loaded_languages(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['factory_loaded_languages']

    @property
    def gesture_hush_enable(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['gesture_hush_enable']

    @property
    def heads_up_enable(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['heads_up_enable']

    @property
    def home_alarm_link_capable(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['home_alarm_link_capable']

    @property
    def home_alarm_link_connected(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['home_alarm_link_connected']

    @property
    def home_alarm_link_type(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['home_alarm_link_type']

    @property
    def hushed_state(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['hushed_state']

    @property
    def installed_locale(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['installed_locale']

    @property
    def kl_software_version(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['kl_software_version']

    @property
    def latest_manual_test_cancelled(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['latest_manual_test_cancelled']

    @property
    def latest_manual_test_end_utc_secs(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['latest_manual_test_end_utc_secs']

    @property
    def latest_manual_test_start_utc_secs(self):
        # TODO confirm units, deprecate for new method name
        return self._device.get('last_manual_test_time')

    @property
    def last_manual_test_time(self):
        # TODO parse time, check that it's in the dict
        return self._device.get('last_manual_test_time')

    @property
    def line_power_present(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['line_power_present']

    @property
    def night_light_continuous(self):
        raise NotImplementedError("No longer available in Nest API")
        # if 'night_light_continuous' in self._device:
        #     return self._device['night_light_continuous']

    @property
    def night_light_enable(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['night_light_enable']

    @property
    def ntp_green_led_enable(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['ntp_green_led_enable']

    @property
    def product_id(self):
        return self._device.get('product_id')

    @property
    def replace_by_date_utc_secs(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['replace_by_date_utc_secs']

    @property
    def resource_id(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['resource_id']

    @property
    def smoke_sequence_number(self):
        return self._device['smoke_sequence_number']

    @property
    def smoke_status(self):
        return self._device['smoke_alarm_state']

    @property
    def software_version(self):
        return self._device['software_version']

    @property
    def spoken_where_id(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['spoken_where_id']

    @property
    def steam_detection_enable(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['steam_detection_enable']

    @property
    def thread_mac_address(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['thread_mac_address']

    @property
    def wifi_ip_address(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['wifi_ip_address']

    @property
    def wifi_mac_address(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['wifi_mac_address']

    @property
    def wifi_regulatory_domain(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['wifi_regulatory_domain']

    @property
    def wired_led_enable(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['wired_led_enable']

    @property
    def wired_or_battery(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['wired_or_battery']


class ActivityZone(NestBase):
    def __init__(self, camera, zone_id):
        self.camera = camera
        NestBase.__init__(self, camera.serial, camera._nest_api)
        # camera's activity_zone dict has int, but an event's list of
        # activity_zone ids is strings `\/0_0\/`
        self._zone_id = int(zone_id)

    @property
    def _camera(self):
        return self.camera._device

    @property
    def _repr_name(self):
        return self.name

    @property
    def _activity_zone(self):
        return next(
            z for z in self._camera['activity_zones']
            if z['id'] == self.zone_id)

    @property
    def zone_id(self):
        return self._zone_id

    @property
    def name(self):
        return self._activity_zone['name']


class CameraEvent(NestBase):
    def __init__(self, camera):
        NestBase.__init__(self, camera.serial, camera._nest_api)
        self.camera = camera

    @property
    def _camera(self):
        return self.camera._device

    @property
    def _event(self):
        return self._camera.get('last_event')

    def __repr__(self):
        return '<%s>' % (self.__class__.__name__)

    def activity_in_zone(self, zone_id):
        if 'activity_zone_ids' in self._event:
            return str(zone_id) in self._event['activity_zone_ids']
        return False

    @property
    def activity_zones(self):
        if 'activity_zone_ids' in self._event:
            return [ActivityZone(self, z)
                    for z in self._event['activity_zone_ids']]

    @property
    def animated_image_url(self):
        return self._event.get('animated_image_url')

    @property
    def app_url(self):
        return self._event.get('app_url')

    @property
    def has_motion(self):
        return self._event.get('has_motion')

    @property
    def has_person(self):
        return self._event.get('has_person')

    @property
    def has_sound(self):
        return self._event.get('has_sound')

    @property
    def image_url(self):
        return self._event.get('image_url')

    @property
    def start_time(self):
        if 'start_time' in self._event:
            return parse_time(self._event['start_time'])

    @property
    def end_time(self):
        if 'end_time' in self._event:
            return parse_time(self._event['end_time'])

    @property
    def urls_expire_time(self):
        if 'urls_expire_time' in self._event:
            return parse_time(self._event['urls_expire_time'])

    @property
    def web_url(self):
        return self._event.get('web_url')

    @property
    def is_ongoing(self):
        if self.end_time is not None:
            # sometimes, existing event is updated with a new start time
            # that's before the end_time which implies something new
            if self.start_time > self.end_time:
                return True

            now = datetime.datetime.now(self.end_time.tzinfo)
            # end time should be in the past
            return self.end_time > now
        # no end_time implies it's ongoing
        return True

    def has_ongoing_motion_in_zone(self, zone_id):
        if self.is_ongoing and self.has_motion:
            return self.activity_in_zone(zone_id)

    def has_ongoing_sound(self):
        if self.is_ongoing:
            return self.has_sound

    def has_ongoing_motion(self):
        if self.is_ongoing:
            return self.has_motion

    def has_ongoing_person(self):
        if self.is_ongoing:
            return self.has_person


class Camera(Device):
    @property
    def is_camera(self):
        return True

    @property
    def _device(self):
        return self._devices[CAMERAS][self._serial]

    @property
    def ongoing_event(self):
        if self.last_event is not None and self.last_event.is_ongoing:
            return self.last_event

    def has_ongoing_motion_in_zone(self, zone_id):
        if self.ongoing_event is not None:
            return self.last_event.has_ongoing_motion_in_zone(zone_id)
        return False

    @property
    def sound_detected(self):
        if self.ongoing_event is not None:
            return self.last_event.has_ongoing_sound()
        return False

    @property
    def motion_detected(self):
        if self.ongoing_event is not None:
            return self.last_event.has_ongoing_motion()
        return False

    @property
    def person_detected(self):
        if self.ongoing_event is not None:
            return self.last_event.has_ongoing_person()
        return False

    @property
    def activity_zones(self):
        return [ActivityZone(self, z['id'])
                for z in self._device.get('activity_zones', [])]

    @property
    def last_event(self):
        if 'last_event' in self._device:
            return CameraEvent(self)

    @property
    def is_streaming(self):
        return self._device.get('is_streaming')

    @is_streaming.setter
    def is_streaming(self, value):
        self._set('devices/cameras', {'is_streaming': value})

    @property
    def is_video_history_enabled(self):
        return self._device.get('is_video_history_enabled')

    @property
    def is_audio_enabled(self):
        return self._device.get('is_audio_input_enabled')

    @property
    def is_public_share_enabled(self):
        return self._device.get('is_public_share_enabled')

    @property
    def capabilities(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['capabilities']

    @property
    def cvr(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['cvr_enrolled']

    @property
    def nexustalk_host(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['direct_nexustalk_host']

    @property
    def download_host(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['download_host']

    @property
    def last_connected(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['last_connected_time']

    @property
    def last_cuepoint(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['last_cuepoint']

    @property
    def live_stream(self):
        # return self._device['live_stream_host']
        raise NotImplementedError("No longer available in Nest API")

    @property
    def mac_address(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['mac_address']

    @property
    def model(self):
        return self._device['model']

    @property
    def nexus_api_http_server_url(self):
        # return self._device['nexus_api_http_server_url']
        raise NotImplementedError("No longer available in Nest API")

    @property
    def streaming_state(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['streaming_state']

    @property
    def component_hum_test_passed(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['component_hum_test_passed']

    @property
    def component_led_test_passed(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['component_led_test_passed']

    @property
    def component_pir_test_passed(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['component_pir_test_passed']

    @property
    def component_smoke_test_passed(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['component_smoke_test_passed']

    @property
    def component_temp_test_passed(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['component_temp_test_passed']

    @property
    def component_us_test_passed(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['component_us_test_passed']

    @property
    def component_wifi_test_passed(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['component_wifi_test_passed']

    @property
    def creation_time(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['creation_time']

    @property
    def device_external_color(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['device_external_color']

    @property
    def device_locale(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['device_locale']

    @property
    def fabric_id(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['fabric_id']

    @property
    def factory_loaded_languages(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['factory_loaded_languages']

    @property
    def installed_locale(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['installed_locale']

    @property
    def kl_software_version(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['kl_software_version']

    @property
    def product_id(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['product_id']

    @property
    def resource_id(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['resource_id']

    @property
    def software_version(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['software_version']

    @property
    def spoken_where_id(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['spoken_where_id']

    @property
    def thread_mac_address(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['thread_mac_address']

    @property
    def where_id(self):
        return self._device['where_id']

    @property
    def wifi_ip_address(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['wifi_ip_address']

    @property
    def wifi_mac_address(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['wifi_mac_address']

    @property
    def wifi_regulatory_domain(self):
        raise NotImplementedError("No longer available in Nest API")
        # return self._device['wifi_regulatory_domain']

    @property
    def snapshot_url(self):
        if ('snapshot_url' in self._device and
                self._device['snapshot_url'] != SIMULATOR_SNAPSHOT_URL):
            return self._device['snapshot_url']
        else:
            return SIMULATOR_SNAPSHOT_PLACEHOLDER_URL


class Structure(NestBase):
    @property
    def _structure(self):
        return self._nest_api._status[STRUCTURES][self._serial]

    def _set_away(self, value, auto_away=False):
        self._set('structures', {'away': AWAY_MAP[value]})

    @property
    def away(self):
        return self._structure['away']

    @away.setter
    def away(self, value):
        self._set_away(value)

    @property
    def country_code(self):
        return self._structure.get('country_code')

    @property
    def devices(self):
        raise NotImplementedError("Use thermostats instead")

    @property
    def thermostats(self):
        if THERMOSTATS in self._structure:
            return [Thermostat(devid, self._nest_api)
                    for devid in self._structure[THERMOSTATS]]
        else:
            return []

    @property
    def protectdevices(self):
        raise NotImplementedError("Use smoke_co_alarms instead")

    @property
    def smoke_co_alarms(self):
        if SMOKE_CO_ALARMS in self._structure:
            return [SmokeCoAlarm(devid, self._nest_api)
                    for devid in self._structure[SMOKE_CO_ALARMS]]
        else:
            return []

    @property
    def cameradevices(self):
        raise NotImplementedError("Use cameras instead")

    @property
    def cameras(self):
        if CAMERAS in self._structure:
            return [Camera(devid, self._nest_api)
                    for devid in self._structure[CAMERAS]]
        else:
            return []

    @property
    def dr_reminder_enabled(self):
        raise NotImplementedError("Deprecated Nest API")
        # return self._structure['dr_reminder_enabled']

    @property
    def emergency_contact_description(self):
        raise NotImplementedError("Deprecated Nest API")
        # return self._structure['emergency_contact_description']

    @property
    def emergency_contact_type(self):
        raise NotImplementedError("Deprecated Nest API")
        # return self._structure['emergency_contact_type']

    @property
    def emergency_contact_phone(self):
        raise NotImplementedError("Deprecated Nest API")
        # return self._structure['emergency_contact_phone']

    @property
    def enhanced_auto_away_enabled(self):
        # FIXME there is probably an equivilant thing for this
        raise NotImplementedError("Deprecated Nest API")
        # return self._structure['topaz_enhanced_auto_away_enabled']

    @property
    def eta_preconditioning_active(self):
        # FIXME there is probably an equivilant thing for this
        # or something that can be recommended
        raise NotImplementedError("Deprecated Nest API")
        # return self._structure['eta_preconditioning_active']

    @property
    def house_type(self):
        raise NotImplementedError("Deprecated Nest API")
        # return self._structure['house_type']

    @property
    def hvac_safety_shutoff_enabled(self):
        raise NotImplementedError("Deprecated Nest API")
        # return self._structure['hvac_safety_shutoff_enabled']

    @property
    def name(self):
        return self._structure['name']

    @name.setter
    def name(self, value):
        self._set('structure', {'name': value})

    @property
    def location(self):
        raise NotImplementedError("Deprecated Nest API")
        # return self._structure.get('location')

    @property
    def address(self):
        raise NotImplementedError("Deprecated Nest API")
        # return self._structure.get('street_address')

    @property
    def num_thermostats(self):
        if THERMOSTATS in self._structure:
            return len(self._structure[THERMOSTATS])
        else:
            return 0

    @property
    def num_cameras(self):
        if CAMERAS in self._structure:
            return len(self._structure[CAMERAS])
        else:
            return 0

    @property
    def num_smokecoalarms(self):
        if SMOKE_CO_ALARMS in self._structure:
            return len(self._structure[SMOKE_CO_ALARMS])
        else:
            return 0

    @property
    def measurement_scale(self):
        raise NotImplementedError(
            "Deprecated Nest API, see temperature_scale on "
            "thermostats instead")
        # return self._structure['measurement_scale']

    @property
    def postal_code(self):
        # TODO check permissions if this is empty?
        return self._structure.get('postal_code')

    @property
    def renovation_date(self):
        raise NotImplementedError("Deprecated Nest API")
        # return self._structure['renovation_date']

    @property
    def structure_area(self):
        raise NotImplementedError("Deprecated Nest API")
        # return self._structure['structure_area']

    @property
    def time_zone(self):
        if 'time_zone' in self._structure:
            return self._structure['time_zone']

    @property
    def peak_period_start_time(self):
        if 'peak_period_start_time' in self._structure:
            return parse_time(self._structure['peak_period_start_time'])

    @property
    def peak_period_end_time(self):
        if 'peak_period_end_time' in self._structure:
            return parse_time(self._structure['peak_period_end_time'])

    @property
    def eta_begin(self):
        if 'eta_begin' in self._structure:
            return parse_time(self._structure['eta_begin'])

    @property
    def wheres(self):
        return self._structure['wheres']

    @wheres.setter
    def wheres(self, value):
        self._set('where', {'wheres': value})

    def add_where(self, name, ident=None):
        name = name.lower()

        if name in self.wheres:
            return self.wheres[name]

        name = ' '.join([n.capitalize() for n in name.split()])
        wheres = copy.copy(self.wheres)

        if ident is None:
            ident = str(uuid.uuid4())

        wheres.append({'name': name, 'where_id': ident})
        self.wheres = wheres

        return self.add_where(name)

    def remove_where(self, name):
        name = name.lower()

        if name not in self.wheres:
            return None

        ident = self.wheres[name]

        wheres = [w for w in copy.copy(self.wheres)
                  if w['name'] != name and w['where_id'] != ident]

        self.wheres = wheres
        return ident


class Nest(object):
    def __init__(self, username=None, password=None,
                 user_agent=None,
                 access_token=None, access_token_cache_file=None,
                 local_time=False,
                 client_id=None, client_secret=None,
                 product_version=None):
        self._urls = {}
        self._limits = {}
        self._user = None
        self._userid = None
        self._weave = None
        self._staff = False
        self._superuser = False
        self._email = None
        self._queue = collections.deque(maxlen=2)
        self._event_thread = None
        self._update_event = threading.Event()
        self._queue_lock = threading.Lock()

        if local_time:
            raise ValueError("local_time no longer supported")

        if user_agent:
            raise ValueError("user_agent no longer supported")

        self._access_token = access_token
        self._client_id = client_id
        self._client_secret = client_secret
        self._product_version = product_version

        self._session = requests.Session()
        auth = NestAuth(client_id=self._client_id,
                        client_secret=self._client_secret,
                        session=self._session, access_token=access_token,
                        access_token_cache_file=access_token_cache_file)
        self._session.auth = auth

    @property
    def update_event(self):
        return self._update_event

    @property
    def authorization_required(self):
        return self.never_authorized or \
            self.invalid_access_token or \
            self.client_version_out_of_date

    @property
    def never_authorized(self):
        return self.access_token is None

    @property
    def invalid_access_token(self):
        try:
            self._get("/")
            return False
        except AuthorizationError:
            return True

    @property
    def client_version_out_of_date(self):
        if self._product_version is not None:
            try:
                return self.client_version < self._product_version
            # an error means they need to authorize anyways
            except AuthorizationError:
                return True
        return False

    @property
    def authorize_url(self):
        state = hashlib.md5(os.urandom(32)).hexdigest()
        return AUTHORIZE_URL.format(self._client_id, state)

    def request_token(self, pin):
        self._session.auth.pin = pin
        self._session.auth.login()

    @property
    def access_token(self):
        return self._access_token or self._session.auth.access_token

    def _handle_ratelimit(self, res, verb, url, data,
                          max_retries=10, default_wait=5,
                          stream=False, headers=None):
        response = res
        retries = 0
        while response.status_code == 429 and retries <= max_retries:
            retries += 1
            retry_after = response.headers['Retry-After']
            # Default Retry Time
            wait = default_wait

            try:
                # Checks if retry_after is a number
                wait = float(retry_after)
            except ValueError:
                # If not:
                try:
                    # Checks if retry_after is a HTTP date
                    now = datetime.datetime.now()
                    wait = (now - parse_time(retry_after)).total_seconds()
                except ValueError:
                    # Does nothing and uses default (shouldn't happen)
                    pass

            time.sleep(wait)
            response = self._session.request(verb, url,
                                             allow_redirects=False,
                                             stream=stream,
                                             headers=headers,
                                             data=data)
        return response

    def _open_data_stream(self, path="/"):
        url = "%s%s" % (API_URL, path)

        # Opens the data stream
        headers = {'Accept': 'text/event-stream'}
        response = self._session.get(url, stream=True, headers=headers,
                                     allow_redirects=False)

        if response.status_code == 401:
            raise AuthorizationError(response)

        if response.status_code == 429:
            response = self._handle_ratelimit(response, 'GET', url, None,
                                              max_retries=10,
                                              default_wait=5,
                                              stream=True,
                                              headers=headers)

        if response.status_code == 307:
            redirect_url = response.headers['Location']
            response = self._session.get(redirect_url,
                                         allow_redirects=False,
                                         headers=headers,
                                         stream=True)
            if response.status_code == 429:
                response = self._handle_ratelimit(response, 'GET', url, None,
                                                  max_retries=10,
                                                  default_wait=5,
                                                  stream=True,
                                                  headers=headers)

        ready_event = threading.Event()
        self._event_thread = threading.Thread(target=self._start_event_loop,
                                              args=(response,
                                                    self._queue,
                                                    ready_event,
                                                    self._update_event))
        self._event_thread.setDaemon(True)
        self._event_thread.start()
        ready_event.wait(timeout=10)

    def _start_event_loop(self, response, queue, ready_event, update_event):
        client = sseclient.SSEClient(response.iter_content())
        for event in client.events():
            event_type = event.event
            if event_type == 'open' or event_type == 'keep-alive':
                pass
            elif event_type == 'put':
                queue.appendleft(json.loads(event.data))
                update_event.set()
            elif event_type == 'auth_revoked':
                raise AuthorizationError(None,
                                         msg='Auth token has been revoked')
            elif event_type == 'error':
                raise APIError(None, msg=event.data)

            if not ready_event.is_set():
                ready_event.set()
        response.close()
        queue.clear()

    def _request(self, verb, path="/", data=None):
        url = "%s%s" % (API_URL, path)

        if data is not None:
            data = json.dumps(data)

        response = self._session.request(verb, url,
                                         allow_redirects=False,
                                         data=data)
        if response.status_code == 200:
            return response.json()

        if response.status_code == 401:
            raise AuthorizationError(response)

        # Rate Limit Exceeded Catch
        if response.status_code == 429:
            response = self._handle_ratelimit(response, verb, url, data,
                                              max_retries=10,
                                              default_wait=5)

            # Prevent this from catching as APIError
            if response.status_code == 200:
                return response.json()

        # This will handle the error if max_retries is exceeded
        if response.status_code != 307:
            raise APIError(response)

        redirect_url = response.headers['Location']
        response = self._session.request(verb, redirect_url,
                                         allow_redirects=False,
                                         data=data)

        # Rate Limit Exceeded Catch
        if response.status_code == 429:
            response = self._handle_ratelimit(response, verb, redirect_url,
                                              data, max_retries=10,
                                              default_wait=5)

        # This will handle the error if max_retries is exceeded
        if 400 <= response.status_code < 600:
            raise APIError(response)

        return response.json()

    def _get(self, path="/"):
        return self._request('GET', path)

    def _put(self, path="/", data=None):
        return self._request('PUT', path, data=data)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    @property
    def _status(self):
        self._queue_lock.acquire()
        if len(self._queue) == 0 or not self._queue[0]:
            self._open_data_stream("/")
        self._queue_lock.release()

        self._queue_lock.acquire(False)
        value = self._queue[0]['data']
        self._queue_lock.release()
        if not value:
            value = self._get("/")

        return value

    @property
    def _metadata(self):
        return self._status[METADATA]

    @property
    def client_version(self):
        return self._metadata['client_version']

    @property
    def _devices(self):
        return self._status[DEVICES]

    @property
    def devices(self):
        raise NotImplementedError("Use thermostats instead")

    @property
    def thermostats(self):
        return [Thermostat(devid, self)
                for devid in self._devices.get(THERMOSTATS, [])]

    @property
    def protectdevices(self):
        raise NotImplementedError("Use smoke_co_alarms instead")

    @property
    def smoke_co_alarms(self):
        return [SmokeCoAlarm(devid, self)
                for devid in self._devices.get(SMOKE_CO_ALARMS, [])]

    @property
    def cameradevices(self):
        raise NotImplementedError("Use cameras instead")

    @property
    def cameras(self):
        return [Camera(devid, self)
                for devid in self._devices.get(CAMERAS, [])]

    @property
    def structures(self):
        return [Structure(stid, self)
                for stid in self._status[STRUCTURES]]

    @property
    def urls(self):
        raise NotImplementedError("Deprecated Nest API")

    @property
    def user(self):
        raise NotImplementedError("Deprecated Nest API")
