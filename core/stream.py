import urllib2
import threading
import logging
import socket
import string
from array import array
from itertools import imap
from ssl import SSLError

try:
  import ujson as json
except ImportError:
  import json

import db
from config import OAUTH_CONSUMER_KEY, OAUTH_CONSUMER_SECRET
from worker import Job
from lib import twitter
from lib.thread import StoppableThread, ThreadStop, threadstop
from lib.logger import debug

MAX_CONNECT_TIMEOUT = 5
MAX_DATA_TIMEOUT = 90
WAIT_TIMES = (0, 30, 60, 120, 240)

logger = logging.getLogger('user streaming')
contain = lambda strlist, s: any(imap(s.__contains__, strlist))

class Timeout(Exception):
  pass


class StreamThread(StoppableThread):
  def __init__(self, queue, bare_jid):
    super(StreamThread, self).__init__()
    self._user_changed = threading.Event()
    self.bare_jid = bare_jid
    self.queue = queue
    self.refresh_user()

  def user_changed(self):
    self.refresh_user()
    self._user_changed.set()

  def is_user_changed(self):
    return self._user_changed.is_set()

  def check_user_changed(self):
    if self.is_user_changed():
      self._user_changed = threading.Event()
      self.user = db.get_user_from_jid(self.bare_jid)

  def refresh_user(self):
    logger.debug('%s: refresh user.' % self.bare_jid)
    self.user = db.get_user_from_jid(self.bare_jid)
    self.blocked_ids = array('L', imap(int, self.user['blocked_ids'].split(',')) if self.user['blocked_ids'] else ())
    self.list_ids = array('L', imap(int, self.user['list_ids'].split(',')) if self.user['list_ids'] else ())
    self.track_words = map(string.lower, self.user['track_words'].split(',')) if self.user['track_words'] else ()
    self.user_at_screen_name = '@%s' % self.user['screen_name']
    self.api = twitter.Api(consumer_key=OAUTH_CONSUMER_KEY, consumer_secret=OAUTH_CONSUMER_SECRET,
                           access_token_key=self.user['access_key'], access_token_secret=self.user['access_secret'])

  @threadstop
  def run(self):
    self.wait_time_now_index = 0
    while True:
      self.running()
      wait_time_now = WAIT_TIMES[self.wait_time_now_index]
      if wait_time_now:
        logger.info('%s: Sleep %d seconds.' % (self.user['jid'], wait_time_now))
        self.sleep(wait_time_now)
      if self.wait_time_now_index + 1 < len(WAIT_TIMES):
        self.wait_time_now_index += 1

  def read(self, fp, size):
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
        if c:
          tmp.append(c)
          data_len += 1
        else:
          raise Timeout
    return tmp.tostring()

  def read_line(self, fp):
    s = array('c')
    while True:
      char = self.read(fp, 1)
      s.append(char)
      if char == '\n':
        return s.tostring()

  def read_data(self, fp):
    while True:
      # we should not directly use readline method of user_stream_handler,
      # because it has its own buffer which will cause block unintentionally
      length = self.read_line(fp).strip(' \r\n')
      if length:
        return json.loads(self.read(fp, int(length)))


  @debug
  def running(self):
    try:
      user_stream_handler = self.api.user_stream(timeout=MAX_CONNECT_TIMEOUT, track=self.user['track_words'])
      logger.debug('%s: connected.' % self.user['jid'])

      self.friend_ids = array('L', self.read_data(user_stream_handler)['friends'])

      if self.wait_time_now_index:
        self.wait_time_now_index = 0

      while True:
        data = self.read_data(user_stream_handler)
        self.check_user_changed()
        if data:
          self.process(data)
    except urllib2.HTTPError, e:
      if e.code == 401:
        logger.error('User %s OAuth unauthorized, exiting.' % self.user['jid'])
        raise ThreadStop
      if e.code == 420:
        logger.warn('User %s Streaming connect too often!' % self.user['jid'])
        if not self.wait_time_now_index:
          self.wait_time_now_index = 1
    except (urllib2.URLError, SSLError, Timeout, socket.error), e:
      logger.warn('connection failed: %s' % unicode(e))

  @debug
  def process(self, data):
    if 'event' in data:
      title = None
      if self.user['timeline'] & db.MODE_EVENT:
        if data['event'] == 'follow':
          if data['source']['screen_name'] != self.user['screen_name']:
            title = '@%s is now following @%s.' % (data['source']['screen_name'], data['target']['screen_name'])
          else:
            if data['target']['id'] not in self.friend_ids:
              self.friend_ids.append(data['target']['id'])
        elif data['event'] == 'block':
          if data['target']['id'] not in self.blocked_ids:
            self.blocked_ids.append(data['target']['id'])
          if data['target']['id'] in self.friend_ids:
            self.friend_ids.remove(data['target']['id'])
          title = '@%s has blocked @%s.' % (data['source']['screen_name'], data['target']['screen_name'])
        elif data['event'] == 'unblock':
          if data['target']['id'] in self.blocked_ids:
            self.blocked_ids.remove(data['target']['id'])
          title = '@%s has unblocked @%s.' % (data['source']['screen_name'], data['target']['screen_name'])
        elif data['event'] == 'list_member_added':
          if data['target']['id'] not in self.list_ids:
            self.list_ids.append(data['target']['id'])
        elif data['event'] == 'list_member_removed':
          if data['target']['id'] in self.list_ids:
            self.list_ids.remove(data['target']['id'])
        elif data['event'] in ('favorite', 'unfavorite'):
          if data['source']['screen_name'] != self.user['screen_name']:
            title = '%s %sd %s\'s tweet %s.'\
            % (data['event'], data['source']['screen_name'], data['target']['screen_name'], data['target_object']['id_str'])
        else:
          logger.error('Unmatched event %s.' % data['event'])
      if title:
        self.queue.put(Job(self.user['jid'], title=title, always=False))
    elif 'delete' in data:
      pass
    else:
      title = None
      if 'direct_message' in data:
        if self.user['timeline'] & db.MODE_DM:
          data = twitter.DirectMessage(data['direct_message'])
          if data['sender_screen_name'] != self.user['screen_name']:
            title = 'Direct Message:'
          else:
            data = None
        else:
          data = None
      else:
        if data['user']['id'] in self.blocked_ids or\
           ('retweeted_status' in data and data['retweeted_status']['user']['id'] in self.blocked_ids) or\
           data['user']['screen_name'] == self.user['screen_name']:
          data = None
        else:
          data = twitter.CachedStatus(data)
          if (self.user['timeline'] & db.MODE_HOME and data['user']['id'] in self.friend_ids) or\
             (self.user['timeline'] & db.MODE_MENTION and self.user_at_screen_name in data['text']) or\
             (self.user['timeline'] & db.MODE_LIST and data['user']['id'] in self.list_ids) or\
             (self.user['timeline'] & db.MODE_TRACK and contain(self.track_words, data['text'].lower())):
            if self.user_at_screen_name in data['text']:
              retweeted_status = data.get('retweeted_status')
              if retweeted_status and retweeted_status.get('in_reply_to_status_id_str'):
                data['retweeted_status']['in_reply_to_status'] = None
              elif data.get('in_reply_to_status_id_str'):
                data['in_reply_to_status'] = None
          else:
            data = None
      if data:
        self.queue.put(Job(self.user['jid'], data=data, allow_duplicate=False, always=False, title=title, xmpp_command=False))
