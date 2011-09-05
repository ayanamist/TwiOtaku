import random
import logging
import traceback
import time
from StringIO import StringIO
from Queue import Queue
from threading import Thread

try:
  from urlparse import parse_qsl
except ImportError:
  from cgi import parse_qsl

import sleekxmpp

import oauth
import twitter
import db
from util import Util
from worker import worker, Job
from config import XMPP_USERNAME, XMPP_PASSWORD, OAUTH_CONSUMER_KEY, OAUTH_CONSUMER_SECRET, MAX_CONVERSATION_NUM, ADMIN_USERS

SHORT_COMMANDS = {
  '@': 'reply',
  'r': 'reply',
  'd': 'dm',
  're': 'retweet',
  'ho': 'home',
  'lt': 'list',
  'tl': 'timeline',
  'fo': 'follow',
  'unfo': 'unfollow',
  'b': 'block',
  'ub': 'unblock',
  'm': 'msg',
  'f': 'fav',
  'uf': 'unfav',
  'u': 'user',
  '?': 'help',
  'h': 'help'
}

class XMPPBot(sleekxmpp.ClientXMPP):
  def __init__(self, threads, queues):
    self.logger = logging.getLogger('xmpp')
    self.worker_threads = threads
    self.worker_queues = queues
    self.online_clients = dict() # this save online buddies no matter it's our users or not.
    sleekxmpp.ClientXMPP.__init__(self, XMPP_USERNAME, XMPP_PASSWORD)
    self.auto_authorize = True
    self.auto_subscribe = True
    self.add_event_handler('session_start', self.on_start)
    self.add_event_handler('message', self.on_message)
    self.add_event_handler('changed_status', self.on_changed_status)

  def on_start(self, _):
    self.send_presence()
    self.get_roster()

  def on_message(self, msg):
    if msg['type'] == 'chat':
      XMPPMessageHandler(self).process(msg)
    elif msg['type'] == 'error':
      if msg['error']['type'] == 'cancel': # If we send lots of stanzas at the same time, some of them will be returned as type "error", we must resend them.
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
      if bare_jid not in self.worker_queues:
        q = self.worker_queues[bare_jid] = Queue()
        w = self.worker_threads[bare_jid] = Thread(target=worker, args=(self, q))
        w.setDaemon(True)
        w.start()


class XMPPMessageHandler(object):
  def __init__(self, xmpp):
    self._xmpp = xmpp

  def process(self, msg):
    self._jid = str(msg['from'])
    self._bare_jid = self._xmpp.getjidbare(self._jid).lower()
    self._user = db.get_user_from_jid(self._bare_jid)
    self._util = Util(self._user)
    self._api = twitter.Api(consumer_key=OAUTH_CONSUMER_KEY, consumer_secret=OAUTH_CONSUMER_SECRET,
                            access_token_key=self._user.get('access_key'), access_token_secret=self._user.get('access_secret'))

    try:
      result = self.parse_command(msg['body'].rstrip())
    except BaseException, e:
      result = str(e)
      err = StringIO()
      traceback.print_exc(file=err)
      xmpp_logger = logging.getLogger('xmpp')
      xmpp_logger.error(err.getvalue())

    if result:
      msg.reply(result).send()

  def parse_command(self, cmd):
    if cmd[0] == '-' or cmd[0] == ' ':
      args = cmd[1:].split(' ')
      if args[0] in SHORT_COMMANDS:
        args[0] = SHORT_COMMANDS[args[0]]
      if not self._user and args[0] != 'invite':
        return
      func_name = 'func_' + args[0]
      if func_name in dir(self):
        func = getattr(self, func_name)
      else:
        return 'Invalid command.'
      return func(*args[1:])
    else:
      if len(cmd) > twitter.CHARACTER_LIMIT:
        return 'Words count %s exceeed %s characters.' % (len(cmd), twitter.CHARACTER_LIMIT)
      if type(cmd) == unicode:
        cmd = cmd.encode('UTF8')
      self._api.post_update(cmd)

  def func_oauth(self):
    consumer = oauth.Consumer(OAUTH_CONSUMER_KEY, OAUTH_CONSUMER_SECRET)
    client = oauth.Client(consumer)
    resp = client.request(twitter.REQUEST_TOKEN_URL)
    self._request_token = dict(parse_qsl(resp))
    oauth_token = self._request_token['oauth_token']
    redirect_url = "%s?oauth_token=%s" % (twitter.AUTHORIZATION_URL, oauth_token)
    db.update_user(self._user['id'], access_key=oauth_token, access_secret=None)
    return 'Please visit below url to get PIN code:\n%s\nthen you should use "-bind PIN" command to actually bind your Twitter.' % redirect_url

  def func_bind(self, pin_code):
    if type(pin_code) is unicode:
      pin_code = pin_code.encode('UTF8')
    if self._user['access_key']:
      token = oauth.Token(self._user['access_key'])
      token.set_verifier(pin_code)
      consumer = oauth.Consumer(OAUTH_CONSUMER_KEY, OAUTH_CONSUMER_SECRET)
      client = oauth.Client(consumer, token)
      resp = client.request(twitter.ACCESS_TOKEN_URL, "POST")
      access_token = dict(parse_qsl(resp))
      if 'oauth_token' in access_token:
        db.update_user(self._user['id'], access_key=access_token['oauth_token'], access_secret=access_token['oauth_token_secret'],
                       screen_name=access_token['screen_name'])
        self._xmpp.add_online_user(self._bare_jid)
        return 'Successfully bind you with Twitter user @%s.' % access_token['screen_name']
    return 'Invalid PIN code.'

  def func_invite(self, invite_code=None):
    def generate_invite_code():
      valid_chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
      return ''.join(random.choice(valid_chars) for _ in range(8))

    expire_days = 3

    if invite_code and not self._user:
      invite_code, create_time = db.get_invite_code(invite_code)
      if invite_code and create_time and create_time + expire_days * 24 * 3600 > time.time():
        db.delete_invite_code(invite_code)
        db.add_user(self._bare_jid)
        return 'Your account %s has been added, enjoy using TwiOtaku.' % self._bare_jid
      else:
        return 'Invite code is invalid or expired.'

    elif self._bare_jid in ADMIN_USERS:
      invite_code = generate_invite_code()
      create_time = int(time.time())
      db.add_invite_code(invite_code, create_time)
      return 'You have generated a new invite code which is available for %d days:\n%s' % (expire_days, invite_code)

  def func_reply(self, short_id_or_page=None, *content):
    if short_id_or_page is None or (short_id_or_page[0].lower() == 'p' and short_id_or_page[1:].isdigit()):
      page = short_id_or_page[1:] if short_id_or_page else '1'
      statuses = self._api.get_mentions(page=int(page))
      queue = self._xmpp.worker_queues.get(self._bare_jid)
      queue.put(Job(self._jid, data=statuses, title='Mentions: Page %s' % page))
    else:
      long_id, long_id_type = self._util.restore_short_id(short_id_or_page)
      if long_id_type == db.TYPE_STATUS:
        status = self._api.get_status(long_id)
        screen_name = status['user']['screen_name']
      else:
        direct_message = self._api.get_direct_message(long_id)
        screen_name = direct_message['sender']['screen_name']
      message = u'@%s %s' % (screen_name, ' '.join(content))
      self._api.post_update(message.encode('UTF8'), long_id)


  def func_msg(self, short_id_or_long_id):
    long_id, long_id_type = self._util.restore_short_id(short_id_or_long_id)
    data = list()
    if long_id_type == db.TYPE_STATUS:
      origin_status = self._api.get_status(long_id)
      related_result = self._api.get_related_results(long_id)
      if related_result:
        last_conversation_role = 'Ancestor' # possible value: Ancestor, Descendant, Fork
        related_result = related_result[0]['results']
        for result in related_result:
          if result['kind'] == 'Tweet':
            if result['annotations']['ConversationRole'] != last_conversation_role:
              data.append(origin_status)
              last_conversation_role = result['annotations']['ConversationRole']
            data.append(result['value'])
      else:
        data.append(origin_status)
      while len(data) <= MAX_CONVERSATION_NUM:
        status = data[0]
        if status['in_reply_to_status_id_str']:
          long_id = status['in_reply_to_status_id_str']
          try:
            status = self._api.get_status(long_id)
          except twitter.TwitterNotFoundError:
            break
        else:
          break
        if 'retweeted_status' in status:
          data.insert(0, status['retweeted_status'])
        else:
          data.insert(0, status)
    else:
      data = [self._api.get_direct_message(long_id)]
    queue = self._xmpp.worker_queues.get(self._bare_jid)
    queue.put(Job(self._jid, data=data, title='Conversation:', reverse=False))
