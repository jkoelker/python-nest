#!/usr/bin/env python
#-*- coding:utf-8 -*-

import io

from setuptools import setup


# NOTE(jkoelker) Subjective guidelines for Major.Minor.Micro ;)
#                Bumping Major means an API contract change.
#                Bumping Minor means API bugfix or new functionality.
#                Bumping Micro means CLI change of any kind unless it is
#                    significant enough to warrant a minor/major bump.
version = '2.7.0'


setup(name='python-nest',
      version=version,
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
