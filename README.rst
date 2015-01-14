=========================================================
Python API and command line tool for the Nest™ Thermostat
=========================================================

.. image:: https://travis-ci.org/jkoelker/python-nest.svg?branch=master
    :target: https://travis-ci.org/jkoelker/python-nest


Installation
============

.. code-block:: bash

    [sudo] pip install python-nest


Usage
=====

Module
------

You can import the module as `nest`.

.. code-block:: python

    import nest

    username = 'joe@user.com'
    password = 'swordfish'

    napi = nest.Nest(username, password)

    for structure in napi.structures:
        print 'Structure %s' % structure.name
        print '    Away: %s' % structure.away
        print '    Devices:'

        for device in structure.devices:
            print '        Device: %s' % device.name
            print '            Temp: %0.1f' % device.temperature


    # The Nest object can also be used as a context manager
    with nest.Nest(username, password) as napi:
        for device in napi.devices:
            device.temp = 23

    # Weather data is also availible under structure or device
    # The api is the same from either

    structure = napi.structures[0]
    time_str = structure.weather.current.datetime.strftime('%Y-%m-%d %H:%M:%S')
    print 'Current Weather at %s:' % time_str
    print '    Condition: %s' % structure.weather.current.condition
    print '    Temperature: %s' % structure.weather.current.temperature
    print '    Humidity: %s' % structure.weather.current.humidity
    print '    Wind Dir: %s' % structure.weather.current.wind.direction
    print '    Wind Azimuth: %s' % structure.weather.current.wind.azimuth
    print '    Wind Speed: %s' % structure.weather.current.wind.kph

    # NOTE: Hourly forecasts do not contain a "contidion" its value is `None`
    #       Wind Speed is likwise `None` as its generally not reported
    print 'Hourly Forcast:'
    for f in structure.weather.hourly:
        print '    %s:' % f.datetime.strftime('%Y-%m-%d %H:%M:%S')
        print '        Temperature: %s' % f.temperature
        print '        Humidity: %s' % f.humidity
        print '        Wind Dir: %s' % f.wind.direction
        print '        Wind Azimuth: %s' % f.wind.azimuth


    # NOTE: Daily forecasts temperature is a tuple of (low, high)
    print 'Daily Forcast:'
    for f in structure.weather.daily:
        print '    %s:' % f.datetime.strftime('%Y-%m-%d %H:%M:%S')
        print '    Condition: %s' % structure.weather.current.condition
        print '        Low: %s' % f.temperature[0]
        print '        High: %s' % f.temperature[1]
        print '        Humidity: %s' % f.humidity
        print '        Wind Dir: %s' % f.wind.direction
        print '        Wind Azimuth: %s' % f.wind.azimuth
        print '        Wind Speed: %s' % structure.weather.current.wind.kph


    # NOTE: By default all datetime objects are timezone unaware (UTC)
    #       By passing `local_time=True` to the `Nest` object datetime objects
    #       will be converted to the timezone reported by nest. If the `pytz`
    #       module is installed those timezone objects are used, else one is
    #       synthesized from the nest data
    napi = nest.Nest(username, password, local_time=True)
    print napi.structures[0].weather.current.dateimte.tzinfo


In the API all temperature values are in degrees celsius. Helper functions
for conversion are in the `utils` module:


.. code-block:: python

    from nest import utils as nest_utils
    temp = 23.5
    fahrenheit = nest_utils.c_to_f(temp)
    temp == nest_utils.f_to_c(fahrenheit)


The utils function use `decimal.Decimal` to ensure precision.

For "advanced" usage such as token caching, use the source, luke!

Command line
------------

.. code-block:: bash

    usage: nest [-h] [--conf FILE] [--token-cache TOKEN_CACHE_FILE] [-t TOKEN]
                [-u USER] [-p PASSWORD] [-c] [-s SERIAL] [-i INDEX]
                {temp,fan,mode,away,target,humid,target_hum,show} ...

    Command line interface to Nest™ Thermostats

    positional arguments:
      {temp,fan,mode,away,target,humid,target_hum,show}
                            command help
        temp                show/set temperature
        fan                 set fan "on" or "auto"
        mode                show/set current mode
        away                show/set current away status
        target              show current temp target
        humid               show current humidity
        target_hum          show/set target humidity
                                specify target humidity value or auto to auto-select a
                                humidity based on outside temp
        show                show everything



    optional arguments:
      -h, --help            show this help message and exit
      --conf FILE           config file (default ~/.config/nest/config)
      --token-cache TOKEN_CACHE_FILE
                            auth access token
      -t TOKEN, --token TOKEN
                            auth access token cache file
      -u USER, --user USER  username for nest.com
      -p PASSWORD, --password PASSWORD
                            password for nest.com
      -c, --celsius         use celsius instead of farenheit
      -s SERIAL, --serial SERIAL
                            optional, specify serial number of nest thermostat to
                            talk to
      -i INDEX, --index INDEX
                            optional, specify index number of nest to talk to

    examples:
        nest --user joe@user.com --password swordfish temp 73
        nest --user joe@user.com --password swordfish fan auto
        nest --user joe@user.com --password swordfish target_hum 35


A configuration file can also be specified to prevent username/password repitition.


.. code-block:: ini

    [DEFAULT]
    user = joe@user.com
    password = swordfish
    token_cache = ~/.config/nest/cache


The `[DEFAULT]` section may also be named `[nest]` for convience.


History
=======

This module was originally a fork of `nest_thermostat <https://github.com/FiloSottile/nest_thermostat>`
which was a fork of `pynest <https://github.com/smbaker/pynest`
