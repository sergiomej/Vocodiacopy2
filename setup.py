#!/usr/bin/.env python
from setuptools import find_packages, setup

setup(name='vocodiaSwitchServices',
      version='1.0.0',
      description='Vocodia Switch Services',
      author='Vocodia',
      author_email='daniel@thedarkside.com.co',
      url='https://www.python.org/sigs/distutils-sig/',
      packages=find_packages(),
      install_requires=[
          "Flask>=2.3.2",
          "azure-eventgrid==4.11.0",
          "azure-communication-callautomation==1.2.0",
          "websockets==12.0",
          "azure-core==1.30.2",
          "pymemcache==4.0.0",
          "pymysql==1.1.1",
          "pytest==8.3.1",
          "azure-cosmos==4.7.0"
      ],
      scripts=[
          'bin/switch.sh',
      ]
      )
