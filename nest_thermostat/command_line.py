#! /usr/bin/python
#-*- coding:utf-8 -*-

'''
nest.py -- a python interface to the Nest Thermostats
'''

import argparse
import nest_thermostat


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
    temp.add_argument('temperature', nargs='?',
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

    subparsers.add_parser('humid', help='show current humidity')
    subparsers.add_parser('target', help='show current temp target')
    subparsers.add_parser('show', help='show everything')

    return parser


def main():
    parser = create_parser()
    args = parser.parse_args()

    if args.celsius:
        units = nest_thermostat.CELSIUS
    else:
        units = nest_thermostat.FAHRENHEIT

    cmd = args.command

    with nest_thermostat.Nest(args.user, args.password, args.serial,
                              args.index, units=units) as nest:
        nest.get_status()

        if cmd == 'temp':
            if args.temperature:
                nest.set_temperature(float(args.temperature))

            nest.show_curtemp()

        elif cmd == 'fan':
            if args.auto:
                nest.set_fan('auto')

            elif args.on:
                nest.set_fan('on')

            # TODO(jkoelker) Fan state?

        elif cmd == 'mode':
            if args.cool:
                nest.set_mode('cool')

            elif args.heat:
                nest.set_mode('heat')

            elif args.range:
                nest.set_mode('range')

            elif args.off:
                nest.set_mode('off')

            nest.show_curmode()

        elif cmd == 'away':
            # TODO(jkoelker) after refactor of nest class
            pass

        elif cmd == 'humid':
            print nest.status['device'][nest.serial]['current_humidity']

        elif cmd == 'target':
            nest.show_target()

        elif cmd == 'show':
            nest.show_status()

if __name__ == '__main__':
    main()
