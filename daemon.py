#!/usr/bin/env python
import sys
import platform
import signal
import logging
from Queue import Queue
from threading import Thread

import sleekxmpp
from apscheduler.scheduler import Scheduler

try:
  import ujson as json
except ImportError:
  import json

import db
from xmpp import XMPPMessageHandler
from cron import cron_start
from stream import StreamThread
from worker import worker
from config import XMPP_USERNAME, XMPP_PASSWORD

# TODO: implement i18n support
class XMPPBot(sleekxmpp.ClientXMPP):
  def __init__(self):
    self.worker_queues = dict()
    self.worker_threads = dict()

    self.stream_threads = dict()

    self.sched = Scheduler()
    self.logger = logging.getLogger('xmpp')
    self.online_clients = dict() # this save online buddies no matter it's our users or not.
    sleekxmpp.ClientXMPP.__init__(self, XMPP_USERNAME, XMPP_PASSWORD)
    self.auto_authorize = True
    self.auto_subscribe = True
    self.add_event_handler('session_start', self.on_start)
    self.add_event_handler('message', self.on_message)
    self.add_event_handler('changed_status', self.on_changed_status)
    self.register_plugin('xep_0030') # Service Discovery

  def on_start(self, _):
    self.get_roster()
    self.start_workers()
    self.start_streams()
    self.start_cron()
    self.send_presence()

  def on_message(self, msg):
    if msg['type'] == 'chat':
      XMPPMessageHandler(self).process(msg)
    elif msg['type'] == 'error':
      if msg['error'][
         'type'] == 'cancel': # If we send lots of stanzas at the same time, some of them will be returned as type "error", we must resend them.
        msg.reply(msg['body']).send()
      else:
        self.logger.info('%s -> %s: %s' % (msg['from'], msg['to'], str(msg['error'])))

  def on_changed_status(self, presence):
    bare_jid = self.getjidbare(str(presence['from'])).lower()
    n = self.online_clients.get(bare_jid, 0)
    if presence['type'] == 'available':
      self.online_clients[bare_jid] = n + 1
    else:
      if n > 1:
        self.online_clients[bare_jid] = n - 1
      elif n == 1:
        del self.online_clients[bare_jid]

  def add_online_user(self, bare_jid):
    if bare_jid in self.online_clients:
      self.start_worker(bare_jid)
      self.start_stream(bare_jid)

  def sigterm_handler(self, *_):
    logging.debug('Start to shutdown.')
    self.sched.shutdown()
    for q in self.worker_queues.itervalues():
      q.put(None)
    for t in self.worker_threads.itervalues():
      t.join()
    self.disconnect(wait=True)
    sys.exit(0)

  def start_worker(self, bare_jid):
    if bare_jid not in self.worker_queues:
      q = self.worker_queues[bare_jid] = Queue()
      w = self.worker_threads[bare_jid] = Thread(target=worker, args=(self, q))
      w.setDaemon(True)
      w.start()

  def start_workers(self):
    for user in db.get_all_users():
      self.start_worker(user['jid'])

  def start(self, *args, **kwargs):
    logger = logging.getLogger('xmpp')
    if self.connect(('talk.google.com', 5222)):
      self.process(*args, **kwargs)
    else:
      logger.error('Can not connect to server.')

  def start_cron(self):
    cron_initial = Thread(target=cron_start, args=(dict(),))
    cron_initial.setDaemon(True)
    cron_initial.start()
    self.sched.add_interval_job(cron_start, seconds=15, args=(self.worker_queues,))
    self.sched.start()

  def start_stream(self, bare_jid):
    if bare_jid not in self.stream_threads:
      t = StreamThread(self, bare_jid)
      self.stream_threads[bare_jid] = t
      t.setDaemon(True)
      t.start()

  def start_streams(self):
    for user in db.get_all_users():
      if user['access_key'] and user['access_secret']:
        self.start_stream(user['jid'])

if __name__ == '__main__':
  major, minor, _ = platform.python_version_tuple()
  if major != '2' or minor < '6':
    print 'TwiOtaku needs Python 2.6 or later. Python 3.X is not supported yet.'
    exit(1)

  logging.basicConfig(level=logging.DEBUG, format='%(asctime)-15s %(name)-8s %(levelname)-8s %(message)s',
    datefmt='%m-%d %H:%M:%S', stream=sys.stdout)
  stderr = logging.StreamHandler()
  stderr.setLevel(logging.ERROR)
  logging.getLogger('').addHandler(stderr)

  db.init()

  bot = XMPPBot()
  signal.signal(signal.SIGTERM, bot.sigterm_handler)
  bot.start(block=True)