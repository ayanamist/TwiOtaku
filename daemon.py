#!/usr/bin/env python26
import sys
import os
import signal
import logging

try:
  import ujson as json
except ImportError:
  import json

import runtime
import db
from xmpp import XMPPBot


ENVIRONMENT_JSON_PATH = '/home/dotcloud/environment.json'

YAML_PATH = os.path.dirname(__file__) + os.sep + 'dotcloud.yml'

def sigterm_handler(signum, frame):
  bot.disconnect(wait=True)
  sys.exit(0)

if __name__ == '__main__':
  signal.signal(signal.SIGTERM, sigterm_handler)

  logging.basicConfig(level=logging.DEBUG, format='%(asctime)-15s %(name)-8s %(levelname)-8s %(message)s', datefmt='%m-%d %H:%M', stream=sys.stdout)
  stderr = logging.StreamHandler()
  stderr.setLevel(logging.ERROR)
  logging.getLogger('').addHandler(stderr)
  xmpp_logger = logging.getLogger('xmpp')

  if os.path.exists(ENVIRONMENT_JSON_PATH):
    f = open(ENVIRONMENT_JSON_PATH, 'r')
    runtime.CONFIG = json.load(f)
    f.close()
  elif os.path.exists(YAML_PATH):
    import yaml

    try:
      from yaml import CLoader as Loader
    except ImportError:
      from yaml import Loader

    f = open(YAML_PATH, 'r')
    runtime.CONFIG = yaml.load(f.read(), Loader=Loader)['xmpp']['environment']
    f.close()
  else:
    logging.error('Can not find appropriate configuration file.')
    sys.exit(1)

  db.init()

  bot = XMPPBot(runtime.CONFIG['XMPP_USERNAME'], runtime.CONFIG['XMPP_PASSWORD'])
  bot.register_plugin('xep_0030') # Service Discovery
  if bot.connect(('talk.google.com', 5222)):
    bot.process(threaded=False)
  else:
    xmpp_logger.error('Can not connect to server.')
    sys.exit(1)
