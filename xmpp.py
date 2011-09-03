import logging
try:
  from urlparse import parse_qsl
except ImportError:
  from cgi import parse_qsl

import sleekxmpp

import oauth
import twitter
import db

SHORT_COMMANDS = {
  '@': 'reply',
  'r': 'reply',
  'd': 'dm',
  'ho': 'home',
  'lt': 'list',
  'tl': 'timeline',
  's': 'switch',
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

class Dummy(object):
  def __getattr__(self, _):
    raise NotImplementedError('Please OAuth first!')

class XMPPBot(sleekxmpp.ClientXMPP):
  def __init__(self, config):
    self._config = config
    sleekxmpp.ClientXMPP.__init__(self, config['XMPP_USERNAME'], config['XMPP_PASSWORD'])
    self.auto_authorize = True
    self.auto_subscribe = True
    self.add_event_handler('session_start', self.on_start)
    self.add_event_handler('message', self.on_message)
    self.add_event_handler('changed_status', self.on_changed_status)
    self.online_clients = dict()

  def on_start(self, _):
    self.send_presence()
    self.get_roster()

  def on_message(self, msg):
    bare_jid = msg['from']._jid.split('/')[0].lower()
    user = db.get_user_from_jid(bare_jid)
    if user:
      h = XMPPMessageHandler(user, self._config)
      try:
        result = h.parse_command(msg['body'].rstrip())
      except BaseException, e:
        result = str(e)
        import traceback
        from StringIO import StringIO

        err = StringIO()
        traceback.print_exc(file=err)
        xmpp_logger = logging.getLogger('xmpp')
        xmpp_logger.error(err.getvalue())

      if result:
        msg.reply(result).send()

  def on_changed_status(self, presence):
    bare_jid = presence['from']._jid.split('/')[0].lower()
    n = self.online_clients.get(bare_jid, 0)
    if presence['type'] == 'available':
      if n > 0:
        self.online_clients[bare_jid] = n + 1
      else:
        user = db.get_user_from_jid(bare_jid)
        if user and user['enabled'] and user['timeline']:
          self.online_clients[bare_jid] = 1
    else:
      if n > 1:
        self.online_clients[bare_jid] = n - 1
      elif n == 1:
        del self.online_clients[bare_jid]


class XMPPMessageHandler(object):
  def __init__(self, user, config):
    self._user = user
    self._config = config
    if user['access_key'] and user['access_secret']:
      self.api = twitter.Api(consumer_key=config['OAUTH_CONSUMER_KEY'], consumer_secret=config['OAUTH_CONSUMER_SECRET'],
                             access_token_key=user['access_key'], access_token_secret=user['access_secret'])
    else:
      self.api = Dummy()

  def parse_command(self, cmd):
    if cmd[0] == '-' or cmd[0] == ' ':
      args = cmd[1:].split(' ')
      if args[0] in SHORT_COMMANDS:
        args[0] = SHORT_COMMANDS[args[0]]
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
    consumer = oauth.Consumer(self._config['OAUTH_CONSUMER_KEY'], self._config['OAUTH_CONSUMER_SECRET'])
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
      consumer = oauth.Consumer(self._config['OAUTH_CONSUMER_KEY'], self._config['OAUTH_CONSUMER_SECRET'])
      client = oauth.Client(consumer, token)
      resp = client.request(twitter.ACCESS_TOKEN_URL, "POST")
      access_token = dict(parse_qsl(resp))
      if 'oauth_token' in access_token:
        db.update_user(self._user['id'], access_key=access_token['oauth_token'], access_secret=access_token['oauth_token_secret'],
                       screen_name=access_token['screen_name'], enabled=1)
        return 'Successfully bind you with Twitter user @%s.' % access_token['screen_name']
    return 'Invalid PIN code.'
