import urllib2
import threading
import logging
import socket
from array import array
from time import sleep, time
from ssl import SSLError

try:
  import ujson as json
except ImportError:
  import json

import db
from config import OAUTH_CONSUMER_KEY, OAUTH_CONSUMER_SECRET
from worker import Job
from lib import twitter
from lib.decorators import debug

MAX_CONNECT_TIMEOUT = 5
MAX_DATA_TIMEOUT = 90
WAIT_TIMES = (0, 30, 60, 120, 240)
REFRESH_BLOCKED_IDS_INTERVAL = 3600

class ThreadStop(Exception):
  pass


class Timeout(Exception):
  pass


class StreamThread(threading.Thread):
  def __init__(self, xmpp, bare_jid):
    super(StreamThread, self).__init__()
    self.last_blocked_ids_update = 0
    self.stream_logger = logging.getLogger('user streaming')
    self._stop = threading.Event()
    self._user_changed = threading.Event()
    self.xmpp = xmpp
    self.bare_jid = bare_jid
    self.blocked_ids = array('L')
    self.user = db.get_user_from_jid(self.bare_jid)
    self.queue = self.xmpp.worker_queues[self.bare_jid]
    self.api = twitter.Api(consumer_key=OAUTH_CONSUMER_KEY,
      consumer_secret=OAUTH_CONSUMER_SECRET,
      access_token_key=self.user['access_key'],
      access_token_secret=self.user['access_secret'])

  def stop(self):
    self._stop.set()

  def user_changed(self):
    self._user_changed.set()

  def is_stopped(self):
    return self._stop.is_set()

  def is_user_changed(self):
    result = self._user_changed.is_set()
    if result:
      self._user_changed = threading.Event()
    return result

  # TODO: implement track and follow (list) (it's implemented in twitter lib)
  # TODO: use individual thread to update block and list ids

  def run(self):
    self.verify_credentials()
    self.refresh_blocked_ids()
    self.wait_time_now_index = 0
    try:
      while True:
        self.running()
        wait_time_now = WAIT_TIMES[self.wait_time_now_index]
        if wait_time_now:
          self.stream_logger.info('%s: Sleep %d seconds.' % (self.user['jid'], wait_time_now))
          for _ in xrange(wait_time_now):
            self.check_stop()
            sleep(1)
        if self.wait_time_now_index + 1 < len(WAIT_TIMES):
          self.wait_time_now_index += 1
    except ThreadStop:
      self.xmpp.global_lock.acquire()
      del self.xmpp.stream_threads[self.bare_jid]
      self.xmpp.global_lock.release()
      return

  @debug('userstreaming')
  def running(self):
    def read(fp, size):
      tmp = array('c')
      data_len = 0
      timeout_sum = 0
      while data_len < size:
        self.check_stop()
        try:
          c = fp.read(1)
        except SSLError:
          timeout_sum += MAX_CONNECT_TIMEOUT
          if timeout_sum > MAX_DATA_TIMEOUT:
            raise Timeout
        else:
          tmp.append(c)
          data_len += 1
      return ''.join(tmp)

    def read_line(fp):
      s = array('c')
      while True:
        char = read(fp, 1)
        s.append(char)
        if char == '\n':
          return ''.join(s)

    def read_data(fp):
      while True:
        # we should not directly use readline method of user_stream_handler,
        # because it has buffer which will block unintentionally
        length = read_line(fp).strip(' \r\n')
        if length:
          return json.loads(read(fp, int(length)))

    try:
      user_stream_handler = self.api.user_stream(timeout=MAX_CONNECT_TIMEOUT)
      self.stream_logger.debug('%s: User Streaming connected.' % self.user['jid'])
      # read out friends ids and eliminate them because they are useless.
      read_data(user_stream_handler)

      if self.wait_time_now_index:
        self.wait_time_now_index = 0

      while True:
        self.refresh_blocked_ids()
        data = read_data(user_stream_handler)
        self.check_user_changed()
        self.process(data)
    except (urllib2.URLError, urllib2.HTTPError, SSLError, Timeout, socket.error), e:
      self.stream_logger.warn('User Streaming connection failed.')
      if isinstance(e, urllib2.HTTPError):
        if e.code == 401:
          self.stream_logger.error('User %s OAuth unauthorized, exiting.' % self.user['jid'])
          raise ThreadStop
        if e.code == 420:
          self.stream_logger.warn('User %s Streaming connect too often!' % self.user['jid'])
          if not self.wait_time_now_index:
            self.wait_time_now_index = 1

  def refresh_blocked_ids(self):
    @debug('refresh_blocked_ids')
    def wrap():
      return self.api.get_blocking_ids()

    time_now = time()
    if time_now - self.last_blocked_ids_update >= REFRESH_BLOCKED_IDS_INTERVAL:
      result = wrap()
      self.last_blocked_ids_update = time_now
      if result:
        self.blocked_ids = result

  @debug()
  def verify_credentials(self):
    try:
      data = self.api.verify_credentials()
      screen_name = data['screen_name']
    except twitter.TwitterUnauthorizedError:
      db.update_user(jid=self.bare_jid, access_key=None, access_secret=None)
      raise ThreadStop
    else:
      if screen_name != self.user['screen_name']:
        self.user['screen_name'] = screen_name
        db.update_user(jid=self.bare_jid, screen_name=screen_name)
    self.user_at_screen_name = '@%s' % self.user['screen_name']

  @debug()
  def process(self, data):
    if 'event' in data:
      title = None
      if self.user['timeline'] & db.MODE_EVENT:
        if data['event'] == 'follow':
          title = '@%s is now following @%s.' % (data['source']['screen_name'], data['target']['screen_name'])
        elif data['event'] == 'block':
          if data['target']['id'] not in self.blocked_ids:
            self.blocked_ids.append(data['target']['id'])
          title = '@%s has blocked @%s.' % (data['source']['screen_name'], data['target']['screen_name'])
        elif data['event'] == 'unblock':
          if data['target']['id'] in self.blocked_ids:
            self.blocked_ids.remove(data['target']['id'])
          title = '@%s has unblocked @%s.' % (data['source']['screen_name'], data['target']['screen_name'])
        elif data['event'] == 'list_member_added':
          pass
        elif data['event'] == 'list_member_removed':
          pass
      if title:
        self.queue.put(Job(self.user['jid'], title=title, always=False))
    elif 'delete' in data:
      pass
    else:
      title = None
      if 'direct_message' in data:
        if self.user['timeline'] & db.MODE_DM:
          data = twitter.DirectMessage(data['direct_message'])
          title = 'Direct Message:'
        else:
          data = None
      else:
        if data['user']['id'] not in self.blocked_ids:
          if self.user['timeline'] & db.MODE_HOME\
          or (self.user['timeline'] & db.MODE_MENTION and self.user_at_screen_name in data['text']):
            data = twitter.Status(data)
            if self.user_at_screen_name in data['text']:
              retweeted_status = data.get('retweeted_status')
              if retweeted_status and retweeted_status.get('in_reply_to_status_id_str'):
                data['retweeted_status']['in_reply_to_status'] = None
              elif data.get('in_reply_to_status_id_str'):
                data['in_reply_to_status'] = None
          else:
            data = None
        else:
          data = None
      if data:
        self.queue.put(Job(self.user['jid'], data=data, allow_duplicate=False, always=False, title=title))

  def check_stop(self):
    if self.is_stopped():
      raise ThreadStop

  def check_user_changed(self):
    if self.is_user_changed():
      self.user = db.get_user_from_jid(self.bare_jid)
