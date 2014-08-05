#! /usr/bin/python

'''
nest_thermostat -- a python interface to the Nest Thermostat
by Scott M Baker, smbaker@gmail.com, http://www.smbaker.com/
updated by Bob Pasker bob@pasker.net http://pasker.net
'''

import time
import os
import weakref

import requests
from requests import auth
from requests import adapters
from requests.compat import json
from requests import hooks


LOGIN_URL = 'https://home.nest.com/user/login'
AWAY_MAP = {'on': True,
            'away': True,
            'off': False,
            'home': False,
            True: True,
            False: False}
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
                                   os.O_WRONLY | os.O_CREAT, 0600),
                           'w') as f:
                json.dump(self._res, f)

    def _callback(self, res):
        if self.auth_callback is not None and callable(self.auth_callback):
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


class NestBase(object):
    def __init__(self, serial, nest_api):
        self._serial = serial
        self._nest_api = nest_api

    def __repr__(self):
        return '<%s: %s>' % (self.__class__.__name__, self.name)

    def _set(self, what, data):
        url = '%s/v2/put/%s.%s' % (self._nest_api.urls['transport_url'],
                                   what, self._serial)
        response = self._nest_api._session.post(url, data=json.dumps(data))
        response.raise_for_status()

        self._nest_api._bust_cache()

    @property
    def name(self):
        return self._serial


class Device(NestBase):
    @property
    def _device(self):
        return self._nest_api._status['device'][self._serial]

    @property
    def _shared(self):
        return self._nest_api._status['shared'][self._serial]

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
    def temperature(self):
        return self._shared['current_temperature']

    @temperature.setter
    def temperature(self, value):
        self.target = value

    @property
    def target(self):
        if self._shared['target_temperature_type'] == 'range':
            return (self._shared['target_temperature_low'],
                    self._shared['target_temperature_high'])

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


class Structure(NestBase):
    def _set(self, data):
        super(Structure, self)._set('structure', data)

    @property
    def _structure(self):
        return self._nest_api._status['structure'][self._serial]

    @property
    def away(self):
        return self._structure['away']

    @away.setter
    def away(self, value):
        self._set({'away': AWAY_MAP[value]})

    @property
    def devices(self):
        return [Device(devid.lstrip('device.'), self._nest_api)
                for devid in self._structure['devices']]

    @property
    def name(self):
        return self._structure['name']

    @name.setter
    def name(self, value):
        self._set({'name': value})

    @property
    def location(self):
        return self._structure['location']

    @property
    def address(self):
        return self._structure['street_address']

    @property
    def postal_code(self):
        return self._structure['postal_code']


class Nest(object):
    def __init__(self, username, password, cache_ttl=270,
                 user_agent='Nest/1.1.0.10 CFNetwork/548.0.4',
                 access_token=None, access_token_cache_file=None):
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
        return [Device(devid.lstrip('device.'), self)
                for devid in self._status['device']]

    @property
    def structures(self):
        return [Structure(stid, self) for stid in self._status['structure']]

    @property
    def urls(self):
        return self._session.auth.urls

    @property
    def user(self):
        return self._session.auth.user
