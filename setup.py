#!/usr/bin/env python
#-*- coding:utf-8 -*-

import io

from setuptools import setup

setup(name='python-nest',
      version='2.2',
      description='Python API and command line tool for talking to the '
                  'Nest™ Thermostat',
      long_description=io.open('README.rst', encoding='UTF-8').read(),
      keywords='nest thermostat',
      author='Jason Kölker',
      author_email='jason@koelker.net',
      url='https://github.com/jkoelker/python-nest/',
      packages=['nest'],
      install_requires=['requests'],
      entry_points={
          'console_scripts': ['nest=nest.command_line:main'],
      }
      )
