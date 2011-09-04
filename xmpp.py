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
from worker import worker
from config import XMPP_USERNAME, XMPP_PASSWORD, OAUTH_CONSUMER_KEY, OAUTH_CONSUMER_SECRET, ADMIN_USERS

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
  def __init__(self):
    self.logger = logging.getLogger('xmpp')
    self.tbd_queues = dict()
    self.tbd_threads = dict()
    self.online_clients = dict()
    self.online_users = set()
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
    bare_jid = presence['from']._jid.split('/')[0].lower()
    n = self.online_clients.get(bare_jid, 0)
    if presence['type'] == 'available':
      self.online_clients[bare_jid] = n + 1
      if bare_jid not in self.online_users:
        user = db.get_user_from_jid(bare_jid)
        if user and user['access_key'] and user['access_secret']:
          self.add_online_user(bare_jid)
    else:
      if n > 1:
        self.online_clients[bare_jid] = n - 1
      elif n == 1:
        del self.online_clients[bare_jid]
        self.online_users.remove(bare_jid)

  def add_online_user(self, bare_jid):
    self.online_users.add(bare_jid)
    if bare_jid not in self.tbd_queues:
      q = self.tbd_queues[bare_jid] = Queue()
      w = self.tbd_threads[bare_jid] = Thread(target=worker, args=(self, q))
      w.setDaemon(True)
      w.start()


class XMPPMessageHandler(object):
  def __init__(self, xmpp):
    self._xmpp = xmpp

  def process(self, msg):
    self._bare_jid = msg['from']._jid.split('/')[0].lower()
    self._user = db.get_user_from_jid(self._bare_jid)
    self.api = twitter.Api(consumer_key=OAUTH_CONSUMER_KEY, consumer_secret=OAUTH_CONSUMER_SECRET,
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
      self.api.post_update(cmd)

  def func_oauth(self):
    consumer = oauth.Consumer(OAUTH_CONSUMER_KEY, OAUTH_CONSUMER_SECRET)
    client = oauth.Client(consumer)
    resp = client.request(twitter.REQUEST_TOKEN_URL)
    self._request_token = dict(parse_qsl(resp))
    oauth_token = self._request_token['oauth_token']
    redirect_url = "%s?oauth_token=%s" % (twitter.AUTHORIZATION_URL, oauth_token)
    db.update_user(self._user['id'], access_key=oauth_token)
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
        if self._bare_jid not in self._xmpp.online_users:
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

