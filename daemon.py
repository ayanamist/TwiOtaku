#!/usr/bin/env python
import sys
import platform
import signal
import logging
from Queue import Queue

# we must write these code here because sleekxmpp will set its own logger during import!
from lib import logger

logging.basicConfig(level=logging.DEBUG, format=logger.LOGGING_FORMAT, datefmt=logger.LOGGING_DATEFMT,
  stream=sys.stdout)
logging.setLoggerClass(logger.ErrorLogger)

import sleekxmpp

try:
  import ujson as json
except ImportError:
  import json

import db
from config import XMPP_USERNAME, XMPP_PASSWORD
from core.xmpp import XMPPMessageHandler
from core.cron import CronStart, CronMisc
from core.stream import StreamThread
from core.worker import Worker

logger = logging.getLogger('xmpp')

# TODO: implement i18n support
class XMPPBot(sleekxmpp.ClientXMPP):
  def __init__(self):
    self.worker_queues = dict()
    self.worker_threads = dict()

    self.stream_threads = dict()

    self.online_clients = dict() # this save online buddies no matter it's our users or not.
    sleekxmpp.ClientXMPP.__init__(self, XMPP_USERNAME, XMPP_PASSWORD)
    self.auto_authorize = True
    self.auto_subscribe = True
    self.first_run = True
    self.add_event_handler('session_start', self.on_start)
    self.add_event_handler('message', self.on_message)
    self.add_event_handler('changed_status', self.on_changed_status)
    self.register_plugin('xep_0030') # Service Discovery

  def on_start(self, _):
    self.get_roster()
    if self.first_run:
      self.start_workers()
      self.start_streams()
      self.start_cron()
      self.first_run = False
    self.send_presence()

  def on_message(self, msg):
    if msg['type'] == 'chat':
      XMPPMessageHandler(self).process(msg)
    elif msg['type'] == 'error':
      # If we send lots of stanzas at the same time, some of them will be returned as type "error", we must resend them.
      if msg['error']['type'] == 'cancel':
        msg.reply(msg['body']).send()
      else:
        logger.info('%s -> %s: %s' % (msg['from'], msg['to'], str(msg['error'])))

  def on_changed_status(self, presence):
    bare_jid = self.getjidbare(str(presence['from'])).lower()
    n = self.online_clients.get(bare_jid, 0)
    if presence['type'] in presence.types:
      if presence['type'] == 'available':
        self.online_clients[bare_jid] = n + 1
      else:
        if n > 1:
          self.online_clients[bare_jid] = n - 1
        elif n == 1:
          del self.online_clients[bare_jid]

  def send_message(self, mto, mbody, msubject=None, mtype=None, mhtml=None, mfrom=None, mnick=None):
    if mtype is None:
      mtype = 'chat' # we must set this so messages can be saved into gmail.
    return super(XMPPBot, self).send_message(mto, mbody, msubject, mtype, mhtml, mfrom, mnick)

  def add_online_user(self, bare_jid):
    if bare_jid in self.online_clients:
      self.start_worker(bare_jid)
      self.start_stream(bare_jid)

  def start(self, *args, **kwargs):
    if self.connect(('talk.google.com', 5222)):
      self.process(*args, **kwargs)
    else:
      logger.error('Can not connect to server.')

  def sigterm_handler(self, *_):
    self.stop_streams()
    self.stop_cron()
    self.stop_workers()
    self.disconnect(wait=True)
    sys.exit(0)

  def start_worker(self, bare_jid):
    w = self.worker_threads.get(bare_jid)
    if w and w.is_alive():
      pass
    else:
      logger.debug('%s: start worker.' % bare_jid)
      q = self.worker_queues[bare_jid] = Queue()
      w = self.worker_threads[bare_jid] = Worker(self, q)
      w.start()

  def start_workers(self):
    for user in db.get_all_users():
      if user['access_key'] and user['access_secret']:
        self.start_worker(user['jid'])

  def stop_workers(self):
    logger.info('shutdown workers.')
    for t in self.worker_threads.itervalues():
      t.stop()
    for t in self.worker_threads.itervalues():
      t.join()

  def start_cron(self):
    logger.debug('start cron.')
    self.cron_thread = CronStart(self.worker_queues)
    self.cron_thread.start()
    self.cron_misc_thread = CronMisc(self)
    self.cron_misc_thread.start()

  def stop_cron(self):
    logger.info('shutdown cron scheduler.')
    self.cron_thread.stop()
    self.cron_misc_thread.stop()
    self.cron_thread.join()
    self.cron_misc_thread.join()

  def start_stream(self, bare_jid):
    t = self.stream_threads.get(bare_jid)
    if t and t.is_alive():
      pass
    else:
      logger.debug('%s: start user streaming.' % bare_jid)
      t = StreamThread(self.worker_queues[bare_jid], bare_jid)
      t.start()
      self.stream_threads[bare_jid] = t

  def start_streams(self):
    for user in db.get_all_users():
      if user['access_key'] and user['access_secret']:
        self.start_stream(user['jid'])

  def stop_streams(self):
    logger.info('shutdown stream.')
    for t in self.stream_threads:
      t.stop()
    for t in self.stream_threads:
      t.join()


if __name__ == '__main__':
  major, minor, _ = platform.python_version_tuple()
  if major != '2' or minor < '6':
    print 'TwiOtaku needs Python 2.6 or later. Python 3.X is not supported yet.'
    exit(1)

  bot = XMPPBot()
  signal.signal(signal.SIGTERM, bot.sigterm_handler)
  bot.start(block=True)