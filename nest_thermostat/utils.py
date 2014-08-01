#-*- coding:utf-8 -*-

CELSIUS = 'C'
FAHRENHEIT = 'F'


def c_to_f(temp):
    return (temp - 32.0) / 1.8


def f_to_c(temp):
    return temp*1.8 + 32.0
