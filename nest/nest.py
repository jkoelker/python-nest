# -*- coding:utf-8 -*-

import collections
import copy
import datetime
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


LOGIN_URL = 'https://home.nest.com/user/login'
AWAY_MAP = {'on': True,
            'away': True,
            'off': False,
            'home': False,
            True: True,
            False: False}
AZIMUTH_MAP = {'N': 0.0, 'NNE': 22.5, 'NE': 45.0, 'ENE': 67.5, 'E': 90.0,
               'ESE': 112.5, 'SE': 135.0, 'SSE': 157.5, 'S': 180.0,
               'SSW': 202.5, 'SW': 225.0, 'WSW': 247.5, 'W': 270.0,
               'WNW': 292.5, 'NW': 315.0, 'NNW': 337.5}
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
    def __init__(self, username, password, auth_callback=None, session=None,
                 access_token=None, access_token_cache_file=None):
        self._res = {}
        self.username = username
        self.password = password
        self.auth_callback = auth_callback
        self._access_token_cache_file = access_token_cache_file

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

    def _login(self, headers=None):
        data = {'username': self.username, 'password': self.password}

        post = requests.post

        if self._session:
            session = self._session()
            post = session.post

        response = post(LOGIN_URL, data=data, headers=headers)
        response.raise_for_status()
        self._res = response.json()

        self._cache()
        self._callback(self._res)

    def _perhaps_relogin(self, r, **kwargs):
        if r.status_code == 401:
            self._login(r.headers.copy())
            req = r.request.copy()
            req.hooks = hooks.default_hooks()
            req.headers['Authorization'] = 'Basic ' + self.access_token

            adapter = self._adapter
            if self._session:
                session = self.session()
                if session:
                    adapter = session.get_adapter(req.url)

            response = adapter.send(req, **kwargs)
            response.history.append(r)

            return response

        return r

    @property
    def access_token(self):
        return self._res.get('access_token')

    @property
    def urls(self):
        if not self._res.get('urls'):
            # NOTE(jkoelker) Bootstrap the URLs
            self._login()

        return self._res.get('urls')

    @property
    def user(self):
        return self._res.get('user')

    def __call__(self, r):
        if self.access_token:
            r.headers['Authorization'] = 'Basic ' + self.access_token

        r.register_hook('response', self._perhaps_relogin)
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
        self._time = forecast.get('observation_time',
                                  forecast.get('time',
                                               forecast.get('date')))

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
        self._weather = weather

        self._tz = None
        if local_time:
            if pytz:
                self._tz = pytz.timezone(weather['location']['timezone_long'])

            else:
                self._tz = NestTZ(weather['location']['gmt_offset'])

    @property
    def _current(self):
        return self._weather['current']

    @property
    def _daily(self):
        return self._weather['forecast']['daily']

    @property
    def _hourly(self):
        return self._weather['forecast']['hourly']

    @property
    def current(self):
        return Forecast(self._current, self._tz)

    @property
    def daily(self):
        return [Forecast(f, self._tz) for f in self._daily]

    @property
    def hourly(self):
        return [Forecast(f, self._tz) for f in self._hourly]


class NestBase(object):
    def __init__(self, serial, nest_api, local_time=False):
        self._serial = serial
        self._nest_api = nest_api
        self._local_time = local_time

    def __repr__(self):
        return '<%s: %s>' % (self.__class__.__name__, self._repr_name)

    def _set(self, what, data):
        url = '%s/v2/put/%s.%s' % (self._nest_api.urls['transport_url'],
                                   what, self._serial)
        response = self._nest_api._session.post(url, data=json.dumps(data))
        response.raise_for_status()

        self._nest_api._bust_cache()

    @property
    def _weather(self):
        return self._nest_api._weather[self.postal_code]

    @property
    def weather(self):
        return Weather(self._weather, self._local_time)

    @property
    def name(self):
        return self._serial

    @property
    def _repr_name(self):
        return self.name


class Device(NestBase):
    @property
    def _device(self):
        return self._nest_api._status['device'][self._serial]

    @property
    def _shared(self):
        return self._nest_api._status['shared'][self._serial]

    @property
    def _link(self):
        return self._nest_api._status['link'][self._serial]

    @property
    def _track(self):
        return self._nest_api._status['track'][self._serial]

    @property
    def _repr_name(self):
        if self.name:
            return self.name

        return self.where

    @property
    def structure(self):
        return Structure(self._link['structure'].split('.')[-1],
                         self._nest_api, self._local_time)

    @property
    def where(self):
        if 'where_id' in self._device:
            return self.structure.wheres[self._device['where_id']]

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
        return self._shared['hvac_fan_state']

    @fan.setter
    def fan(self, value):
        self._set('device', {'fan_mode': FAN_MAP.get(value, 'auto')})

    @property
    def humidity(self):
        return self._device['current_humidity']

    @property
    def target_humidity(self):
        return self._device['target_humidity']

    @target_humidity.setter
    def target_humidity(self, value):
        if value == 'auto':

            if self._weather['current']['temp_c'] >= 4.44:
                hum_value = 45
            elif self._weather['current']['temp_c'] >= -1.11:
                hum_value = 40
            elif self._weather['current']['temp_c'] >= -6.67:
                hum_value = 35
            elif self._weather['current']['temp_c'] >= -12.22:
                hum_value = 30
            elif self._weather['current']['temp_c'] >= -17.78:
                hum_value = 25
            elif self._weather['current']['temp_c'] >= -23.33:
                hum_value = 20
            elif self._weather['current']['temp_c'] >= -28.89:
                hum_value = 15
            elif self._weather['current']['temp_c'] >= -34.44:
                hum_value = 10
        else:
            hum_value = value

        if float(hum_value) != self._device['target_humidity']:
            self._set('device', {'target_humidity': float(hum_value)})

    @property
    def mode(self):
        return self._shared['target_temperature_type']

    @mode.setter
    def mode(self, value):
        self._set('shared', {'target_temperature_type': value.lower()})

    @property
    def name(self):
        return self._shared['name']

    @name.setter
    def name(self, value):
        self._set('shared', {'name': value})

    @property
    def hvac_ac_state(self):
        return self._shared['hvac_ac_state']

    @property
    def hvac_cool_x2_state(self):
        return self._shared['hvac_cool_x2_state']

    @property
    def hvac_heater_state(self):
        return self._shared['hvac_heater_state']

    @property
    def hvac_aux_heater_state(self):
        return self._shared['hvac_aux_heater_state']

    @property
    def hvac_heat_x2_state(self):
        return self._shared['hvac_heat_x2_state']

    @property
    def hvac_heat_x3_state(self):
        return self._shared['hvac_heat_x3_state']

    @property
    def hvac_alt_heat_state(self):
        return self._shared['hvac_alt_heat_state']

    @property
    def hvac_alt_heat_x2_state(self):
        return self._shared['hvac_alt_heat_x2_state']

    @property
    def hvac_emer_heat_state(self):
        return self._shared['hvac_emer_heat_state']

    @property
    def online(self):
        return self._track['online']

    @property
    def local_ip(self):
        return self._device['local_ip']

    @property
    def last_ip(self):
        return self._track['last_ip']

    @property
    def last_connection(self):
        return self._track['last_connection']

    @property
    def error_code(self):
        return self._device['error_code']

    @property
    def battery_level(self):
        return self._device['battery_level']

    @property
    def postal_code(self):
        return self._device['postal_code']

    @property
    def temperature(self):
        return self._shared['current_temperature']

    @temperature.setter
    def temperature(self, value):
        self.target = value

    @property
    def target(self):
        if self._shared['target_temperature_type'] == 'range':
            low = self._shared['target_temperature_low']
            high = self._shared['target_temperature_high']
            return LowHighTuple(low, high)

        return self._shared['target_temperature']

    @target.setter
    def target(self, value):
        data = {'target_change_pending': True}

        if self._shared['target_temperature_type'] == 'range':
            data['target_temperature_low'] = value[0]
            data['target_temperature_high'] = value[1]

        else:
            data['target_temperature'] = value

        self._set('shared', data)

    @property
    def away_temperature(self):
        low = None
        high = None

        if self._device['away_temperature_low_enabled']:
            low = self._device['away_temperature_low']

        if self._device['away_temperature_high_enabled']:
            high = self._device['away_temperature_high']

        return LowHighTuple(low, high)

    @away_temperature.setter
    def away_temperature(self, value):
        low, high = value

        data = {}
        if low is not None:
            data['away_temperature_low'] = low
            data['away_temperature_low_enabled'] = True

        else:
            data['away_temperature_low_enabled'] = False

        if high is not None:
            data['away_temperature_high'] = high
            data['away_temperature_high_enabled'] = True

        else:
            data['away_temperature_high_enabled'] = False

        self._set('device', data)


class Structure(NestBase):
    @property
    def _structure(self):
        return self._nest_api._status['structure'][self._serial]

    def _set_away(self, value, auto_away=False):
        self._set('structure', {'away': AWAY_MAP[value],
                                'away_timestamp': int(time.time()),
                                'away_setter': int(auto_away)})

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
        return [Device(devid.split('.')[-1], self._nest_api,
                       self._local_time)
                for devid in self._structure['devices']]

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
    def measurement_scale(self):
        return self._structure['measurement_scale']

    @property
    def postal_code(self):
        return self._structure['postal_code']

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
    def _wheres(self):
        return self._nest_api._status['where'][self._serial]['wheres']

    @property
    def wheres(self):
        ret = {w['name'].lower(): w['where_id'] for w in self._wheres}
        ret.update({v: k for k, v in ret.items()})
        return ret

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
    def __init__(self, username, password, cache_ttl=270,
                 user_agent='Nest/1.1.0.10 CFNetwork/548.0.4',
                 access_token=None, access_token_cache_file=None,
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
            self._urls = result['urls']
            self._limits = result['limits']
            self._user = result['user']
            self._userid = result['userid']
            self._weave = result['weave']
            self._staff = result['is_staff']
            self._superuser = result['is_superuser']
            self._email = result['email']

        self._user_agent = user_agent
        self._session = requests.Session()
        auth = NestAuth(username, password, auth_callback=auth_callback,
                        session=self._session, access_token=access_token,
                        access_token_cache_file=access_token_cache_file)
        self._session.auth = auth

        headers = {'user-agent': 'Nest/1.1.0.10 CFNetwork/548.0.4',
                   'X-nl-protocol-version': '1'}
        self._session.headers.update(headers)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    @property
    def _status(self):
        value, last_update = self._cache
        now = time.time()

        if not value or now - last_update > self._cache_ttl:
            url = self.urls['transport_url'] + '/v2/mobile/' + self.user
            response = self._session.get(url)
            response.raise_for_status()
            value = response.json()
            self._cache = (value, now)

        return value

    def _bust_cache(self):
        self._cache = (None, 0)

    @property
    def devices(self):
        return [Device(devid.split('.')[-1], self, self._local_time)
                for devid in self._status['device']]

    @property
    def structures(self):
        return [Structure(stid, self, self._local_time)
                for stid in self._status['structure']]

    @property
    def urls(self):
        return self._session.auth.urls

    @property
    def user(self):
        return self._session.auth.user
