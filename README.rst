=========================================================
Python API and command line tool for the Nest™ Thermostat
=========================================================

.. image:: https://travis-ci.org/jkoelker/python-nest.svg?branch=master
    :target: https://travis-ci.org/jkoelker/python-nest


Installation
============

.. code-block:: bash

    [sudo] pip install python-nest


*NOTE* The ``4.x`` version uses the streaming endpoint. To use the older
polling/caching behavior pin your requirements to ``python-nest<4.0``.

*NOTE* The ``3.x`` version uses the Nest official api. As such, some functionality
was removed as it is not available. To keep the old version and functionality, make sure to set
your requirements to ``python-nest<3.0``.

Nest Developer Account
=======================


You will need a Nest developer account, and a Product on the Nest developer portal to use this module:

1. Visit `Nest Developers <https://developers.nest.com/>`_, and sign in. Create an account if you don't have one already.

2. Fill in the account details:

  - The "Company Information" can be anything.

3. Submit changes.

4. Click "`Products <https://developers.nest.com/products>`_" at top of page.

5. Click "`Create New Product <https://developers.nest.com/products/new>`_"

6. Fill in details:

  - Product name must be unique.

  - The description, users, urls can all be anything you want.

7. For permissions, check every box and if it's an option select the read/write option.

  - The description requires a specific format to be accepted.

8. Click "Create Product".

9. Once the new product page opens the "Product ID" and "Product Secret" are located on the right side. These will be used as client_id and client_secret below.


Usage
=====

Module
------

You can import the module as ``nest``.

.. code-block:: python

    import nest
    import sys

    client_id = 'XXXXXXXXXXXXXXX'
    client_secret = 'XXXXXXXXXXXXXXX'
    access_token_cache_file = 'nest.json'

    napi = nest.Nest(client_id=client_id, client_secret=client_secret, access_token_cache_file=access_token_cache_file)

    if napi.authorization_required:
        print('Go to ' + napi.authorize_url + ' to authorize, then enter PIN below')
        if sys.version_info[0] < 3:
            pin = raw_input("PIN: ")
        else:
            pin = input("PIN: ")
        napi.request_token(pin)

    for structure in napi.structures:
        print ('Structure %s' % structure.name)
        print ('    Away: %s' % structure.away)
        print ('    Devices:')

        for device in structure.thermostats:
            print ('        Device: %s' % device.name)
            print ('            Temp: %0.1f' % device.temperature)

    # Access advanced structure properties:
    for structure in napi.structures:
        print ('Structure   : %s' % structure.name)
        print (' Postal Code                    : %s' % structure.postal_code)
        print (' Country                        : %s' % structure.country_code)
        print (' num_thermostats                : %s' % structure.num_thermostats)

    # Access advanced device properties:
        for device in structure.thermostats:
            print ('        Device: %s' % device.name)
            print ('        Where: %s' % device.where)
            print ('            Mode       : %s' % device.mode)
            print ('            HVAC State : %s' % device.hvac_state)
            print ('            Fan        : %s' % device.fan)
            print ('            Fan Timer  : %i' % device.fan_timer)
            print ('            Temp       : %0.1fC' % device.temperature)
            print ('            Humidity   : %0.1f%%' % device.humidity)
            print ('            Target     : %0.1fC' % device.target)
            print ('            Eco High   : %0.1fC' % device.eco_temperature.high)
            print ('            Eco Low    : %0.1fC' % device.eco_temperature.low)

            print ('            hvac_emer_heat_state  : %s' % device.is_using_emergency_heat)

            print ('            online                : %s' % device.online)

    # The Nest object can also be used as a context manager
    with nest.Nest(client_id=client_id, client_secret=client_secret, access_token_cache_file=access_token_cache_file) as napi:
        for device in napi.thermostats:
            device.temperature = 23

    # Nest products can be updated to include other permissions. Before you
    # can access them with the API, a user has to authorize again. To handle this
    # and detect when re-authorization is required, pass in a product_version
    client_id = 'XXXXXXXXXXXXXXX'
    client_secret = 'XXXXXXXXXXXXXXX'
    access_token_cache_file = 'nest.json'
    product_version = 1337

    napi = nest.Nest(client_id=client_id, client_secret=client_secret, access_token_cache_file=access_token_cache_file, product_version=product_version)

    print("Never Authorized: %s" % napi.never_authorized)
    print("Invalid Token: %s" % napi.invalid_access_token)
    print("Client Version out of date: %s" % napi.client_version_out_of_date)
    if napi.authorization_required is None:
        print('Go to ' + napi.authorize_url + ' to authorize, then enter PIN below')
        pin = input("PIN: ")
        napi.request_token(pin)


    # NOTE: By default all datetime objects are timezone unaware (UTC)
    #       By passing ``local_time=True`` to the ``Nest`` object datetime objects
    #       will be converted to the timezone reported by nest. If the ``pytz``
    #       module is installed those timezone objects are used, else one is
    #       synthesized from the nest data
    napi = nest.Nest(username, password, local_time=True)
    print napi.structures[0].weather.current.datetime.tzinfo




In the API, all temperature values are reported and set in the temperature scale
the device is set to (as determined by the ``device.temperature_scale`` property).

Helper functions for conversion are in the ``utils`` module:

.. code-block:: python

    from nest import utils as nest_utils
    temp = 23.5
    fahrenheit = nest_utils.c_to_f(temp)
    temp == nest_utils.f_to_c(fahrenheit)


The utils function use ``decimal.Decimal`` to ensure precision.


Command line
------------

.. code-block:: bash

    usage: nest [-h] [--conf FILE] [--token-cache TOKEN_CACHE_FILE] [-t TOKEN]
                [--client-id CLIENTID] [--client-secret SECRET] [-c] [-s SERIAL] [-i INDEX]
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
        camera-show         show everything (for cameras)
        camera-streaming    show/set camera streaming


    optional arguments:
      -h, --help            show this help message and exit
      --conf FILE           config file (default ~/.config/nest/config)
      --token-cache TOKEN_CACHE_FILE
                            auth access token cache file
      -t TOKEN, --token TOKEN
                            auth access token
      --client-id ID        product id on developer.nest.com
      --client-secret SECRET
                            product secret for nest.com
      -c, --celsius         use celsius instead of farenheit
      -s SERIAL, --serial SERIAL
                            optional, specify serial number of nest thermostat to
                            talk to
      -S STRUCTURE, --structure STRUCTURE
                            optional, specify structure name toscope device
                            actions
      -i INDEX, --index INDEX
                            optional, specify index number of nest to talk to

    examples:
        # If your nest is not in range mode
        nest --conf myconfig --client-id CLIENTID --client-secret SECRET temp 73
        # If your nest is in range mode
        nest --conf myconfig --client-id CLIENTID --client-secret SECRET temp 66 73

        nest --conf myconfig --client-id CLIENTID --client-secret SECRET fan --auto
        nest --conf myconfig --client-id CLIENTID --client-secret SECRET target_hum 35

        # nestcam examples
        nest --conf myconfig --client-id CLIENTID --client-secret SECRET camera-show
        nest --conf myconfig --client-id CLIENTID --client-secret SECRET camera-streaming --enable-camera-streaming

A configuration file must be specified and used for the credentials to communicate with the NEST Thermostat initially.  Once completed and a token is generated, if you're using the default location for the token, the command line option will read from it automatically.


.. code-block:: ini

    [NEST]
    user = joe@user.com
    password = swordfish
    token_cache = ~/.config/nest/token_cache


The ``[NEST]`` section may also be named ``[nest]`` for convenience. Do not use ``[DEFAULT]`` as it cannot be read


History
=======

This module was originally a fork of `nest_thermostat <https://github.com/FiloSottile/nest_thermostat>`_
which was a fork of `pynest <https://github.com/smbaker/pynest>`_
