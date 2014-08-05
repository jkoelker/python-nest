#nest_thermostat

**a Python interface for the Nest Thermostat**
 
*fork of pynest by Scott M Baker, smbaker@gmail.com, http://www.smbaker.com/*

##Installation
`[sudo] pip install nest-thermostat`

##Usage

### Module

You can import the module as `nest_thermostat`.

```python
import nest_thermostat as nest

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
        device.temp = 73
```

For "advanced" usage such as token caching, use the source, luke!

### Command line
```
usage: nest [-h] [--conf FILE] [--token-cache TOKEN_CACHE_FILE] [-t TOKEN]
            [-u USER] [-p PASSWORD] [-c] [-s SERIAL] [-i INDEX]
            {temp,fan,mode,away,target,humid,show} ...

Command line interface to Nest™ Thermostats

positional arguments:
  {temp,fan,mode,away,target,humid,show}
                        command help
    temp                show/set temperature
    fan                 set fan "on" or "auto"
    mode                show/set current mode
    away                show/set current away status
    target              show current temp target
    humid               show current humidity
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
```

A configuration file can also be specified to prevent username/password repitition.

```config
[DEFAULT]
user = joe@user.com
password = swordfish
token_cache = ~/.config/nest/cache
```

The `[DEFAULT]` section may also be named `[nest]` for convience.


---

*Chris Burris's Siri Nest Proxy was very helpful to learn the Nest's authentication and some bits of the protocol.*
