import urllib2
import threading
import logging
import socket
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
MAX_DATA_TIMEOUT = 180

class ThreadStop(Exception):
  pass


class Timeout(Exception):
  pass


class StreamThread(threading.Thread):
  """Thread class with a stop() method. The thread itself has to check
  regularly for the stopped() condition."""

  def __init__(self, xmpp, bare_jid):
    super(StreamThread, self).__init__()
    self._stop = threading.Event()
    self._user_changed = threading.Event()
    self.xmpp = xmpp
    self.bare_jid = bare_jid
    self.blocked_ids = list()
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

  # TODO: implement track and follow (list) (possibly via select?)

  def run(self):
    try:
      self.running()
    except ThreadStop:
      self.xmpp.global_lock.acquire()
      del self.xmpp.stream_threads[self.bare_jid]
      self.xmpp.global_lock.release()
      return

  @debug('userstreaming')
  def running(self):
    def read(fp, length):
      tmp_list = []
      data_len = 0
      timeout_sum = 0
      while data_len < length:
        check_stop()
        try:
          c = fp.read(1)
        except SSLError:
          timeout_sum += MAX_CONNECT_TIMEOUT
          if timeout_sum > MAX_DATA_TIMEOUT:
            raise Timeout
        else:
          tmp_list.append(c)
          data_len += 1
      return ''.join(tmp_list)

    def read_line(fp):
      s = ''
      while True:
        char = read(fp, 1)
        s += char
        if char == '\n':
          return s

    def read_data(fp):
      while True:
        # we should not directly use readline method of user_stream_handler,
        # because it has buffer which will block unintentionally
        length = read_line(fp).strip(' \r\n')
        if length:
          return json.loads(read(fp, int(length)))

    def refresh_blocked_ids():
      @debug('refresh_blocked_ids')
      def wrap():
        return self.api.get_blocking_ids()

      result = wrap()
      if result is not None:
        self.blocked_ids = result

    def check_stop():
      if self.is_stopped():
        raise ThreadStop

    def check_user_changed():
      if self.is_user_changed():
        self.user = db.get_user_from_jid(self.bare_jid)

    @debug()
    def verify_credentials():
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
        self.twitter_user_id = data['id_str']

    @debug()
    def process(data):
      if 'event' in data:
        title = None
        if self.user['timeline'] & db.MODE_EVENT:
          if data['event'] == 'follow':
            title = '@%s is now following @%s.' % (data['source']['screen_name'], data['target']['screen_name'])
          elif data['event'] == 'block':
            refresh_blocked_ids()
            title = '@%s has blocked @%s.' % (data['source']['screen_name'], data['target']['screen_name'])
          elif data['event'] == 'unblock':
            refresh_blocked_ids()
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
          user_at_screen_name = '@%s' % self.user['screen_name']
          if data['user']['id_str'] not in self.blocked_ids:
            if self.user['timeline'] & db.MODE_HOME\
            or (self.user['timeline'] & db.MODE_MENTION and user_at_screen_name in data['text']):
              data = twitter.Status(data)
              if user_at_screen_name in data['text']:
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


    stream_logger = logging.getLogger('user streaming')
    verify_credentials()
    wait_times = (0, 30, 60, 120, 240)
    wait_time_now_index = 0
    refresh_blocked_ids()
    last_blocked_ids_update = time()
    refresh_blocked_ids_interval = 3600
    while True:
      try:
        user_stream_handler = self.api.user_stream(timeout=MAX_CONNECT_TIMEOUT)
        stream_logger.debug('%s: User Streaming connected.' % self.user['jid'])
        # read out friends ids and eliminate them because they are useless.
        read_data(user_stream_handler)

        if wait_time_now_index:
          wait_time_now_index = 0

        while True:
          time_now = time()
          if time_now - last_blocked_ids_update >= refresh_blocked_ids_interval:
            check_stop()
            refresh_blocked_ids()
            last_blocked_ids_update = time_now
          data = read_data(user_stream_handler)
          check_user_changed()
          process(data)
      except (urllib2.URLError, urllib2.HTTPError, SSLError, Timeout, socket.error), e:
        stream_logger.warn('User Streaming connection failed.')
        if isinstance(e, urllib2.HTTPError):
          if e.code == 401:
            stream_logger.error('User %s OAuth unauthorized, exiting.' % self.user['jid'])
            raise ThreadStop
          if e.code == 420:
            stream_logger.warn('User %s Streaming connect too often!' % self.user['jid'])
            if not wait_time_now_index:
              wait_time_now_index = 1
        wait_time_now = wait_times[wait_time_now_index]
        if wait_time_now:
          stream_logger.info('%s: Sleep %d seconds.' % (self.user['jid'], wait_time_now))
          for _ in xrange(wait_time_now):
            check_stop()
            sleep(1)
        if wait_time_now_index + 1 < len(wait_times):
          wait_time_now_index += 1

