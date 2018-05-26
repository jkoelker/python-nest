#! /usr/bin/python
# -*- coding:utf-8 -*-

'''
nest.py -- a python interface to the Nest Thermostats
'''

from __future__ import print_function

import argparse
import os
import sys
import errno

from . import nest
from . import utils
from . import helpers

# use six for python2/python3 compatibility
from six.moves import input


def parse_args():
    # Get Executable name
    prog = os.path.basename(sys.argv[0])

    config_file = os.path.sep.join(('~', '.config', 'nest', 'config'))
    token_cache = os.path.sep.join(('~', '.config', 'nest', 'token_cache'))

    conf_parser = argparse.ArgumentParser(prog=prog, add_help=False)

    conf_parser.add_argument('--conf', default=config_file,
                             help='config file (default %s)' % config_file,
                             metavar='FILE')

    args, remaining_argv = conf_parser.parse_known_args()

    defaults = helpers.get_config(config_path=args.conf)

    description = 'Command line interface to Nest™ Thermostats'
    parser = argparse.ArgumentParser(description=description,
                                     parents=[conf_parser])

    parser.add_argument('--token-cache', dest='token_cache',
                        default=token_cache,
                        help='auth access token cache file',
                        metavar='TOKEN_CACHE_FILE')

    parser.add_argument('-t', '--token', dest='token',
                        help='auth access token', metavar='TOKEN')

    parser.add_argument('--client-id', dest='client_id',
                        help='product id on developer.nest.com', metavar='ID')

    parser.add_argument('--client-secret', dest='client_secret',
                        help='product secret for nest.com', metavar='SECRET')

    parser.add_argument('-k', '--keep-alive', dest='keep_alive',
                        action='store_true',
                        help='keep showing update received from stream API '
                             'in show and camera-show commands')

    parser.add_argument('-c', '--celsius', dest='celsius', action='store_true',
                        help='use celsius instead of farenheit')

    parser.add_argument('-s', '--serial', dest='serial',
                        help='optional, specify serial number of nest '
                             'thermostat to talk to')

    parser.add_argument('-S', '--structure', dest='structure',
                        help='optional, specify structure name to'
                             'scope device actions')

    parser.add_argument('-i', '--index', dest='index', default=0, type=int,
                        help='optional, specify index number of nest to '
                             'talk to')

    subparsers = parser.add_subparsers(dest='command',
                                       help='command help')
    temp = subparsers.add_parser('temp', help='show/set temperature')

    temp.add_argument('temperature', nargs='*', type=float,
                      help='target temperature to set device to')

    fan = subparsers.add_parser('fan', help='set fan "on" or "auto"')
    fan_group = fan.add_mutually_exclusive_group()
    fan_group.add_argument('--auto', action='store_true', default=False,
                           help='set fan to auto')
    fan_group.add_argument('--on', action='store_true', default=False,
                           help='set fan to on')

    mode = subparsers.add_parser('mode', help='show/set current mode')
    mode_group = mode.add_mutually_exclusive_group()
    mode_group.add_argument('--cool', action='store_true', default=False,
                            help='set mode to cool')
    mode_group.add_argument('--heat', action='store_true', default=False,
                            help='set mode to heat')
    mode_group.add_argument('--eco', action='store_true', default=False,
                            help='set mode to eco')
    mode_group.add_argument('--range', action='store_true', default=False,
                            help='set mode to range')
    mode_group.add_argument('--off', action='store_true', default=False,
                            help='set mode to off')

    away = subparsers.add_parser('away', help='show/set current away status')
    away_group = away.add_mutually_exclusive_group()
    away_group.add_argument('--away', action='store_true', default=False,
                            help='set away status to "away"')
    away_group.add_argument('--home', action='store_true', default=False,
                            help='set away status to "home"')

    subparsers.add_parser('target', help='show current temp target')
    subparsers.add_parser('humid', help='show current humidity')

    target_hum = subparsers.add_parser('target_hum',
                                       help='show/set target humidty')
    target_hum.add_argument('humidity', nargs='*',
                            help='specify target humidity value or auto '
                                 'to auto-select a humidity based on outside '
                                 'temp')

    subparsers.add_parser('show', help='show everything')

    # Camera parsers
    subparsers.add_parser('camera-show',
                          help='show everything (for cameras)')
    cam_streaming = subparsers.add_parser('camera-streaming',
                                          help='show/set camera streaming')
    camera_streaming_group = cam_streaming.add_mutually_exclusive_group()
    camera_streaming_group.add_argument('--enable-camera-streaming',
                                        action='store_true', default=False,
                                        help='Enable camera streaming')
    camera_streaming_group.add_argument('--disable-camera-streaming',
                                        action='store_true', default=False,
                                        help='Disable camera streaming')

    parser.set_defaults(**defaults)
    return parser.parse_args()


def get_structure(napi, args):
    if args.structure:
        struct = [s for s in napi.structures if s.name == args.structure]
        if struct:
            return struct[0]
    return napi.structures[0]


def get_device(napi, args, structure):
    if args.serial:
        return nest.Camera(args.serial, napi)
    else:
        return structure.cameras[args.index]


def handle_camera_show(device, print_prompt, print_meta_data=True):
    if print_meta_data:
        print('Device                : %s' % device.name)
        # print('Model               : %s' % device.model) # Doesn't work
        print('Serial                : %s' % device.serial)
        print('Where                 : %s' % device.where)
        print('Where ID              : %s' % device.where_id)
        print('Video History Enabled : %s' % device.is_video_history_enabled)
        print('Audio Enabled         : %s' % device.is_audio_enabled)
        print('Public Share Enabled  : %s' % device.is_public_share_enabled)
        print('Snapshot URL          : %s' % device.snapshot_url)

    print('Away                  : %s' % device.structure.away)
    print('Sound Detected        : %s' % device.sound_detected)
    print('Motion Detected       : %s' % device.motion_detected)
    print('Person Detected       : %s' % device.person_detected)
    print('Streaming             : %s' % device.is_streaming)
    if print_prompt:
        print('Press Ctrl+C to EXIT')


def handle_camera_streaming(device, args):
    if args.disable_camera_streaming:
        device.is_streaming = False
    elif args.enable_camera_streaming:
        device.is_streaming = True

    print('Streaming : %s' % device.is_streaming)


def handle_camera_commands(napi, args):
    structure = get_structure(napi, args)
    device = get_device(napi, args, structure)
    if args.command == "camera-show":
        handle_camera_show(device, args.keep_alive)
        if args.keep_alive:
            try:
                napi.update_event.clear()
                while napi.update_event.wait():
                    napi.update_event.clear()
                    handle_camera_show(device, True, False)
            except KeyboardInterrupt:
                return
    elif args.command == "camera-streaming":
        handle_camera_streaming(device, args)


def handle_show_commands(napi, device, display_temp, print_prompt,
                         print_meta_data=True):
    if print_meta_data:
        # TODO should pad key? old code put : out 35
        print('Device: %s' % device.name)
        print('Where: %s' % device.where)
        print('Can Heat              : %s' % device.can_heat)
        print('Can Cool              : %s' % device.can_cool)
        print('Has Humidifier        : %s' % device.has_humidifier)
        print('Has Dehumidifier      : %s' % device.has_humidifier)
        print('Has Fan               : %s' % device.has_fan)
        print('Has Hot Water Control : %s' % device.has_hot_water_control)

    print('Away                  : %s' % device.structure.away)
    print('Mode                  : %s' % device.mode)
    print('State                 : %s' % device.hvac_state)
    if device.has_fan:
        print('Fan                   : %s' % device.fan)
        print('Fan Timer             : %s' % device.fan_timer)
    if device.has_hot_water_control:
        print('Hot Water Temp        : %s' % device.fan)
    print('Temp                  : %0.1f%s' % (device.temperature,
          device.temperature_scale))
    helpers.print_if('Humidity              : %0.1f%%', device.humidity)
    if isinstance(device.target, tuple):
        print('Target                 : %0.1f-%0.1f%s' % (
            display_temp(device.target[0]),
            display_temp(device.target[1]),
            device.temperature_scale))
    else:
        print('Target                : %0.1f%s' %
              (display_temp(device.target), device.temperature_scale))

    print('Away Heat             : %0.1f%s' %
          (display_temp(device.eco_temperature[0]), device.temperature_scale))
    print('Away Cool             : %0.1f%s' %
          (display_temp(device.eco_temperature[1]), device.temperature_scale))

    print('Has Leaf              : %s' % device.has_leaf)

    if print_prompt:
        print('Press Ctrl+C to EXIT')


def main():
    args = parse_args()

    def _identity(x):
        return x

    display_temp = _identity

    # Expand the path to check for existence
    config_dir = os.path.expanduser("~/.config/nest")

    # Check if .config directory exists
    if not os.path.exists(config_dir):

        # If it does not, create it
        try:
            os.makedirs(config_dir)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise

    # This is the command(s) passed to the command line utility
    cmd = args.command

    token_cache = os.path.expanduser(args.token_cache)

    if not os.path.exists(token_cache):
        if args.client_id is None or args.client_secret is None:
            print("Missing client and secret. If using a configuration file,"
                  " ensure that it is formatted properly, with a section "
                  "titled as per the documentation-otherwise, call with "
                  "--client-id and --client-secret.")
            return

    with nest.Nest(client_id=args.client_id, client_secret=args.client_secret,
                   access_token=args.token,
                   access_token_cache_file=token_cache) as napi:

        if napi.authorization_required:
            print('Go to ' + napi.authorize_url +
                  ' to authorize, then enter PIN below')
            pin = input("PIN: ")
            napi.request_token(pin)

        if cmd.startswith("camera"):
            return handle_camera_commands(napi, args)
        elif cmd == 'away':
            structure = None

            if args.structure:
                struct = [s for s in napi.structures
                          if s.name == args.structure]
                if struct:
                    structure = struct[0]

            else:
                if args.serial:
                    serial = args.serial
                else:
                    serial = napi.thermostats[args.index]._serial

                struct = [s for s in napi.structures for d in s.thermostats
                          if d._serial == serial]
                if struct:
                    structure = struct[0]

            if not structure:
                structure = napi.structures[0]

            if args.away:
                structure.away = True

            elif args.home:
                structure.away = False

            print(structure.away)
            return

        if args.serial:
            device = nest.Thermostat(args.serial, napi)

        elif args.structure:
            struct = [s for s in napi.structures if s.name == args.structure]
            if struct:
                device = struct[0].thermostats[args.index]

            else:
                device = napi.structures[0].thermostats[args.index]

        else:
            device = napi.thermostats[args.index]

        if args.celsius and device.temperature_scale is 'F':
            display_temp = utils.f_to_c
        elif not args.celsius and device.temperature_scale is 'C':
            display_temp = utils.c_to_f

        if cmd == 'temp':
            if args.temperature:
                if len(args.temperature) > 1:
                    if device.mode != 'range':
                        device.mode = 'range'

                    device.temperature = args.temperature

                else:
                    device.temperature = args.temperature[0]

            print('%0.1f' % display_temp(device.temperature))

        elif cmd == 'fan':
            if args.auto:
                device.fan = False

            elif args.on:
                device.fan = True

            print(device.fan)

        elif cmd == 'mode':
            if args.cool:
                device.mode = 'cool'

            elif args.heat:
                device.mode = 'heat'

            elif args.eco:
                device.mode = 'eco'

            elif args.range:
                device.mode = 'range'

            elif args.off:
                device.mode = 'off'

            print(device.mode)

        elif cmd == 'humid':
            print(device.humidity)

        elif cmd == 'target':
            target = device.target

            if isinstance(target, tuple):
                print('Lower: %0.1f' % display_temp(target[0]))
                print('Upper: %0.1f' % display_temp(target[1]))

            else:
                print('%0.1f' % display_temp(target))

        elif cmd == 'show':
            handle_show_commands(napi, device, display_temp, args.keep_alive)
            if args.keep_alive:
                try:
                    napi.update_event.clear()
                    while napi.update_event.wait():
                        napi.update_event.clear()
                        handle_show_commands(napi, device, display_temp,
                                             True, False)
                except KeyboardInterrupt:
                    return


if __name__ == '__main__':
    main()
