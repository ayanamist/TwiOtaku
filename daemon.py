#!/usr/bin/env python26
import sys
import signal
import logging
from Queue import Queue
from threading import Thread

from apscheduler.scheduler import Scheduler

# TODO: we must use a Daemon class to wrap all, now codes are messy.
try:
  import ujson as json
except ImportError:
  import json

import db
from cron import cron_start
from stream import stream
from xmpp import XMPPBot
from worker import worker


def sigterm_handler(*_):
  logging.debug('Start to shutdown.')
  sched.shutdown()
  for q in bot.worker_queues.itervalues():
    q.put(None)
  for t in bot.worker_threads.itervalues():
    t.join()
  bot.disconnect(wait=True)
  sys.exit(0)

if __name__ == '__main__':
  signal.signal(signal.SIGTERM, sigterm_handler)

  logging.basicConfig(level=logging.DEBUG, format='%(asctime)-15s %(name)-8s %(levelname)-8s %(message)s', datefmt='%m-%d %H:%M', stream=sys.stdout)
  stderr = logging.StreamHandler()
  stderr.setLevel(logging.ERROR)
  logging.getLogger('').addHandler(stderr)
  logger = logging.getLogger('xmpp')

  db.init()

  worker_queues = dict()
  worker_threads = dict()
  stream_threads = list()

  bot = XMPPBot(worker_threads, worker_queues)

  # start worker threads that receive jobs
  for user in db.get_all_users():
    jid = user['jid']
    q = worker_queues[jid] = Queue()
    w = worker_threads[jid] = Thread(target=worker, args=(bot, q))
    w.setDaemon(True)
    w.start()

  # start xmpp bot
  bot.register_plugin('xep_0030') # Service Discovery
  if bot.connect(('talk.google.com', 5222)):
    bot.process()
  else:
    logger.error('Can not connect to server.')
    sys.exit(1)

  # start streaming threads
  for user in db.get_all_users():
    if user['access_key'] and user['access_secret']:
      t = Thread(target=stream, args=(worker_queues[user['jid']], user))
      stream_threads.append(t)
      t.setDaemon(True)
      t.start()

  # start cron
  cron_initial = Thread(target=cron_start, args=(dict(),))
  cron_initial.setDaemon(True)
  cron_initial.start()
  sched = Scheduler(daemonic=False)
  sched.add_interval_job(cron_start, seconds=15, args=(worker_queues,))
  sched.start()
