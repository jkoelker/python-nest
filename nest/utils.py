# -*- coding:utf-8 -*-

import decimal

CELSIUS = 'C'
FAHRENHEIT = 'F'
_THIRTYTWO = decimal.Decimal(32)
_ONEPOINTEIGHT = decimal.Decimal(18) / decimal.Decimal(10)
_TENPOINTSEVENSIXFOUR = decimal.Decimal(10764) / decimal.Decimal(1000)
_ONEPOINTSIXZERONINETHREEFOUR = decimal.Decimal(1609344) / decimal.Decimal(1000000)


def f_to_c(temp):
    temp = decimal.Decimal(temp)
    return float((temp - _THIRTYTWO) / _ONEPOINTEIGHT)


def c_to_f(temp):
    temp = decimal.Decimal(temp)
    return float(temp * _ONEPOINTEIGHT + _THIRTYTWO)


def ft2_to_m2(area):
    area = decimal.Decimal(area)
    return float(area / _TENPOINTSEVENSIXFOUR)


def m2_to_ft2(area):
    area = decimal.Decimal(area)
    return float(area * _TENPOINTSEVENSIXFOUR)


# km/h = mph x 1.6093440057
def kph_to_mph(s):
    s = decimal.Decimal(s)
    return float(s * _ONEPOINTSIXZERONINETHREEFOUR)


#mph = km/h / 1.6093440057
#    = km/h * 0.62137119
def mph_to_kph(s):
    s = decimal.Decimal(s)
    return float(s / _ONEPOINTSIXZERONINETHREEFOUR)
