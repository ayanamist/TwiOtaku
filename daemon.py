#!/usr/bin/env python26
import sys
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


def sigterm_handler(*_):
  sched.shutdown()
  for q in bot.tbd_queues.itervalues():
    q.put(None)
  for t in bot.tbd_threads.itervalues():
    t.join()
  bot.disconnect(wait=True)
  db.end_transaction()
  sys.exit(0)

if __name__ == '__main__':
  signal.signal(signal.SIGTERM, sigterm_handler)

  logging.basicConfig(level=logging.DEBUG, format='%(asctime)-15s %(name)-8s %(levelname)-8s %(message)s', datefmt='%m-%d %H:%M', stream=sys.stdout)
  stderr = logging.StreamHandler()
  stderr.setLevel(logging.ERROR)
  logging.getLogger('').addHandler(stderr)
  logger = logging.getLogger('xmpp')

  db.init()

  bot = XMPPBot()
  bot.register_plugin('xep_0030') # Service Discovery
  if bot.connect(('talk.google.com', 5222)):
    bot.process()
  else:
    logger.error('Can not connect to server.')
    sys.exit(1)

  sched = Scheduler()
  sched.add_interval_job(cron.cron_start, minutes=1, args=(bot,))
  sched.start()

  while True:
    pass