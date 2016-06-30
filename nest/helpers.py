# -*- coding:utf-8 -*-
# a module of helper functions
# mostly for the configuration

import os

# use six for python2/python3 compatibility
from six.moves import configparser


def get_config(config_path=None, prog='nest'):
    if not config_path:
        config_path = os.path.sep.join(('~', '.config', prog, 'config'))

    defaults = {'celsius': False}
    config_file = os.path.expanduser(config_path)
    if os.path.exists(config_file):
        config = configparser.SafeConfigParser()
        config.read([config_file])
        if config.has_section('nest'):
            defaults.update(dict(config.items('nest')))

    return defaults


def get_auth_credentials(config_path=None):
    config = get_config(config_path)
    username = config.get('user')
    password = config.get('password')
    return username, password
