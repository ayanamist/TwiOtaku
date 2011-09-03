#!/usr/bin/env python26
import sys
import os
import signal
import logging

from apscheduler.scheduler import Scheduler

try:
  import ujson as json
except ImportError:
  import json

import db
import cron
from xmpp import XMPPBot


ENVIRONMENT_JSON_PATH = '/home/dotcloud/environment.json'
YAML_PATH = os.path.dirname(__file__) + os.sep + 'dotcloud.yml'

def sigterm_handler(*_):
  sched.shutdown()
  for q in bot.tbd_queues.itervalues():
    q.put((None, None, None))
  for t in bot.tbd_threads.itervalues():
    t.join()
  bot.disconnect(wait=True)
  sys.exit(0)

if __name__ == '__main__':
  signal.signal(signal.SIGTERM, sigterm_handler)

  logging.basicConfig(level=logging.DEBUG, format='%(asctime)-15s %(name)-8s %(levelname)-8s %(message)s', datefmt='%m-%d %H:%M', stream=sys.stdout)
  stderr = logging.StreamHandler()
  stderr.setLevel(logging.ERROR)
  logging.getLogger('').addHandler(stderr)
  xmpp_logger = logging.getLogger('xmpp')
  config = dict()

  if os.path.exists(ENVIRONMENT_JSON_PATH):
    f = open(ENVIRONMENT_JSON_PATH, 'r')
    config = json.load(f)
    f.close()
  elif os.path.exists(YAML_PATH):
    import yaml

    try:
      from yaml import CLoader as Loader
    except ImportError:
      from yaml import Loader

    f = open(YAML_PATH, 'r')
    config = yaml.load(f.read(), Loader=Loader)['xmpp']['environment']
    f.close()
  else:
    logging.error('Can not find appropriate configuration file.')
    sys.exit(1)

  config['ADMIN_USERS'] = [x.strip() for x in config['ADMIN_USERS'].split(',')]

  db.init()

  bot = XMPPBot(config)
  bot.register_plugin('xep_0030') # Service Discovery
  if bot.connect(('talk.google.com', 5222)):
    bot.process()
  else:
    xmpp_logger.error('Can not connect to server.')
    sys.exit(1)

  sched = Scheduler()
  sched.add_interval_job(cron.cron_start, minutes=1, args=(bot,))
  sched.start()

  while True:
    pass