# -*- encoding: utf8 -*-
# Copyright 2011 ayanamist
# the program is distributed under the terms of the GNU General Public License
# This file is part of TwiOtaku.
#
#    Foobar is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    TwiOtaku is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with TwiOtaku.  If not, see <http://www.gnu.org/licenses/>.

import datetime
import email.utils
import operator
import random
import re
import time
import urlparse

import config
import db
from lib import logdecorator
from lib import oauth
from lib import twitter
from lib import util
from misc import template_test

def generate_invite_code(length=8):
    valid_chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789'
    return ''.join(random.choice(valid_chars) for _ in xrange(length))


SHORT_COMMANDS = {
    '@': 'reply',
    'r': 'reply',
    'd': 'dm',
    'ra': 'replyall',
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
    'h': 'help',
    }

HELP_MESSAGES = {
    "on": u"USAGE:-on [home|dm|mention|list|event|track]\nEnable automatic update for [home|dm|mention|list|event|track].",
    "off": u"USAGE:-off [home|dm|mention|list|event|track]\nDisable automatic update for [home|dm|mention|list|event|track].",
    "ho": u"USAGE:-ho [PAGE_NUMBER]\nShow home timeline, page one for default. \nSame as -home command.",
    "home": u"USAGE:-home [PAGE_NUMBER]\nShow home timeline, page one for default. \nSame as -ho command.",
    "@": u"USAGE:-@ [TWEET_NUMBER] [REPLY_CONTENT]\nReply to a tweet, show mentions if no TWEET_NUMBER or [REPLY_CONTENT] given. \nSame as -r and -reply command.",
    "r": u"USAGE:-r [TWEET_NUMBER] [REPLY_CONTENT]\nReply to a tweet, show mentions if no TWEET_NUMBER or [REPLY_CONTENT] given. \nSame as -@ and -reply command.",
    "reply": u"USAGE:-reply [TWEET_NUMBER] [REPLY_CONTENT]\nReply to a tweet, show mentions if no TWEET_NUMBER or [REPLY_CONTENT] given. \nSame as -@ and -r command.",
    "ra": u"USAGE:-ra TWEET_NUMBER REPLY_CONTENT\nReply to all users in a tweet. \nSame as -replyall command.",
    "replyall": u"USAGE:-replyall TWEET_NUMBER REPLY_CONTENT\nReply to all users in a tweet. \nSame as -ra command.",
    "del": u"USAGE:-del [TWEET_NUMBER]\nDelete a tweet, delete your last tweet if no TWEET_NUMBER given.",
    "rt": u"USAGE:-rt TWEET_NUMBER [COMMENT]\nRetweet a tweet, Official retweet if no COMMENT given.",
    "d": u"USAGE:-d [DM_NUMBER|USER_ID] [DM_CONTENT]\nSend a direct message, show all direct messages if no DM_NUMBER of USER_ID given. \nSame as -dm command.",
    "dm": u"USAGE:-dm [DM_NUMBER|USER_ID] [DM_CONTENT]\nSend a direct message, show all direct messages if no DM_NUMBER of USER_ID given. \nSame as -d command.",
    "lt": u"USAGE:-lt [LIST_NAME]\nShow a list, show lists following you if no LIST_NAME given. \nSame as -list command.",
    "list": u"USAGE:-list [LIST_NAME]\nShow a list, show lists following you if no LIST_NAME given. \nSame as -lt command.",
    "fo": u"USAGE:-fo USER_ID\nFollow a user. \nSame as -follow command.",
    "unfo": u"USAGE:-unfo USER_ID\nUnfollow a user. \nSame as -unfollow command.",
    "follow": u"USAGE:-fo USER_ID\nFollow a user. \nSame as -fo command.",
    "unfollow": u"USAGE:-unfo USER_ID\nUnfollow a user. \nSame as -unfo command.",
    "b": u"USAGE:-b USER_ID\nBlock a user. \nSame as -block command.",
    "block": u"USAGE:-block USER_ID\nBlock a user. \nSame as -b command.",
    "ub": u"USAGE:-ub USER_ID\nUnblock a user. \nSame as -unblock command.",
    "unblock": u"USAGE:-unblock USER_ID\nUnblock a user. \nSame as -ub command.",
    "u": u"USAGE:-u USER_ID\nShow a user's profile. \nSame as -user command.",
    "tl": u"USAGE:-tl USER_ID\nShow a user's timeline. \nSame as -tl command.",
    "timeline": u"USAGE:-timeline USER_ID\nShow a user's timeline. \nSame as -timeline command.",
    "if": u"USAGE:-if USER_ID_A [USER_ID_B]\nShow whether user A and user B are friends, show whether user A is your friend if no USER_ID_B given.",
    "always": u"USAGE:-always [true|on|1][false|off|0]\nEnable/Disable automatic update when you are offline.",
    "track": u"USAGE:-track *KEYWORDS\nEnable track for your keywords(1 or more).",
    "oauth": u"USAGE:-oauth\nGet twitter oauth url for your account.",
    "bind": u"USAGE:-bind PIN\nBind your twitter account with bot.",
    "invite": u"USAGE:-invite [INVITE_CODE]\nCheck your invite with invite code, generate new invite code if no INVITE_CODE given(You must be admin)."
    }


DEFAULT_MESSAGE = u"ALL COMMANDS AVAILABLE:\n-on\n-off\n{-@|-r|-reply}\n{-d|-dm}\n{-ra|-replyall}\n{-ho|-home}\n-del\n-rt\n{-tl|-timeline}\n{-lt|-list}\n{-fo|-follow}\n{-unfo|-unfollow}\n{-b|-block}\n{-ub|-unblock}\n{-m|-msg}\n{-f|-fav}\n{-uf|-unfav}\n{-u|-user}\n-if\n-always\n-track\n-oauth\n-bind\n-invite\nType '-h command' or '-help command' for details."

_screen_name_regex = r'[a-zA-Z0-9_]+'

class XMPPMessageHandler(object):
    def __init__(self, xmpp):
        self._xmpp = xmpp

    @logdecorator.debug
    def process(self, msg):
        self._jid = str(msg['from'])
        self._bare_jid = self._xmpp.getjidbare(self._jid).lower()
        self._user = db.get_user_from_jid(self._bare_jid)
        self._job = {"jid": self._jid}
        self._queue = None
        if self._user:
            self._util = util.Util(self._user)
            t = self._xmpp.worker_threads.get(self._bare_jid)
            if t:
                self._queue = t.job_queue
            self._api = twitter.Api(consumer_key=config.OAUTH_CONSUMER_KEY,
                consumer_secret=config.OAUTH_CONSUMER_SECRET,
                access_token_key=self._user.get('access_key'),
                access_token_secret=self._user.get('access_secret'))
        try:
            self.parse_command(msg['body'])
        except Exception, e:
            self._job["title"] = str(e)
        if self._queue:
            self._queue.put(self._job)
        else:
            msg.reply(self._job["title"]).send()

    def parse_command(self, cmd):
        if cmd[0] in (u"－", '-', ' '):
            args = cmd[1:].split()
            if args[0] in SHORT_COMMANDS:
                args[0] = SHORT_COMMANDS[args[0]]
            if not self._user and args[0] != 'invite':
                return
            func_name = 'func_' + args[0]
            result = getattr(self, func_name)(*args[1:])
            if result:
                self._job["title"] = result
        else:
            if not self._user:
                return
            try:
                self._job["data"] = self._api.post_update(cmd.encode('UTF8'))
            except twitter.ForbiddenError, e:
                message_length = twitter.actual_len(cmd)
                if message_length > twitter.CHARACTER_LIMIT:
                    raise twitter.ForbiddenError('%s\nMaybe too long: %d' % (str(e), message_length))
                else:
                    raise e
            else:
                self._job["no_duplicate"] = True


    def func_oauth(self):
        consumer = oauth.Consumer(config.OAUTH_CONSUMER_KEY, config.OAUTH_CONSUMER_SECRET)
        client = oauth.Client(consumer)
        resp = client.request(twitter.REQUEST_TOKEN_URL)
        if resp:
            request_token = dict(urlparse.parse_qsl(resp))
            oauth_token = request_token['oauth_token']
            redirect_url = "%s?oauth_token=%s" % (twitter.AUTHORIZATION_URL, oauth_token)
            db.update_user(self._user['id'], access_key=oauth_token, access_secret=None)
            return u'Please visit below url to get PIN code:\n%s\nthen you should use "-bind PIN" command to actually bind your Twitter.' % redirect_url
        else:
            return u'Network error.'

    def func_bind(self, pin_code):
        if self._user['access_key']:
            token = oauth.Token(self._user['access_key'])
            if type(pin_code) is unicode:
                pin_code = pin_code.encode('UTF8')
            token.set_verifier(pin_code)
            consumer = oauth.Consumer(config.OAUTH_CONSUMER_KEY, config.OAUTH_CONSUMER_SECRET)
            client = oauth.Client(consumer, token)
            resp = client.request(twitter.ACCESS_TOKEN_URL, "POST")
            if not resp:
                return u'Network error.'
            access_token = dict(urlparse.parse_qsl(resp))
            if 'oauth_token' in access_token:
                db.update_user(self._user['id'], access_key=access_token['oauth_token'],
                    access_secret=access_token['oauth_token_secret'],
                    screen_name=access_token['screen_name'])
                self._xmpp.add_online_user(self._bare_jid)
                return u'Associated you with @%s.' % access_token['screen_name']
        return u'Invalid PIN code.'

    def func_invite(self, invite_code=None):
        expire_days = 3

        if invite_code:
            create_time = db.verify_invite_code(invite_code)
            if create_time and create_time + expire_days * 24 * 3600 > time.time():
                db.delete_invite_code(invite_code)
                if not self._user:
                    db.add_user(self._bare_jid)
                return u'Your account %s has been added, enjoy using TwiOtaku.' % self._bare_jid
            else:
                return u'Invite code is invalid or expired.'
        elif self._bare_jid in config.ADMIN_USERS:
            invite_code = generate_invite_code()
            create_time = int(time.time())
            db.add_invite_code(invite_code, create_time)
            return u'You have generated a new invite code which is available for %d days: %s' % (
                expire_days, invite_code)

    def func_user(self, short_id_or_screen_name=None):
        if short_id_or_screen_name and short_id_or_screen_name[0] == '#':
            long_id, long_id_type = self._util.restore_short_id(short_id_or_screen_name)
            if long_id_type == db.TYPE_STATUS:
                status = self._api.get_status(long_id)
                twitter_user = status['user']
            else:
                direct_message = self._api.get_direct_message(long_id)
                twitter_user = direct_message['sender']
        else:
            if short_id_or_screen_name is None:
                short_id_or_screen_name = self._user['screen_name']
            twitter_user = self._api.get_user(screen_name=short_id_or_screen_name)
        texts = [u'User @%s (%s):' % (twitter_user['screen_name'], twitter_user['name'])]
        if twitter_user['protected']:
            follow_str = [u'Protected user. ']
        else:
            follow_str = [u'']
        if twitter_user['following']:
            follow_str.append(u'You are following.')
        else:
            if twitter_user['follow_request_sent']:
                follow_str.append(u'You have sent follow request.')
            else:
                follow_str.append(u'You are not following.')
        texts.append(u''.join(follow_str))
        avatar_url = twitter_user['profile_image_url_https']
        i = avatar_url.rfind('_normal.')
        if i != -1:
            avatar_url = avatar_url[:i] + avatar_url[i + 7:]
        texts.append(u'Avatar: %s' % avatar_url)
        if twitter_user['url']:
            texts.append(u'Web: %s' % twitter_user['url'])
        if twitter_user['location']:
            texts.append(u'Location: %s' % twitter_user['location'])
        texts.append(u'Following: %d' % twitter_user['friends_count'])
        texts.append(u'Followers: %d' % twitter_user['followers_count'])
        texts.append(u'Tweets: %d' % twitter_user['statuses_count'])
        join_time = time.mktime(email.utils.parsedate(twitter_user['created_at']))
        join_time += 28800
        join_time = time.strftime(u'%Y-%m-%d %H:%M:%S', time.localtime(join_time))
        texts.append(u'Joined at: %s' % join_time)
        tweet_per_day = twitter_user['statuses_count'] * 86400 /\
                        (time.time() - time.mktime(email.utils.parsedate(twitter_user['created_at'])))
        texts.append(u'Tweets per day: %.2f' % tweet_per_day)
        if twitter_user['description']:
            texts.append(u'Bio: %s' % twitter_user['description'])
        return '\n'.join(texts)

    def func_list(self, *args):
        length = len(args)
        if not length:
            lists = self._api.get_all_lists()
            texts = list()
            for l in lists:
                texts.append(u'%s %s: %s' %
                             (l['slug'] if l['user']['screen_name'] == self._user['screen_name'] else u'%s/%s' % (
                                 l['user']['screen_name'],
                                 l['slug']), l['mode'], l['description']))
            return u'Subscribing Lists:\n' + '\n'.join(texts)
        elif length == 1 or (length == 2 and args[1].isdigit()):
            try:
                page = int(args[1]) if length == 2 else 1
            except ValueError:
                return u'Unknown page number: %s.' % args[1]
            list_user_name = args[0]
            path = list_user_name.split('/', 1)
            if len(path) == 1:
                list_user = self._user['screen_name']
                list_name = path[0]
            else:
                list_user, list_name = path
            self._job["data"] = self._api.get_list_statuses(list_user, list_name, page=page)
            self._job["title"] = 'List %s Statuses: Page %d' % (list_user_name, page)
        else:
            list_command = args[0].lower()
            if list_command == 'info' and length == 2:
                list_user_name = args[1]
                path = list_user_name.split('/', 1)
                if len(path) == 1:
                    list_user = self._user['screen_name']
                    list_name = path[0]
                else:
                    list_user, list_name = path
                l = self._api.get_list(screen_name=list_user, slug=list_name)
                texts = (u'List %s/%s %s: %s' %
                         (l['user']['screen_name'], l['slug'], l['mode'],
                          u'You are following.' if l['following'] else u''),
                         u'Member Count: %d' % l['member_count'], u'Subscriber Count: %d' % l['subscriber_count'],
                         u'Description: %s' % l['description'])
                return '\n'.join(texts)
            elif list_command in ('add', 'del') and 2 <= length <= 3:
                if length == 2:
                    if list_command == 'add':
                        self._api.create_list(args[1], public=False)
                        return u'Created private list %s.' % args[1]
                    else:
                        self._api.destroy_list(self._user['screen_name'], args[1])
                        return u'Deleted list %s.' % args[1]
                else:
                    if list_command == 'add':
                        self._api.create_list_member(self._user['screen_name'], args[1], args[2])
                        title = u'Added %s to list %s.' % (args[2], args[1])
                    else:
                        self._api.destroy_list_member(self._user['screen_name'], args[1], args[2])
                        title = u'Removed %s from list %s.' % (args[2], args[1])
                    if self._user['screen_name'] == self._user['list_user'] and args[1] == self._user['list_name']:
                        db.update_user(id=self._user['id'], list_ids_last_update=0)
                        self._xmpp.stream_threads[self._bare_jid].user_changed()
                    return title
            else:
                raise TypeError('Not supported list command.')

    def func_home(self, page=1):
        try:
            page = int(page)
        except ValueError:
            return u'Unknown page number: %s.' % page
        self._job["data"] = self._api.get_home_timeline(page=page)
        self._job["title"] = 'Home Timeline: Page %d' % page

    def func_timeline(self, screen_name_or_short_id=None, page=1):
        try:
            page = int(page)
        except ValueError:
            return u'Unknown page number: %s.' % page
        if not screen_name_or_short_id:
            screen_name_or_short_id = self._user['screen_name']
        elif screen_name_or_short_id[0] == '#':
            long_id, long_id_type = self._util.restore_short_id(screen_name_or_short_id)
            if long_id_type == db.TYPE_STATUS:
                status = self._api.get_status(long_id)
                screen_name_or_short_id = status['user']['screen_name']
            else:
                direct_message = self._api.get_direct_message(long_id)
                screen_name_or_short_id = direct_message['sender_screen_name']
        self._job["data"] = self._api.get_user_timeline(screen_name=screen_name_or_short_id, page=page)
        self._job["title"] = 'User @%s Timeline: Page %d' % (screen_name_or_short_id, page)

    def func_me(self, page=1):
        self.func_timeline(page=page)

    def func_fav(self, short_id_or_page=None):
        if not short_id_or_page:
            short_id_or_page = '1'
        if short_id_or_page.isdigit():
            try:
                page = int(short_id_or_page)
            except ValueError:
                return u'Unknown page number: %s.' % short_id_or_page
            self._job["data"] = self._api.get_favorites(page=page)
            self._job["title"] = 'Favourite: Page %d' % page
        else:
            long_id, long_id_type = self._util.restore_short_id(short_id_or_page)
            if long_id_type == db.TYPE_DM:
                raise TypeError('Can not create a direct message as favourite.')
            self._job["data"] = self._api.create_favorite(long_id)
            self._job["title"] = 'Created to favourites:'

    def func_unfav(self, short_id):
        long_id, long_id_type = self._util.restore_short_id(short_id)
        if long_id_type == db.TYPE_DM:
            raise TypeError('Can not delete a direct message as favourite.')
        self._job["data"] = self._api.destroy_favorite(long_id)
        self._job["title"] = 'Deleted from favourites:'

    def func_reply(self, short_id_or_page=None, *content):
        if not content:
            try:
                page = int(short_id_or_page) if short_id_or_page else 1
            except ValueError:
                return u'Unknown page number %s.' % short_id_or_page
            self._job["data"] = self._api.get_mentions(page=page)
            self._job["title"] = 'Mentions: Page %d' % page
        else:
            long_id, long_id_type = self._util.restore_short_id(short_id_or_page)
            if long_id_type == db.TYPE_STATUS:
                status = self._api.get_status(long_id)
                screen_name = status['user']['screen_name']
            else:
                direct_message = self._api.get_direct_message(long_id)
                screen_name = direct_message['sender_screen_name']
                long_id = None
            message = u'@%s %s' % (screen_name, ' '.join(content))
            try:
                self._job["data"] = self._api.post_update(message.encode('UTF8'), long_id)
            except twitter.ForbiddenError, e:
                message_length = twitter.actual_len(message)
                if message_length > twitter.CHARACTER_LIMIT:
                    raise twitter.ForbiddenError('%s\nMaybe too long: %d' % (str(e), message_length))
                else:
                    raise e
            else:
                self._job["no_duplicate"] = True

    def func_replyall(self, short_ids, *content):
        def add_mention_user(screen_name):
            if screen_name not in mention_users and screen_name != self._user['screen_name']:
                mention_users.append(screen_name)

        first_long_id = None
        mention_users = list()
        for short_id in short_ids.split(','):
            long_id, long_id_type = self._util.restore_short_id(short_id)
            try:
                if long_id_type == db.TYPE_STATUS:
                    if first_long_id is None:
                        first_long_id = long_id
                    data = self._api.get_status(long_id)
                    add_mention_user(data['user']['screen_name'])
                else:
                    data = self._api.get_direct_message(long_id)
                    add_mention_user(data['sender_screen_name'])
                for m in re.finditer('@(%s)' % _screen_name_regex, data['text']):
                    add_mention_user(m.group(1))
            except twitter.NotFoundError:
                pass
        if not mention_users:
            raise twitter.NotFoundError('Not found.')
        message = u'%s %s' % (' '.join('@' + x for x in mention_users), ' '.join(content))
        try:
            self._job["data"] = self._api.post_update(message.encode('UTF8'), first_long_id)
        except twitter.ForbiddenError, e:
            message_length = twitter.actual_len(message)
            if message_length > twitter.CHARACTER_LIMIT:
                raise twitter.ForbiddenError('%s\nMaybe too long: %d' % (str(e), message_length))
            else:
                raise e
        else:
            self._job["no_duplicate"] = True

    def func_rt(self, short_id, *content):
        long_id, long_id_type = self._util.restore_short_id(short_id)
        if long_id_type == db.TYPE_DM:
            raise TypeError('Can not retweet a direct message.')
        status = self._api.get_status(long_id)
        if not content and not status['user']['protected']:
            self._job["data"] = self._api.create_retweet(long_id)
            self._job["no_duplicate"] = True
        else:
            user_msg = ' '.join(content)
            if user_msg and ord(user_msg[-1]) < 128:
                user_msg += ' '
            if 'retweeted_status' in status:
                status = status['retweeted_status']
            message = u'%sRT @%s' % (user_msg, status['user']['screen_name'])
            actual_length = twitter.actual_len(message)
            if actual_length > twitter.CHARACTER_LIMIT:
                raise ValueError('Content with length %d is too long to be RT.' % actual_length)
            message_strip_index = twitter.CHARACTER_LIMIT + len(message) - actual_length
            message = '%s: %s' % (message, status['text'])
            for m in re.finditer('@%s' % _screen_name_regex, status['text']):
                m_start = m.start()
                m_end = m.end()
                if m_start <= message_strip_index < m_end:
                    message_strip_index = m_start
                    break
            message_stripped = message[:message_strip_index]
            self._job["data"] = self._api.post_update(message_stripped.encode('UTF8'))
            self._job["no_duplicate"] = True

    def func_del(self, short_id=None):
        if not short_id:
            statuses = self._api.get_user_timeline(screen_name=self._user['screen_name'], count=1)
            if statuses:
                long_id = statuses[0]['id_str']
                long_id_type = db.TYPE_STATUS
            else:
                raise twitter.NotFoundError
        else:
            long_id, long_id_type = self._util.restore_short_id(short_id)
        if long_id_type == db.TYPE_STATUS:
            status = self._api.destroy_status(long_id)
            return u'Status deleted: %s' % self._util.parse_text(status)
        else:
            dm = self._api.destroy_direct_message(long_id)
            return u'Direct message to %s deleted: %s' % (dm['recipient_screen_name'], self._util.parse_text(dm))

    def func_dm(self, screen_name_or_short_id_or_page='', *content):
        if not content:
            try:
                page = int(screen_name_or_short_id_or_page) if screen_name_or_short_id_or_page else 1
            except ValueError:
                return u'Unknown page number: %s.' % screen_name_or_short_id_or_page
            self._job["data"] = self._api.get_direct_messages(page=page)
            self._job["title"] = 'Direct Messages: Page %s' % page
        else:
            if screen_name_or_short_id_or_page and screen_name_or_short_id_or_page[0] == '#':
                long_id, long_id_type = self._util.restore_short_id(screen_name_or_short_id_or_page)
                if long_id_type == db.TYPE_STATUS:
                    status = self._api.get_status(long_id)
                    screen_name = status['user']['screen_name']
                else:
                    direct_message = self._api.get_direct_message(long_id)
                    screen_name = direct_message['sender_screen_name']
            else:
                screen_name = screen_name_or_short_id_or_page
            message = ' '.join(content)
            try:
                self._job["data"] = self._api.post_direct_message(screen_name.encode('UTF8'), message.encode('UTF8'))
            except twitter.ForbiddenError, e:
                message_length = twitter.actual_len(message)
                if message_length > twitter.CHARACTER_LIMIT:
                    raise twitter.ForbiddenError('%s\nMaybe too long: %d' % (str(e), message_length))
                else:
                    raise e
            else:
                self._job["title"] = 'Direct Message sent to %s:' % self._job["data"]['recipient_screen_name']
                self._job["no_duplicate"] = True


    def func_msg(self, short_id_or_long_id):
        long_id, long_id_type = self._util.restore_short_id(short_id_or_long_id)
        long_id_str = str(long_id)
        data = list()
        if long_id_type == db.TYPE_STATUS:
            status = self._api.get_status(long_id)
            data.append(status)
            while status['in_reply_to_status_id'] and len(data) <= config.MAX_CONVERSATION_NUM:
                long_id = status['in_reply_to_status_id']
                status = self._api.get_status(long_id)
                data.append(status)
        else:
            long_id_str = ''
            all_dms = self._api.get_direct_messages(max_id=long_id, count=50)
            if all_dms and all_dms[0]['id_str'] == str(long_id):
                all_dms.extend(self._api.get_sent_direct_messages(max_id=long_id, count=50))
                for dm in sorted(all_dms, key=operator.itemgetter('id'), reverse=True):
                    if dm['recipient_screen_name'] == self._user['screen_name'] or\
                       dm['sender_screen_name'] == self._user['screen_name']:
                        data.append(dm)
                        if len(data) >= config.MAX_CONVERSATION_NUM:
                            break
            else:
                raise twitter.NotFoundError
        self._job["data"] = data
        self._job["title"] = 'Conversation: %s' % long_id_str

    def func_block(self, screen_name):
        if screen_name[0] == '#':
            long_id, long_id_type = self._util.restore_short_id(screen_name)
            if long_id_type == db.TYPE_STATUS:
                status = self._api.get_status(long_id)
                screen_name = status['user']['screen_name']
            else:
                direct_message = self._api.get_direct_message(long_id)
                screen_name = direct_message['sender_screen_name']
        self._api.create_block(screen_name)
        return u'Blocked %s.' % screen_name

    def func_unblock(self, screen_name):
        if screen_name[0] == '#':
            long_id, long_id_type = self._util.restore_short_id(screen_name)
            if long_id_type == db.TYPE_STATUS:
                status = self._api.get_status(long_id)
                screen_name = status['user']['screen_name']
            else:
                direct_message = self._api.get_direct_message(long_id)
                screen_name = direct_message['sender_screen_name']
        self._api.destroy_block(screen_name)
        return u'Delete %s from blocked.' % screen_name

    def func_spam(self, screen_name):
        if screen_name[0] == '#':
            long_id, long_id_type = self._util.restore_short_id(screen_name)
            if long_id_type == db.TYPE_STATUS:
                status = self._api.get_status(long_id)
                screen_name = status['user']['screen_name']
            else:
                direct_message = self._api.get_direct_message(long_id)
                screen_name = direct_message['sender_screen_name']
        self._api.report_spam(screen_name)
        return u'Reported %s as spam.' % screen_name

    def func_follow(self, screen_name):
        if screen_name[0] == '#':
            long_id, long_id_type = self._util.restore_short_id(screen_name)
            if long_id_type == db.TYPE_STATUS:
                status = self._api.get_status(long_id)
                screen_name = status['user']['screen_name']
            else:
                direct_message = self._api.get_direct_message(long_id)
                screen_name = direct_message['sender_screen_name']
        twitter_user = self._api.create_friendship(screen_name)
        if twitter_user.get('protected') and twitter_user.get('follow_request_sent'):
            return u'Have sent follow request to %s' % screen_name
        else:
            return u'Following %s.' % screen_name

    def func_unfollow(self, screen_name):
        if screen_name[0] == '#':
            long_id, long_id_type = self._util.restore_short_id(screen_name)
            if long_id_type == db.TYPE_STATUS:
                status = self._api.get_status(long_id)
                screen_name = status['user']['screen_name']
            else:
                direct_message = self._api.get_direct_message(long_id)
                screen_name = direct_message['sender_screen_name']
        self._api.destroy_friendship(screen_name)
        return u'Unfollowed %s.' % screen_name

    def func_if(self, source_screen_name, target_screen_name=None):
        if target_screen_name is None:
            target_screen_name = self._user['screen_name']
        result = self._api.show_friendship(source_screen_name=source_screen_name, target_screen_name=target_screen_name)
        if result:
            return u'%s is already following %s.' % (source_screen_name, target_screen_name)
        else:
            return u'%s is not following %s yet.' % (source_screen_name, target_screen_name)

    def func_on(self, *args):
        if args:
            for a in args:
                a = a.lower()
                if a == 'home':
                    self._user['timeline'] |= db.MODE_HOME
                elif a == 'mention':
                    self._user['timeline'] |= db.MODE_MENTION
                elif a == 'dm':
                    self._user['timeline'] |= db.MODE_DM
                elif a == 'list':
                    self._user['timeline'] |= db.MODE_LIST
                elif a == 'event':
                    self._user['timeline'] |= db.MODE_EVENT
                elif a == 'track':
                    self._user['timeline'] |= db.MODE_TRACK
            db.update_user(id=self._user['id'], timeline=self._user['timeline'])
            if self._user['timeline']:
                self._xmpp.start_worker(self._bare_jid)
                self._xmpp.start_stream(self._bare_jid)
        modes = []
        if self._user['timeline'] & db.MODE_LIST:
            modes.append('list')
        if self._user['timeline'] & db.MODE_HOME:
            modes.append('home')
        if self._user['timeline'] & db.MODE_MENTION:
            modes.append('mention')
        if self._user['timeline'] & db.MODE_DM:
            modes.append('dm')
        if self._user['timeline'] & db.MODE_EVENT:
            modes.append('event')
        if self._user['timeline'] & db.MODE_TRACK:
            modes.append('track')
        modes_str = ', '.join(modes) if modes else 'nothing'
        return u'You have enabled update for %s.' % modes_str

    def func_off(self, *args):
        if args:
            for a in args:
                a = a.lower()
                if a == 'home':
                    self._user['timeline'] &= ~db.MODE_HOME
                elif a == 'mention':
                    self._user['timeline'] &= ~db.MODE_MENTION
                elif a == 'dm':
                    self._user['timeline'] &= ~db.MODE_DM
                elif a == 'list':
                    self._user['timeline'] &= ~db.MODE_LIST
                elif a == 'event':
                    self._user['timeline'] &= ~db.MODE_EVENT
                elif a == 'track':
                    self._user['timeline'] &= ~db.MODE_TRACK
        else:
            self._user['timeline'] = db.MODE_NONE
        db.update_user(self._user['id'], timeline=self._user['timeline'])
        if self._user['timeline']:
            self._xmpp.stream_threads[self._bare_jid].user_changed()
        else:
            self._xmpp.stop_stream(self._bare_jid)
            self._xmpp.stop_worker(self._bare_jid)
        return self.func_on()

    def func_live(self, list_user_name=None):
        if list_user_name:
            path = list_user_name.split('/', 1)
            if len(path) == 1:
                list_user = self._user['screen_name']
                list_name = path[0]
            else:
                list_user, list_name = path
            response = self._api.get_list(list_user.encode('UTF8'), list_name.encode('UTF8'))
            self._user['list_user'] = response['user']['screen_name']
            self._user['list_name'] = response['slug']
            db.update_user(id=self._user['id'], list_user=self._user['list_user'], list_name=self._user['list_name'],
                list_ids=None, list_ids_last_update=0)
            self._xmpp.stream_threads[self._bare_jid].user_changed()
        if self._user['list_user'] and self._user['list_name']:
            return u'List update is assigned for %s/%s.' % (self._user['list_user'], self._user['list_name'])
        return u'Please specify a list as screen_name/list_name format first.'

    def func_msgtpl(self, *content):
        content = ' '.join(content)
        if content:
            if content.lower() == 'reset':
                content = None
                result = u'You have reset message template to default. Preview:\n%s'
            else:
                result = u'You have updated message template. Preview:\n%s'
            self._user['msg_tpl'] = content
            db.update_user(id=self._user['id'], msg_tpl=content)
            self._util = util.Util(self._user)
            preview = self._util.parse_status(template_test.status)
            result %= preview
        else:
            if self._user['msg_tpl']:
                result = u'Your current message template is:\n%s' % self._user['msg_tpl']
            else:
                result = u'Your current message template is default'
        return result

    def func_datefmt(self, *content):
        content = ' '.join(content)
        if content:
            if content.lower() == 'reset':
                content = None
                result = u'You have reset date format to default.'
            else:
                now = datetime.datetime.now()
                now_str = now.strftime(content.encode('UTF8')).decode('UTF8')
                result = u'You have updated date format as following: %s\nPreview: %s' % (content, now_str)
            db.update_user(id=self._user['id'], date_fmt=content)
        else:
            if self._user['date_fmt']:
                result = u'Your current date format is: %s.' % self._user['date_fmt']
            else:
                result = u'Your current date format is default.'
        return result

    def func_always(self, value=None):
        if value is not None:
            value = value.lower()
            if value in ('true', '1', 'on'):
                value = 1
            elif value in ('false', '0', 'off'):
                value = 0
            else:
                raise TypeError('Only accept true/false, 1/0, on/off.')
            self._user['always'] = value
            db.update_user(id=self._user['id'], always=value)
        if self._user['always']:
            return u'You will always receive updates no matter you are online or not.'
        else:
            return u'You will only receive updates when your status is available.'

    def func_track(self, *values):
        if values:
            self._user['track_words'] = ','.join(values)
            db.update_user(id=self._user['id'], track_words=self._user['track_words'])
            self._xmpp.stream_threads[self._bare_jid].stop()
            self._xmpp.stream_threads[self._bare_jid].join()
            self._xmpp.start_stream(self._bare_jid)
        return u'You are tracking words: %s. (comma seprated)' % self._user['track_words']

    def func_help(self,cmd=None):
        if cmd:
            msg = HELP_MESSAGES.get(cmd)
            if msg:
                return msg
            else:
                return DEFAULT_MESSAGE
        else:
            return DEFAULT_MESSAGE
