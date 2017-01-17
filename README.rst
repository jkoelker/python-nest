=========================================================
Python API and command line tool for the Nest™ Thermostat
=========================================================

.. image:: https://travis-ci.org/jkoelker/python-nest.svg?branch=master
    :target: https://travis-ci.org/jkoelker/python-nest


Installation
============

.. code-block:: bash

    [sudo] pip install python-nest


*NOTE* The ``3.x`` version uses the Nest official api. As such some functionality
was removed as it is not available. To keep the old verision make sure to set
your requirements to ``python-nest<3.0``.

Nest Developer Account
=======================


You will a Nest developer account, and a Product on the Nest developer portal to use this module:

1. Visit `Nest Developers <https://developers.nest.com/>`_, and sign in. Create an account if you don't have one already.

2. Fill in account details:

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

You can import the module as `nest`.

.. code-block:: python

    import nest

    client_id = 'XXXXXXXXXXXXXXX'
    client_secret = 'XXXXXXXXXXXXXXX'
    access_token_cache_file = 'nest.json'

    nest = nest.Nest(client_id=client_id, client_secret=client_secret, access_token_cache_file=access_token_cache_file)

    if nest.authorization_required is None:
        print('Go to ' + nest.authorize_url + ' to authorize, then enter PIN below')
        pin = input("PIN: ")
        nest.request_token(pin)

    for structure in napi.structures:
        print 'Structure %s' % structure.name
        print '    Away: %s' % structure.away
        print '    Devices:'

        for device in structure.devices:
            print '        Device: %s' % device.name
            print '            Temp: %0.1f' % device.temperature

    # Access advanced structure properties:
    for structure in napi.structures:
        print 'Structure   : %s' % structure.name
        print ' Postal Code                    : %s' % structure.postal_code
        print ' Country                        : %s' % structure.country_code
        print ' dr_reminder_enabled            : %s' % structure.dr_reminder_enabled
        print ' emergency_contact_description  : %s' % structure.emergency_contact_description
        print ' emergency_contact_type         : %s' % structure.emergency_contact_type
        print ' emergency_contact_phone        : %s' % structure.emergency_contact_phone
        print ' enhanced_auto_away_enabled     : %s' % structure.enhanced_auto_away_enabled
        print ' eta_preconditioning_active     : %s' % structure.eta_preconditioning_active
        print ' house_type                     : %s' % structure.house_type
        print ' hvac_safety_shutoff_enabled    : %s' % structure.hvac_safety_shutoff_enabled
        print ' num_thermostats                : %s' % structure.num_thermostats
        print ' measurement_scale              : %s' % structure.measurement_scale
        print ' renovation_date                : %s' % structure.renovation_date
        print ' structure_area                 : %s' % structure.structure_area

    # Access advanced device properties:
        for device in structure.devices:
            print '        Device: %s' % device.name
            print '        Where: %s' % device.where
            print '            Mode     : %s' % device.mode
            print '            Fan      : %s' % device.fan
            print '            Temp     : %0.1fC' % device.temperature
            print '            Humidity : %0.1f%%' % device.humidity
            print '            Target   : %0.1fC' % device.target
            print '            Away Heat: %0.1fC' % device.away_temperature[0]
            print '            Away Cool: %0.1fC' % device.away_temperature[1]
            print '            Eco      : %s' % device.eco

            print '            hvac_ac_state         : %s' % device.hvac_ac_state
            print '            hvac_cool_x2_state    : %s' % device.hvac_cool_x2_state
            print '            hvac_heater_state     : %s' % device.hvac_heater_state
            print '            hvac_aux_heater_state : %s' % device.hvac_aux_heater_state
            print '            hvac_heat_x2_state    : %s' % device.hvac_heat_x2_state
            print '            hvac_heat_x3_state    : %s' % device.hvac_heat_x3_state
            print '            hvac_alt_heat_state   : %s' % device.hvac_alt_heat_state
            print '            hvac_alt_heat_x2_state: %s' % device.hvac_alt_heat_x2_state
            print '            hvac_emer_heat_state  : %s' % device.hvac_emer_heat_state

            print '            online                : %s' % device.online
            print '            last_ip               : %s' % device.last_ip
            print '            local_ip              : %s' % device.local_ip
            print '            last_connection       : %s' % device.last_connection

            print '            error_code            : %s' % device.error_code
            print '            battery_level         : %s' % device.battery_level

    # The Nest object can also be used as a context manager
    with nest.Nest(client_id=client_id, client_secret=client_secret, access_token_cache_file=access_token_cache_file) as napi:
        for device in napi.devices:
            device.temperature = 23

    # Nest product's can be updated to include other permissions. Before you
    # can access with the API, a user has to authorize again. To handle this
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
    #       By passing `local_time=True` to the `Nest` object datetime objects
    #       will be converted to the timezone reported by nest. If the `pytz`
    #       module is installed those timezone objects are used, else one is
    #       synthesized from the nest data
    napi = nest.Nest(username, password, local_time=True)
    print napi.structures[0].weather.current.datetime.tzinfo




FIXME In the API, temperatures are in  all temperature values are in degrees celsius. Helper functions
for conversion are in the `utils` module:

.. code-block:: python

    from nest import utils as nest_utils
    temp = 23.5
    fahrenheit = nest_utils.c_to_f(temp)
    temp == nest_utils.f_to_c(fahrenheit)


The utils function use `decimal.Decimal` to ensure precision.


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
        # If your nest is not in range mode
        nest --user joe@user.com --password swordfish temp 73
        # If your nest is in range mode
        nest --user joe@user.com --password swordfish temp 66 73

        nest --user joe@user.com --password swordfish fan --auto
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
