# -*- coding:utf-8 -*-

import decimal

CELSIUS = 'C'
FAHRENHEIT = 'F'
_THIRTYTWO = decimal.Decimal(32)
_ONEPOINTEIGHT = decimal.Decimal(18) / decimal.Decimal(10)


def f_to_c(temp):
    temp = decimal.Decimal(temp)
    return float((temp - _THIRTYTWO) / _ONEPOINTEIGHT)


def c_to_f(temp):
    temp = decimal.Decimal(temp)
    return float(temp * _ONEPOINTEIGHT + _THIRTYTWO)
