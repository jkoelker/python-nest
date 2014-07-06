#!/usr/bin/env python
#-*- coding:utf-8 -*-

from setuptools import setup

setup(name='nest-thermostat',
      version='1.2',
      description='Python API and command line tool for talking to the Nest™ Thermostat',
      author='Scott Baker',
      author_email='smbaker@gmail.com',
      maintainer='Filippo Valsorda',
      maintainer_email='hi@filippo.io',
      url='https://github.com/FiloSottile/nest_thermostat/',
      scripts=['nest.py'],
      packages=['nest_thermostat'],
      install_requires = ['requests']
)
