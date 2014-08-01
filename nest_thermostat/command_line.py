#! /usr/bin/python
#-*- coding:utf-8 -*-

'''
nest.py -- a python interface to the Nest Thermostats
'''

import argparse

from . import nest
from . import utils


def create_parser():
    description = 'Command line interface to Nest™ Thermostats'
    parser = argparse.ArgumentParser(description=description)

    parser.add_argument('-u', '--user', dest='user', required=True,
                        help='username for nest.com', metavar='USER')

    parser.add_argument('-p', '--password', dest='password', required=True,
                        help='password for nest.com', metavar='PASSWORD')

    parser.add_argument('-c', '--celsius', dest='celsius', action='store_true',
                        default=False,
                        help='use celsius instead of farenheit')

    parser.add_argument('-s', '--serial', dest='serial',
                        help='optional, specify serial number of nest '
                             'thermostat to talk to')

    parser.add_argument('-i', '--index', dest='index', default=0, type=int,
                        help='optional, specify index number of nest to '
                             'talk to')

    subparsers = parser.add_subparsers(dest='command',
                                       help='command help')
    temp = subparsers.add_parser('temp', help='show/set temperature')
    temp.add_argument('temperature', nargs='*',
                      help='target tempterature to set device to')

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
    subparsers.add_parser('show', help='show everything')

    return parser


def main():
    parser = create_parser()
    args = parser.parse_args()

    if args.celsius:
        display_temp = lambda x: x
        convert_temp = lambda x: x

    else:
        display_temp = utils.c_to_f
        convert_temp = utils.f_to_c

    cmd = args.command

    with nest.Nest(args.user, args.password) as napi:
        if cmd == 'away':
            structure = napi.structures[0]

            if args.away:
                structure.away = True

            elif args.home:
                structure.away = False

            print structure.away
            return

        if args.serial:
            device = nest.Device(args.serial, napi)

        else:
            device = napi.devices[args.index]

        if cmd == 'temp':
            if args.temperature:
                if len(args.temperature) > 1:
                    if args.mode != 'range':
                        device.mode = 'range'

                    device.temperature = (args.temperature[0],
                                          args.temperature[1])

                else:
                    temp = convert_temp(args.temperature)
                    device.temperature = temp

            print '%0.1f' % display_temp(device.temperature)

        elif cmd == 'fan':
            if args.auto:
                device.fan = False

            elif args.on:
                device.fan = True

            print device.fan

        elif cmd == 'mode':
            if args.cool:
                device.mode('cool')

            elif args.heat:
                device.mode('heat')

            elif args.range:
                device.mode('range')

            elif args.off:
                device.mode('off')

            print device.mode

        elif cmd == 'humid':
            print device.humidity

        elif cmd == 'target':
            target = device.target

            if isinstance(target, tuple):
                print 'Lower: %0.1f' % display_temp(target[0])
                print 'Upper: %0.1f' % display_temp(target[1])

            else:
                print '%0.1f' % display_temp(target)

        elif cmd == 'show':
            data = device._shared.copy()
            data.update(device._device)

            for k in sorted(data.keys()):
                print k + '.'*(32-len(k)) + ':', data[k]


if __name__ == '__main__':
    main()
