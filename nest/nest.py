# -*- coding:utf-8 -*-

import collections
import copy
import datetime
import hashlib
import time
import os
import uuid
import weakref

import requests
from requests import auth
from requests import adapters
from requests.compat import json
from requests import hooks

try:
    import pytz
except ImportError:
    pytz = None

ACCESS_TOKEN_URL = 'https://api.home.nest.com/oauth2/access_token'
AUTHORIZE_URL = 'https://home.nest.com/login/oauth2?client_id={0}&state={1}'
API_URL = 'https://developer-api.nest.com'
LOGIN_URL = 'https://home.nest.com/user/login'
SIMULATOR_SNAPSHOT_URL = 'https://developer.nest.com/simulator/api/v1/nest/devices/camera/snapshot'

AWAY_MAP = {'on': 'away',
            'away': 'away',
            'off': 'home',
            'home': 'home',
            True: 'away',
            False: 'home'}
AZIMUTH_MAP = {'N': 0.0, 'NNE': 22.5, 'NE': 45.0, 'ENE': 67.5, 'E': 90.0,
               'ESE': 112.5, 'SE': 135.0, 'SSE': 157.5, 'S': 180.0,
               'SSW': 202.5, 'SW': 225.0, 'WSW': 247.5, 'W': 270.0,
               'WNW': 292.5, 'NW': 315.0, 'NNW': 337.5}

AZIMUTH_ALIASES = (('North', 'N'),
                   ('North North East', 'NNE'),
                   ('North East', 'NE'),
                   ('North North East', 'NNE'),
                   ('East', 'E'),
                   ('East South East', 'ESE'),
                   ('South East', 'SE'),
                   ('South South East', 'SSE'),
                   ('South', 'S'),
                   ('South South West', 'SSW'),
                   ('South West', 'SW'),
                   ('West South West', 'WSW'),
                   ('West', 'W'),
                   ('West North West', 'WNW'),
                   ('North West', 'NW'),
                   ('North North West', 'NNW'))

for (alias, key) in AZIMUTH_ALIASES:
    AZIMUTH_MAP[alias] = AZIMUTH_MAP[key]

FAN_MAP = {'auto on': 'auto',
           'on': 'on',
           'auto': 'auto',
           'always on': 'on',
           '1': 'on',
           '0': 'auto',
           1: 'on',
           0: 'auto',
           True: 'on',
           False: 'auto'}


LowHighTuple = collections.namedtuple('LowHighTuple', ('low', 'high'))

DEVICES = 'devices'
STRUCTURES = 'structures'
THERMOSTATS = 'thermostats'
SMOKE_CO_ALARMS = 'smoke_co_alarms'
CAMERAS = 'cameras'

class APIError(Exception):
    def __init__(self, response):
        message = response.json()['error']
        # Call the base class constructor with the parameters it needs
        super(APIError, self).__init__(message)

        self.response = response

class AuthorizationError(Exception):
    def __init__(self, response):
        message = response.json()['error_description']
        # Call the base class constructor with the parameters it needs
        super(APIError, self).__init__(message)

        self.response = response

class NestTZ(datetime.tzinfo):
    def __init__(self, gmt_offset):
        self._offset = datetime.timedelta(hours=float(gmt_offset))
        self._name = gmt_offset

    def __repr__(self):
        return '<%s: gmt_offset=%s>' % (self.__class__.__name__,
                                        self._name)

    def utcoffset(self, dt):
        return self._offset

    def tzname(self, dt):
        return self._name

    def dst(self, dt):
        return datetime.timedelta(0)


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
            self.auth_callback(self._res)

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


class Wind(object):
    def __init__(self, direction=None, kph=None):
        self.direction = direction
        self.kph = kph

    @property
    def azimuth(self):
        return AZIMUTH_MAP[self.direction]


class Forecast(object):
    def __init__(self, forecast, tz=None):
        self._forecast = forecast
        self._tz = tz
        self.condition = forecast.get('condition')
        self.humidity = forecast['humidity']
        self._icon = forecast.get('icon')

        fget = forecast.get
        self._time = float(fget('observation_time',
                                fget('time',
                                     fget('date',
                                          fget('observation_epoch')))))

    def __repr__(self):
        return '<%s: %s>' % (self.__class__.__name__,
                             self.datetime.strftime('%Y-%m-%d %H:%M:%S'))

    @property
    def datetime(self):
        return datetime.datetime.fromtimestamp(self._time, self._tz)

    @property
    def temperature(self):
        if 'temp_low_c' in self._forecast:
            return LowHighTuple(self._forecast['temp_low_c'],
                                self._forecast['temp_high_c'])

        return self._forecast['temp_c']

    @property
    def wind(self):
        return Wind(self._forecast['wind_dir'], self._forecast.get('wind_kph'))


class Weather(object):
    def __init__(self, weather, local_time):
        raise NotImplementedError("Deprecated Nest API")


class NestBase(object):
    def __init__(self, serial, nest_api, local_time=False):
        self._serial = serial
        self._nest_api = nest_api
        self._local_time = local_time

    def __repr__(self):
        return '<%s: %s>' % (self.__class__.__name__, self._repr_name)

    def _set(self, what, data):
        path = '/%s/%s' % (what, self._serial)

        response = self._nest_api._put(path=path, data=data)
        self._nest_api._bust_cache()

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
    def name(self):
        return self._serial

    @property
    def _devices(self):
        return self._nest_api._devices

    @property
    def _repr_name(self):
        return self.name


class Device(NestBase):
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
    def _repr_name(self):
        if self.name:
            return self.name

        return self.where

    @property
    def structure(self):
        return Structure(self._device['structure_id'],
                         self._nest_api, self._local_time)

    # FIXME duplication with protect & camera where
    @property
    def where(self):
        if 'where_id' in self._device:
            return self.structure.wheres[self._device['where_id']]['name']

    @where.setter
    def where(self, value):
        value = value.lower()
        ident = self.structure.wheres.get(value)

        if ident is None:
            self.structure.add_where(value)
            ident = self.structure.wheres[value]

        self._set('device', {'where_id': ident})

    @property
    def fan(self):
        return self._device['fan_timer_active'] # FIXME confirm this is the same as old havac_fan_state

    @fan.setter
    def fan(self, value):
        self._set('device', {'fan_mode': FAN_MAP.get(value, 'auto')})

    @property
    def humidity(self):
        return self._device['humidity']

    @property
    def target_humidity(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['target_humidity']

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
        return self._device['hvac_mode'] # FIXME confirm same as target_temperature_type

    @mode.setter
    def mode(self, value):
        self._set('devices/thermostats', {'hvac_mode': value.lower()})

    @property
    def name(self):
        return self._device['name']

    @name.setter
    def name(self, value):
        self._set('shared', {'name': value})

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
        raise NotImplementedError("No longer available in Nest API")
        # return self._shared['hvac_emer_heat_state']

    @property
    def online(self):
        return self._device['is_online']

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
        return self._structure.postal_code
        #return self._device['postal_code']

    def _temp_key(self, key):
        return "%s_%s" % (key, self.temperature_scale.lower())

    @property
    def temperature_scale(self):
        return self._device['temperature_scale']

    @property
    def is_locked(self):
        return self._device['is_locked']

    @property
    def locked_temperature(self):
        low = self._device[self._temp_key('locked_temp_min')]
        high = self._device[self._temp_key('locked_temp_max')]
        return LowHighTuple(low, high)

    @property
    def temperature(self):
        return self._device[self._temp_key('ambient_temperature')]

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
            data[self._temp_key('target_temperature_low')] = value[0]
            data[self._temp_key('target_temperature_high')] = value[1]
        else:
            data[self._temp_key('target_temperature')] = value

        self._set('devices/thermostats', data)

    @property
    def away_temperature(self):
        # see https://nestdevelopers.io/t/new-things-for-fall/226
        raise NotImplementedError("Deprecated Nest API, use eco_temperature instead")

    @away_temperature.setter
    def away_temperature(self, value):
        # see https://nestdevelopers.io/t/new-things-for-fall/226
        raise NotImplementedError("Deprecated Nest API, use eco_temperature instead")

    @property
    def eco_temperature(self):
        low = self._device[self._temp_key('eco_temperature_low')]
        high = self._device[self._temp_key('eco_temperature_high')]

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
        return self._device['can_heat']

    @property
    def can_cool(self):
        return self._device['can_cool']

    @property
    def has_humidifier(self):
        return self._device['has_humidifier']

    @property
    def has_dehumidifier(self):
        return self._device['has_dehumidifier']

    @property
    def has_fan(self):
        return self._device['has_fan']

    @property
    def has_hot_water_control(self):
        return self._device['has_hot_water_control']

    @property
    def hot_water_temperature(self):
        return self._device['hot_water_temperature']


class ProtectDevice(NestBase):
    @property
    def _device(self):
        return self._devices[SMOKE_CO_ALARMS][self._serial]

    @property
    def _repr_name(self):
        if self.name:
            return self.name

        return self.where

    @property
    def name(self):
        return self._device['name']

    @property
    def structure(self):
        return Structure(self._device['structure_id'],
                         self._nest_api, self._local_time)

    @property
    def where(self):
        if 'where_id' in self._device:
            return self.structure.wheres[self._device['where_id']]['name']

    @property
    def auto_away(self):
        raise NotImplementedError("No longer available in Nest API.")
        #return self._device['auto_away']

    @property
    def battery_health(self):
        return self._device['battery_health']

    @property
    def battery_health_state(self):
        raise NotImplementedError("use battery_health instead")

    @property
    def battery_level(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['battery_level']

    @property
    def capability_level(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['capability_level']

    @property
    def certification_body(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['certification_body']

    @property
    def co_blame_duration(self):
        raise NotImplementedError("No longer available in Nest API")
        #if 'co_blame_duration' in self._device:
        #    return self._device['co_blame_duration']

    @property
    def co_blame_threshold(self):
        raise NotImplementedError("No longer available in Nest API")
        #if 'co_blame_threshold' in self._device:
        #    return self._device['co_blame_threshold']

    @property
    def co_previous_peak(self):
        raise NotImplementedError("No longer available in Nest API")
        #if 'co_previous_peak' in self._device:
        #    return self._device['co_previous_peak']

    @property
    def co_sequence_number(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['co_sequence_number']

    @property
    def co_status(self):
        return self._device['co_alarm_state']

    @property
    def component_als_test_passed(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['component_als_test_passed']

    @property
    def component_co_test_passed(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['component_co_test_passed']

    @property
    def component_heat_test_passed(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['component_heat_test_passed']

    @property
    def component_hum_test_passed(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['component_hum_test_passed']

    @property
    def component_led_test_passed(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['component_led_test_passed']

    @property
    def component_pir_test_passed(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['component_pir_test_passed']

    @property
    def component_smoke_test_passed(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['component_smoke_test_passed']

    @property
    def component_temp_test_passed(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['component_temp_test_passed']

    @property
    def component_us_test_passed(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['component_us_test_passed']

    @property
    def component_wifi_test_passed(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['component_wifi_test_passed']

    @property
    def creation_time(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['creation_time']

    @property
    def description(self):
        return self._device['name_long']

    @property
    def device_external_color(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['device_external_color']

    @property
    def device_locale(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['device_locale']

    @property
    def fabric_id(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['fabric_id']

    @property
    def factory_loaded_languages(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['factory_loaded_languages']

    @property
    def gesture_hush_enable(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['gesture_hush_enable']

    @property
    def heads_up_enable(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['heads_up_enable']

    @property
    def home_alarm_link_capable(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['home_alarm_link_capable']

    @property
    def home_alarm_link_connected(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['home_alarm_link_connected']

    @property
    def home_alarm_link_type(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['home_alarm_link_type']

    @property
    def hushed_state(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['hushed_state']

    @property
    def installed_locale(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['installed_locale']

    @property
    def kl_software_version(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['kl_software_version']

    @property
    def latest_manual_test_cancelled(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['latest_manual_test_cancelled']

    @property
    def latest_manual_test_end_utc_secs(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['latest_manual_test_end_utc_secs']

    @property
    def latest_manual_test_start_utc_secs(self):
        return self._device['last_manual_test_time'] # TODO confirm units

    @property
    def line_power_present(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['line_power_present']

    @property
    def night_light_continuous(self):
        raise NotImplementedError("No longer available in Nest API")
        #if 'night_light_continuous' in self._device:
        #    return self._device['night_light_continuous']

    @property
    def night_light_enable(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['night_light_enable']

    @property
    def ntp_green_led_enable(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['ntp_green_led_enable']

    @property
    def product_id(self):
        return self._device['product_id']

    @property
    def replace_by_date_utc_secs(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['replace_by_date_utc_secs']

    @property
    def resource_id(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['resource_id']

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
        #return self._device['spoken_where_id']

    @property
    def steam_detection_enable(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['steam_detection_enable']

    @property
    def thread_mac_address(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['thread_mac_address']

    @property
    def where_id(self):
        return self._device['where_id']

    @property
    def wifi_ip_address(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['wifi_ip_address']

    @property
    def wifi_mac_address(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['wifi_mac_address']

    @property
    def wifi_regulatory_domain(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['wifi_regulatory_domain']

    @property
    def wired_led_enable(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['wired_led_enable']

    @property
    def wired_or_battery(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['wired_or_battery']


class CameraDevice(NestBase):
    @property
    def _device(self):
        return self._devices[CAMERAS][self._serial]

    @property
    def name(self):
        return self._device['name']

    @property
    def _repr_name(self):
        if self.name:
            return self.name

        return self.where

    @property
    def structure(self):
        return Structure(self._device['structure_id'],
                         self._nest_api, self._local_time)

    @property
    def is_online(self):
        return self._device['is_online']

    @property
    def is_streaming(self):
        return self._device['is_streaming']

    @property
    def is_video_history_enabled(self):
        return self._device['is_video_history_enabled']

    @property
    def where(self):
        if 'where_id' in self._device:
            return self.structure.wheres[self._device['where_id']]['name']

    @property
    def is_audio_enabled(self):
        return self._device['is_audio_input_enabled']

    @property
    def is_public_share_enabled(self):
        return self._device['is_public_share_enabled']

    @property
    def capabilities(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['capabilities']

    @property
    def cvr(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['cvr_enrolled']

    @property
    def description(self):
        return self._device['name_long']

    @property
    def nexustalk_host(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['direct_nexustalk_host']

    @property
    def download_host(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['download_host']

    @property
    def last_connected(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['last_connected_time']

    @property
    def last_cuepoint(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['last_cuepoint']

    @property
    def live_stream(self):
        #return self._device['live_stream_host']
        raise NotImplementedError("No longer available in Nest API")

    @property
    def mac_address(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['mac_address']

    @property
    def model(self):
        return self._device['model']

    @property
    def nexus_api_http_server_url(self):
        #return self._device['nexus_api_http_server_url']
        raise NotImplementedError("No longer available in Nest API")

    @property
    def streaming_state(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['streaming_state']

    @property
    def component_hum_test_passed(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['component_hum_test_passed']

    @property
    def component_led_test_passed(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['component_led_test_passed']

    @property
    def component_pir_test_passed(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['component_pir_test_passed']

    @property
    def component_smoke_test_passed(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['component_smoke_test_passed']

    @property
    def component_temp_test_passed(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['component_temp_test_passed']

    @property
    def component_us_test_passed(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['component_us_test_passed']

    @property
    def component_wifi_test_passed(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['component_wifi_test_passed']

    @property
    def creation_time(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['creation_time']

    @property
    def device_external_color(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['device_external_color']

    @property
    def device_locale(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['device_locale']

    @property
    def fabric_id(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['fabric_id']

    @property
    def factory_loaded_languages(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['factory_loaded_languages']


    @property
    def installed_locale(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['installed_locale']

    @property
    def kl_software_version(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['kl_software_version']

    @property
    def product_id(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['product_id']

    @property
    def resource_id(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['resource_id']

    @property
    def software_version(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['software_version']

    @property
    def spoken_where_id(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['spoken_where_id']

    @property
    def thread_mac_address(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['thread_mac_address']

    @property
    def where_id(self):
        return self._device['where_id']

    @property
    def wifi_ip_address(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['wifi_ip_address']

    @property
    def wifi_mac_address(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['wifi_mac_address']

    @property
    def wifi_regulatory_domain(self):
        raise NotImplementedError("No longer available in Nest API")
        #return self._device['wifi_regulatory_domain']

    @property
    def snapshot_url(self):
        if self._device['snapshot_url'] != SIMULATOR_SNAPSHOT_URL:
            returnelf._device['snapshot_url']
        else:
            return 'https://media.giphy.com/media/WCwFvyeb6WJna/giphy.gif'


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
        return self._structure['country_code']

    @property
    def devices(self):
        if THERMOSTATS in self._structure:
            return [Device(devid, self._nest_api,
                           self._local_time)
                    for devid in self._structure[THERMOSTATS]]
        else:
            return []

    @property
    def protectdevices(self):
        if SMOKE_CO_ALARMS in self._structure:
            return [ProtectDevice(topazid, self._nest_api,
                                  self._local_time)
                    for topazid in self._structure[SMOKE_CO_ALARMS]]
        else:
            return []

    @property
    def cameradevices(self):
        if CAMERAS in self._structure:
            return [CameraDevice(devid, self._nest_api,
                                  self._local_time)
                    for devid in self._structure[CAMERAS]]
        else:
            return []

    @property
    def dr_reminder_enabled(self):
        return self._structure['dr_reminder_enabled']

    @property
    def emergency_contact_description(self):
        return self._structure['emergency_contact_description']

    @property
    def emergency_contact_type(self):
        return self._structure['emergency_contact_type']

    @property
    def emergency_contact_phone(self):
        return self._structure['emergency_contact_phone']

    @property
    def enhanced_auto_away_enabled(self):
        return self._structure['topaz_enhanced_auto_away_enabled']

    @property
    def eta_preconditioning_active(self):
        return self._structure['eta_preconditioning_active']

    @property
    def house_type(self):
        return self._structure['house_type']

    @property
    def hvac_safety_shutoff_enabled(self):
        return self._structure['hvac_safety_shutoff_enabled']

    @property
    def name(self):
        return self._structure['name']

    @name.setter
    def name(self, value):
        self._set('structure', {'name': value})

    @property
    def location(self):
        return self._structure.get('location')

    @property
    def address(self):
        return self._structure.get('street_address')

    @property
    def num_thermostats(self):
        return self._structure['num_thermostats']

    @property
    def postal_code(self):
        # TODO check permissions if this is empty?
        return self._structure.get('postal_code')

    @property
    def renovation_date(self):
        return self._structure['renovation_date']

    @property
    def structure_area(self):
        return self._structure['structure_area']

    @property
    def time_zone(self):
        return self._structure['time_zone']

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
        wheres = copy.copy(self._wheres)

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

        wheres = [w for w in copy.copy(self._wheres)
                  if w['name'] != name and w['where_id'] != ident]

        self.wheres = wheres
        return ident


class WeatherCache(object):
    def __init__(self, nest_api, cache_ttl=270):
        self._nest_api = nest_api
        self._cache_ttl = cache_ttl
        self._cache = {}

    def __getitem__(self, postal_code):
        value, last_update = self._cache.get(postal_code, (None, 0))
        now = time.time()

        if not value or now - last_update > self._cache_ttl:
            url = self._nest_api.urls['weather_url'] + postal_code
            response = self._nest_api._session.get(url)
            response.raise_for_status()
            value = response.json()[postal_code]
            self._cache[postal_code] = (value, now)

        return value


class Nest(object):
    def __init__(self, username=None, password=None, cache_ttl=270,
                 user_agent='Nest/1.1.0.10 CFNetwork/548.0.4',
                 access_token=None, access_token_cache_file=None,
                 client_id=None, client_secret=None,
                 local_time=False):
        self._urls = {}
        self._limits = {}
        self._user = None
        self._userid = None
        self._weave = None
        self._staff = False
        self._superuser = False
        self._email = None

        self._cache_ttl = cache_ttl
        self._cache = (None, 0)
        self._weather = WeatherCache(self)

        self._local_time = local_time

        def auth_callback(result):
            self._access_token = result['access_token']

        self._access_token = access_token
        self._client_id = client_id
        self._client_secret = client_secret

        self._session = requests.Session()
        auth = NestAuth(client_id=self._client_id, client_secret=self._client_secret,
                        session=self._session, access_token=access_token,
                        access_token_cache_file=access_token_cache_file)
        self._session.auth = auth


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

    #@property
    #def _headers(self):
    #    if self._access_token is not None:
    #        return {'Authorization': 'Bearer ' + self._access_token, 'Content-Type': 'application/json'}
    #    else:
    #        return {}

    def _request(self, verb, path = "/", data=None):
        url = "%s%s" % (API_URL, path)

        if data is not None:
            data = json.dumps(data)

        response = self._session.request(verb, url, allow_redirects=False, data=data)
        if response.status_code == 200:
            return response.json()

        if response.status_code != 307:
            raise APIError(response)

        redirect_url = response.headers['Location']
        response = self._session.request(verb, redirect_url, allow_redirects=False, data=data)
        # TODO check for 429 status code for too frequent access. see https://developers.nest.com/documentation/cloud/data-rate-limits
        if 400 <= response.status_code < 600:
            raise APIError(response)

        return response.json()

    def _get(self, path = "/"):
        return self._request('GET', path)

    def _put(self, path = "/", data=None):
        return self._request('PUT', path, data=data)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    @property
    def _status(self):
        value, last_update = self._cache
        now = time.time()

        if not value or now - last_update > self._cache_ttl:
            value = self._get("/")
            self._cache = (value, now)

        return value

    @property
    def _devices(self):
        return self._status[DEVICES]

    def _bust_cache(self):
        self._cache = (None, 0)

    @property
    def devices(self):
        return [Device(devid, self, self._local_time)
                for devid in self._devices[THERMOSTATS]]

    @property
    def protectdevices(self):
        return [ProtectDevice(topazid, self, self._local_time)
                for topazid in self._devices[SMOKE_CO_ALARMS]]\

    @property
    def cameradevices(self):
        return [CameraDevice(topazid, self, self._local_time)
                for topazid in self._devices[CAMERAS]]

    @property
    def structures(self):
        return [Structure(stid, self, self._local_time)
                for stid in self._status[STRUCTURES]]

    @property
    def urls(self):
        return self._session.auth.urls

    @property
    def user(self):
        return self._session.auth.user
