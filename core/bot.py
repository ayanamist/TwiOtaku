import logging

from Queue import Queue
from itertools import ifilter

import sleekxmpp

import db
from config import XMPP_USERNAME, XMPP_PASSWORD
from core.xmpp import XMPPMessageHandler
from core.cron import CronStart, CronMisc
from core.stream import StreamThread
from core.worker import Worker
from core.messagesender import MessageSender
from lib.logger import debug

logger = logging.getLogger('xmpp')

class XMPPBot(sleekxmpp.ClientXMPP):
  messages_queue = Queue()
  worker_queues = dict()
  worker_threads = dict()
  stream_threads = dict()
  online_clients = dict() # this save available roster using ref count
  auto_authorize = True
  auto_subscribe = True
  first_run = True

  def __init__(self):
    sleekxmpp.ClientXMPP.__init__(self, XMPP_USERNAME, XMPP_PASSWORD)
    self.add_event_handler('session_start', self.on_start)
    self.add_event_handler('message', self.on_message)
    self.add_event_handler('changed_status', self.on_changed_status)
    self.register_plugin('xep_0030') # Service Discovery

  def on_start(self, _):
    self.get_roster()
    if self.first_run:
      self.first_run = False
      self.start_message_sender()
      self.start_workers()
      self.start_streams()
      self.start_cron()
    self.send_presence()

  @debug
  def on_message(self, msg):
    if msg['type'] == 'chat':
      XMPPMessageHandler(self).process(msg)
    elif msg['type'] == 'error':
      if msg['error']['type'] == 'cancel':
        # we can do nothing because if we resend this message, some of them will always fail.
        logger.warning('xmpp failed: %s', str(msg))
      else:
        logger.info('%s -> %s: %s' % (msg['from'], msg['to'], str(msg['error'])))

  def on_changed_status(self, presence):
    bare_jid = self.getjidbare(str(presence['from'])).lower()
    n = self.online_clients.get(bare_jid, 0)
    if presence['type'] in presence.types:
      if presence['type'] == 'available':
        self.online_clients[bare_jid] = n + 1
      else:
        self.online_clients[bare_jid] = n - 1

  def get_presence(self, jid):
    bare_jid = self.getjidbare(jid).lower()
    n = self.online_clients.get(bare_jid, 0)
    if n > 0:
      return True
    else:
      return False

  def send_message(self, mto, mbody, msubject=None, mtype=None, mhtml=None, mfrom=None, mnick=None):
    if mtype is None:
      mtype = 'chat' # we must set this so that messages can be saved into gmail.
    self.messages_queue.put(
      self.make_message(mto, mbody, msubject=msubject, mtype=mtype, mhtml=mhtml, mfrom=mfrom, mnick=mnick))

  def add_online_user(self, bare_jid):
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
    self.stop_message_sender()
    self.disconnect(wait=True)

  def start_message_sender(self):
    self.sender = MessageSender(self.messages_queue)
    self.sender.start()

  def stop_message_sender(self):
    self.messages_queue.put(None)
    self.sender.join()

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
    for user in ifilter(lambda user: user['access_key'] and user['access_secret'], db.get_all_users()):
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
      t.user_changed()
    else:
      logger.debug('%s: start user streaming.' % bare_jid)
      t = StreamThread(self.worker_queues[bare_jid], bare_jid)
      t.start()
      self.stream_threads[bare_jid] = t

  def start_streams(self):
    for user in ifilter(lambda user: user['access_key'] and user['access_secret'], db.get_all_users()):
      self.start_stream(user['jid'])

  def stop_stream(self, jid):
    t = self.stream_threads.get(jid)
    if t:
      t.stop()
      t.join()
      return True
    return False

  def stop_streams(self):
    logger.info('shutdown stream.')
    for t in self.stream_threads:
      t.stop()
    for t in self.stream_threads:
      t.join()


  