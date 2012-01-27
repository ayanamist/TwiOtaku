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
import Queue

import config
import db
from lib import job
from lib import logdecorator
from lib import oauth
from lib import twitter
from lib import util
from misc import template_test

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

_screen_name_regex = r'[a-zA-Z0-9_]+'

class XMPPMessageHandler(object):
    def __init__(self, xmpp):
        self.__xmpp = xmpp

    @logdecorator.debug
    def process(self, msg):
        self.__jid = str(msg['from'])
        self.__bare_jid = self.__xmpp.getjidbare(self.__jid).lower()
        self.__queue = self.__xmpp.worker_queues.get(self.__bare_jid, Queue.Queue())
        self.__user = db.get_user_from_jid(self.__bare_jid)
        if self.__user:
            self.__util = util.Util(self.__user)
            self.__api = twitter.Api(consumer_key=config.OAUTH_CONSUMER_KEY,
                consumer_secret=config.OAUTH_CONSUMER_SECRET,
                access_token_key=self.__user.get('access_key'),
                access_token_secret=self.__user.get('access_secret'))
        try:
            result = self.parse_command(msg['body'])
        except Exception, e:
            result = u'%s: %s' % (e.__class__.__name__, unicode(e))
        if result:
            self.__xmpp.send_message(msg['from'], result)

    def parse_command(self, cmd):
        if cmd[0] == '-' or cmd[0] == ' ':
            args = cmd[1:].lstrip().split(' ')
            if args[0] in SHORT_COMMANDS:
                args[0] = SHORT_COMMANDS[args[0]]
            if not self.__user and args[0] != 'invite':
                return
            func_name = 'func_' + args[0]
            func = getattr(self, func_name)
            return func(*args[1:])
        else:
            if not self.__user:
                return
            status = self.__api.post_update(cmd.encode('UTF8'))
            self.__queue.put(job.Job(self.__jid, data=status, allow_duplicate=False))

    def func_oauth(self):
        consumer = oauth.Consumer(config.OAUTH_CONSUMER_KEY, config.OAUTH_CONSUMER_SECRET)
        client = oauth.Client(consumer)
        resp = client.request(twitter.REQUEST_TOKEN_URL)
        if resp:
            request_token = dict(urlparse.parse_qsl(resp))
            oauth_token = request_token['oauth_token']
            redirect_url = "%s?oauth_token=%s" % (twitter.AUTHORIZATION_URL, oauth_token)
            db.update_user(self.__user['id'], access_key=oauth_token, access_secret=None)
            return u'Please visit below url to get PIN code:\n%s\nthen you should use "-bind PIN" command to actually bind your Twitter.' % redirect_url
        else:
            return u'Network error.'

    def func_bind(self, pin_code):
        if self.__user['access_key']:
            token = oauth.Token(self.__user['access_key'])
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
                db.update_user(self.__user['id'], access_key=access_token['oauth_token'],
                    access_secret=access_token['oauth_token_secret'],
                    screen_name=access_token['screen_name'])
                self.__xmpp.add_online_user(self.__bare_jid)
                return u'Associated you with @%s.' % access_token['screen_name']
        return u'Invalid PIN code.'

    def func_invite(self, invite_code=None):
        def generate_invite_code():
            valid_chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789'
            return ''.join(random.choice(valid_chars) for _ in xrange(8))

        expire_days = 3

        if invite_code:
            invite_code, create_time = db.get_invite_code(invite_code)
            if invite_code and create_time and create_time + expire_days * 24 * 3600 > time.time():
                db.delete_invite_code(invite_code)
                if not self.__user:
                    db.add_user(self.__bare_jid)
                return u'Your account %s has been added, enjoy using TwiOtaku.' % self.__bare_jid
            else:
                return u'Invite code is invalid or expired.'
        elif self.__bare_jid in config.ADMIN_USERS:
            invite_code = generate_invite_code()
            create_time = int(time.time())
            db.add_invite_code(invite_code, create_time)
            return u'You have generated a new invite code which is available for %d days: %s' % (
                expire_days, invite_code)

    def func_user(self, short_id_or_screen_name=None):
        if short_id_or_screen_name and short_id_or_screen_name[0] == '#':
            long_id, long_id_type = self.__util.restore_short_id(short_id_or_screen_name)
            if long_id_type == db.TYPE_STATUS:
                status = self.__api.get_status(long_id)
                twitter_user = status['user']
            else:
                direct_message = self.__api.get_direct_message(long_id)
                twitter_user = direct_message['sender']
        else:
            if short_id_or_screen_name is None:
                short_id_or_screen_name = self.__user['screen_name']
            twitter_user = self.__api.get_user(screen_name=short_id_or_screen_name)
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
        texts.append(''.join(follow_str))
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
            lists = self.__api.get_all_lists()
            texts = list()
            for l in lists:
                texts.append(u'%s %s: %s' %
                             (l['slug'] if l['user']['screen_name'] == self.__user['screen_name'] else u'%s/%s' % (
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
                list_user = self.__user['screen_name']
                list_name = path[0]
            else:
                list_user, list_name = path
            statuses = self.__api.get_list_statuses(list_user, list_name, page=page)
            self.__queue.put(job.Job(self.__jid, data=statuses,
                title='List %s Statuses: Page %d' % (list_user_name, page)))
        else:
            list_command = args[0].lower()
            if list_command == 'info' and length == 2:
                list_user_name = args[1]
                path = list_user_name.split('/', 1)
                if len(path) == 1:
                    list_user = self.__user['screen_name']
                    list_name = path[0]
                else:
                    list_user, list_name = path
                l = self.__api.get_list(screen_name=list_user, slug=list_name)
                texts = (u'List %s/%s %s: %s' %
                         (l['user']['screen_name'], l['slug'], l['mode'],
                          u'You are following.' if l['following'] else u''),
                         u'Member Count: %d' % l['member_count'], u'Subscriber Count: %d' % l['subscriber_count'],
                         u'Description: %s' % l['description'])
                return '\n'.join(texts)
            elif list_command in ('add', 'del') and 2 <= length <= 3:
                if length == 2:
                    if list_command == 'add':
                        self.__api.create_list(args[1], public=False)
                        return u'Created private list %s.' % args[1]
                    else:
                        self.__api.destroy_list(self.__user['screen_name'], args[1])
                        return u'Deleted list %s.' % args[1]
                else:
                    if list_command == 'add':
                        self.__api.create_list_member(self.__user['screen_name'], args[1], args[2])
                        result = u'Added %s to list %s.' % (args[2], args[1])
                    else:
                        self.__api.destroy_list_member(self.__user['screen_name'], args[1], args[2])
                        result = u'Removed %s from list %s.' % (args[2], args[1])
                    if self.__user['screen_name'] == self.__user['list_user'] and args[1] == self.__user['list_name']:
                        db.update_user(id=self.__user['id'], list_ids_last_update=0)
                        self.__xmpp.stream_threads[self.__bare_jid].user_changed()
                    return result
            else:
                raise TypeError('Not supported list command.')

    def func_home(self, page=1):
        try:
            page = int(page)
        except ValueError:
            return u'Unknown page number: %s.' % page
        statuses = self.__api.get_home_timeline(page=page)
        self.__queue.put(job.Job(self.__jid, data=statuses, title='Home Timeline: Page %d' % page))

    def func_timeline(self, screen_name_or_short_id=None, page=1):
        try:
            page = int(page)
        except ValueError:
            return u'Unknown page number: %s.' % page
        if not screen_name_or_short_id:
            screen_name_or_short_id = self.__user['screen_name']
        elif screen_name_or_short_id[0] == '#':
            long_id, long_id_type = self.__util.restore_short_id(screen_name_or_short_id)
            if long_id_type == db.TYPE_STATUS:
                status = self.__api.get_status(long_id)
                screen_name_or_short_id = status['user']['screen_name']
            else:
                direct_message = self.__api.get_direct_message(long_id)
                screen_name_or_short_id = direct_message['sender_screen_name']
        statuses = self.__api.get_user_timeline(screen_name=screen_name_or_short_id, page=page)
        self.__queue.put(
            job.Job(self.__jid, data=statuses, title='User @%s Timeline: Page %d' % (screen_name_or_short_id, page)))

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
            statuses = self.__api.get_favorites(page=page)
            self.__queue.put(job.Job(self.__jid, data=statuses, title='Favourite: Page %d' % page))
        else:
            long_id, long_id_type = self.__util.restore_short_id(short_id_or_page)
            if long_id_type == db.TYPE_DM:
                raise TypeError('Can not create a direct message as favourite.')
            status = self.__api.create_favorite(long_id)
            self.__queue.put(job.Job(self.__jid, data=status, title='Created to favourites:'))

    def func_unfav(self, short_id):
        long_id, long_id_type = self.__util.restore_short_id(short_id)
        if long_id_type == db.TYPE_DM:
            raise TypeError('Can not delete a direct message as favourite.')
        status = self.__api.destroy_favorite(long_id)
        self.__queue.put(job.Job(self.__jid, data=status, title='Deleted from favourites:'))

    def func_reply(self, short_id_or_page=None, *content):
        if not content:
            try:
                page = int(short_id_or_page) if short_id_or_page else 1
            except ValueError:
                return u'Unknown page number %s.' % short_id_or_page
            statuses = self.__api.get_mentions(page=page)
            self.__queue.put(job.Job(self.__jid, data=statuses, title='Mentions: Page %d' % page))
        else:
            long_id, long_id_type = self.__util.restore_short_id(short_id_or_page)
            if long_id_type == db.TYPE_STATUS:
                status = self.__api.get_status(long_id)
                screen_name = status['user']['screen_name']
            else:
                direct_message = self.__api.get_direct_message(long_id)
                screen_name = direct_message['sender_screen_name']
                long_id = None
            message = u'@%s %s' % (screen_name, ' '.join(content))
            status = self.__api.post_update(message.encode('UTF8'), long_id)
            self.__queue.put(job.Job(self.__jid, data=status, allow_duplicate=False))

    def func_replyall(self, short_ids, *content):
        def add_mention_user(screen_name):
            if screen_name not in mention_users and screen_name != self.__user['screen_name']:
                mention_users.append(screen_name)

        first_long_id = None
        mention_users = list()
        for short_id in short_ids.split(','):
            long_id, long_id_type = self.__util.restore_short_id(short_id)
            try:
                if long_id_type == db.TYPE_STATUS:
                    if first_long_id is None:
                        first_long_id = long_id
                    data = self.__api.get_status(long_id)
                    add_mention_user(data['user']['screen_name'])
                else:
                    data = self.__api.get_direct_message(long_id)
                    add_mention_user(data['sender_screen_name'])
                for m in re.finditer('@(%s)' % _screen_name_regex, data['text']):
                    add_mention_user(m.group(1))
            except twitter.NotFoundError:
                pass
        if not mention_users:
            raise twitter.NotFoundError('Not found.')
        message = u'%s %s' % (' '.join('@' + x for x in mention_users), ' '.join(content))
        status = self.__api.post_update(message.encode('UTF8'), first_long_id)
        self.__queue.put(job.Job(self.__jid, data=status, allow_duplicate=False))

    def func_rt(self, short_id, *content):
        long_id, long_id_type = self.__util.restore_short_id(short_id)
        if long_id_type == db.TYPE_DM:
            raise TypeError('Can not retweet a direct message.')
        status = self.__api.get_status(long_id)
        if not content and not status['user']['protected']:
            status = self.__api.create_retweet(long_id)
            self.__queue.put(job.Job(self.__jid, data=status, allow_duplicate=False))
        else:
            user_msg = ' '.join(content)
            if user_msg and ord(user_msg[-1]) < 128:
                user_msg += ' '
            if 'retweeted_status' in status:
                status = status['retweeted_status']
            message = u'%sRT @%s' % (user_msg, status['user']['screen_name'])
            if len(message) > twitter.CHARACTER_LIMIT:
                raise ValueError('Content is too long to be RT.')
            message = '%s: %s' % (message, status['text'])
            message_stripped = ''
            for m in re.finditer('@%s' % _screen_name_regex, status['text']):
                m_start = m.start()
                m_end = m.end()
                if twitter.CHARACTER_LIMIT < m_end >= m_start:
                    message_stripped = message[:m_start]
                    break
            if not message_stripped:
                message_stripped = message[:140]
            status = self.__api.post_update(message_stripped.encode('UTF8'))
            self.__queue.put(job.Job(self.__jid, data=status, allow_duplicate=False))

    def func_del(self, short_id=None):
        if not short_id:
            statuses = self.__api.get_user_timeline(screen_name=self.__user['screen_name'], count=1)
            if statuses:
                long_id = statuses[0]['id_str']
                long_id_type = db.TYPE_STATUS
            else:
                raise twitter.NotFoundError
        else:
            long_id, long_id_type = self.__util.restore_short_id(short_id)
        if long_id_type == db.TYPE_STATUS:
            status = self.__api.destroy_status(long_id)
            return u'Status deleted: %s' % self.__util.parse_text(status)
        else:
            dm = self.__api.destroy_direct_message(long_id)
            return u'Direct message to %s deleted: %s' % (dm['recipient_screen_name'], self.__util.parse_text(dm))

    def func_dm(self, screen_name_or_short_id_or_page='', *content):
        if not content:
            try:
                page = int(screen_name_or_short_id_or_page) if screen_name_or_short_id_or_page else 1
            except ValueError:
                return u'Unknown page number: %s.' % screen_name_or_short_id_or_page
            statuses = self.__api.get_direct_messages(page=page)
            self.__queue.put(job.Job(self.__jid, data=statuses, title='Direct Messages: Page %s' % page))
        else:
            if screen_name_or_short_id_or_page and screen_name_or_short_id_or_page[0] == '#':
                long_id, long_id_type = self.__util.restore_short_id(screen_name_or_short_id_or_page)
                if long_id_type == db.TYPE_STATUS:
                    status = self.__api.get_status(long_id)
                    screen_name = status['user']['screen_name']
                else:
                    direct_message = self.__api.get_direct_message(long_id)
                    screen_name = direct_message['sender_screen_name']
            else:
                screen_name = screen_name_or_short_id_or_page
            message = ' '.join(content)
            dm = self.__api.post_direct_message(screen_name.encode('UTF8'), message.encode('UTF8'))
            self.__queue.put(job.Job(self.__jid,
                title='Direct Message sent to %s:' % screen_name, data=dm, allow_duplicate=False))


    def func_msg(self, short_id_or_long_id):
        long_id, long_id_type = self.__util.restore_short_id(short_id_or_long_id)
        long_id_str = str(long_id)
        data = list()
        if long_id_type == db.TYPE_STATUS:
            origin_status = self.__api.get_status(long_id)
            related_result = self.__api.get_related_results(long_id)
            if related_result:
                last_conversation_role = 'Ancestor' # possible value: Ancestor, Descendant, Fork
                related_result = related_result[0]['results']
                for result in related_result:
                    if result['kind'] == 'Tweet':
                        if result['annotations']['ConversationRole'] != last_conversation_role:
                            data.append(origin_status)
                            origin_status = None
                            last_conversation_role = result['annotations']['ConversationRole']
                        data.append(result['value'])
            if origin_status:
                data.append(origin_status)
            first_short = data[0]['id_str'] == long_id
            while len(data) <= config.MAX_CONVERSATION_NUM or first_short:
                first_short = False
                status = data[0]
                if status['in_reply_to_status_id_str']:
                    long_id = status['in_reply_to_status_id_str']
                    try:
                        status = self.__api.get_status(long_id)
                    except twitter.Error:
                        break
                else:
                    break
                if 'retweeted_status' in status:
                    data.insert(0, status['retweeted_status'])
                else:
                    data.insert(0, status)
        else:
            long_id_str = ''
            all_dms = self.__api.get_direct_messages(max_id=long_id, count=50)
            if all_dms and all_dms[0]['id_str'] == str(long_id):
                all_dms.extend(self.__api.get_sent_direct_messages(max_id=long_id, count=50))
                for dm in sorted(all_dms, key=operator.itemgetter('id'), reverse=True):
                    if dm['recipient_screen_name'] == self.__user['screen_name'] or\
                       dm['sender_screen_name'] == self.__user['screen_name']:
                        data.insert(0, dm)
                        if len(data) >= config.MAX_CONVERSATION_NUM:
                            break
            else:
                raise twitter.NotFoundError
        self.__queue.put(job.Job(self.__jid, data=data, title='Conversation: %s' % long_id_str, reverse=False))

    def func_block(self, screen_name):
        if screen_name[0] == '#':
            long_id, long_id_type = self.__util.restore_short_id(screen_name)
            if long_id_type == db.TYPE_STATUS:
                status = self.__api.get_status(long_id)
                screen_name = status['user']['screen_name']
            else:
                direct_message = self.__api.get_direct_message(long_id)
                screen_name = direct_message['sender_screen_name']
        self.__api.create_block(screen_name)
        return u'Blocked %s.' % screen_name

    def func_unblock(self, screen_name):
        if screen_name[0] == '#':
            long_id, long_id_type = self.__util.restore_short_id(screen_name)
            if long_id_type == db.TYPE_STATUS:
                status = self.__api.get_status(long_id)
                screen_name = status['user']['screen_name']
            else:
                direct_message = self.__api.get_direct_message(long_id)
                screen_name = direct_message['sender_screen_name']
        self.__api.destroy_block(screen_name)
        return u'Delete %s from blocked.' % screen_name

    def func_spam(self, screen_name):
        if screen_name[0] == '#':
            long_id, long_id_type = self.__util.restore_short_id(screen_name)
            if long_id_type == db.TYPE_STATUS:
                status = self.__api.get_status(long_id)
                screen_name = status['user']['screen_name']
            else:
                direct_message = self.__api.get_direct_message(long_id)
                screen_name = direct_message['sender_screen_name']
        self.__api.report_spam(screen_name)
        return u'Reported %s as spam.' % screen_name

    def func_follow(self, screen_name):
        if screen_name[0] == '#':
            long_id, long_id_type = self.__util.restore_short_id(screen_name)
            if long_id_type == db.TYPE_STATUS:
                status = self.__api.get_status(long_id)
                screen_name = status['user']['screen_name']
            else:
                direct_message = self.__api.get_direct_message(long_id)
                screen_name = direct_message['sender_screen_name']
        twitter_user = self.__api.create_friendship(screen_name)
        if twitter_user.get('protected') and twitter_user.get('follow_request_sent'):
            return u'Have sent follow request to %s' % screen_name
        else:
            return u'Following %s.' % screen_name

    def func_unfollow(self, screen_name):
        if screen_name[0] == '#':
            long_id, long_id_type = self.__util.restore_short_id(screen_name)
            if long_id_type == db.TYPE_STATUS:
                status = self.__api.get_status(long_id)
                screen_name = status['user']['screen_name']
            else:
                direct_message = self.__api.get_direct_message(long_id)
                screen_name = direct_message['sender_screen_name']
        self.__api.destroy_friendship(screen_name)
        return u'Unfollowed %s.' % screen_name

    def func_if(self, user_a, user_b=None):
        if user_b is None:
            user_b = self.__user['screen_name']
        result = self.__api.exists_friendship(user_a=user_a, user_b=user_b)
        if result:
            return u'%s is already following %s.' % (user_a, user_b)
        else:
            return u'%s is not following %s yet.' % (user_a, user_b)

    def func_on(self, *args):
        if args:
            for a in args:
                a = a.lower()
                if a == 'home':
                    self.__user['timeline'] |= db.MODE_HOME
                elif a == 'mention':
                    self.__user['timeline'] |= db.MODE_MENTION
                elif a == 'dm':
                    self.__user['timeline'] |= db.MODE_DM
                elif a == 'list':
                    self.__user['timeline'] |= db.MODE_LIST
                elif a == 'event':
                    self.__user['timeline'] |= db.MODE_EVENT
                elif a == 'track':
                    self.__user['timeline'] |= db.MODE_TRACK
            db.update_user(id=self.__user['id'], timeline=self.__user['timeline'])
            if self.__user['timeline']:
                self.__xmpp.start_worker(self.__bare_jid)
                self.__xmpp.start_stream(self.__bare_jid)
        modes = []
        if self.__user['timeline'] & db.MODE_LIST:
            modes.append('list')
        if self.__user['timeline'] & db.MODE_HOME:
            modes.append('home')
        if self.__user['timeline'] & db.MODE_MENTION:
            modes.append('mention')
        if self.__user['timeline'] & db.MODE_DM:
            modes.append('dm')
        if self.__user['timeline'] & db.MODE_EVENT:
            modes.append('event')
        if self.__user['timeline'] & db.MODE_TRACK:
            modes.append('track')
        modes_str = ', '.join(modes) if modes else 'nothing'
        return u'You have enabled update for %s.' % modes_str

    def func_off(self, *args):
        if args:
            for a in args:
                a = a.lower()
                if a == 'home':
                    self.__user['timeline'] &= ~db.MODE_HOME
                elif a == 'mention':
                    self.__user['timeline'] &= ~db.MODE_MENTION
                elif a == 'dm':
                    self.__user['timeline'] &= ~db.MODE_DM
                elif a == 'list':
                    self.__user['timeline'] &= ~db.MODE_LIST
                elif a == 'event':
                    self.__user['timeline'] &= ~db.MODE_EVENT
                elif a == 'track':
                    self.__user['timeline'] &= ~db.MODE_TRACK
        else:
            self.__user['timeline'] = db.MODE_NONE
        db.update_user(self.__user['id'], timeline=self.__user['timeline'])
        if self.__user['timeline']:
            self.__xmpp.stream_threads[self.__bare_jid].user_changed()
        else:
            self.__xmpp.stop_stream(self.__bare_jid)
            self.__xmpp.stop_worker(self.__bare_jid)
        return self.func_on()

    def func_live(self, list_user_name=None):
        if list_user_name:
            path = list_user_name.split('/', 1)
            if len(path) == 1:
                list_user = self.__user['screen_name']
                list_name = path[0]
            else:
                list_user, list_name = path
            response = self.__api.get_list(list_user.encode('UTF8'), list_name.encode('UTF8'))
            self.__user['list_user'] = response['user']['screen_name']
            self.__user['list_name'] = response['slug']
            db.update_user(id=self.__user['id'], list_user=self.__user['list_user'], list_name=self.__user['list_name'],
                list_ids=None, list_ids_last_update=0)
            self.__xmpp.stream_threads[self.__bare_jid].user_changed()
        if self.__user['list_user'] and self.__user['list_name']:
            return u'List update is assigned for %s/%s.' % (self.__user['list_user'], self.__user['list_name'])
        return u'Please specify a list as screen_name/list_name format first.'

    def func_msgtpl(self, *content):
        content = ' '.join(content)
        if content:
            if content.lower() == 'reset':
                content = None
                result = u'You have reset message template to default. Preview:\n%s'
            else:
                result = u'You have updated message template. Preview:\n%s'
            self.__user['msg_tpl'] = content
            db.update_user(id=self.__user['id'], msg_tpl=content)
            self.__util = util.Util(self.__user)
            preview = self.__util.parse_status(template_test.status)
            result %= preview
        else:
            if self.__user['msg_tpl']:
                result = u'Your current message template is:\n%s' % self.__user['msg_tpl']
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
            db.update_user(id=self.__user['id'], date_fmt=content)
        else:
            if self.__user['date_fmt']:
                result = u'Your current date format is: %s.' % self.__user['date_fmt']
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
            self.__user['always'] = value
            db.update_user(id=self.__user['id'], always=value)
        if self.__user['always']:
            return u'You will always receive updates no matter you are online or not.'
        else:
            return u'You will only receive updates when your status is available.'

    def func_track(self, *values):
        if values:
            self.__user['track_words'] = ','.join(values)
            db.update_user(id=self.__user['id'], track_words=self.__user['track_words'])
            self.__xmpp.stream_threads[self.__bare_jid].stop()
            self.__xmpp.stream_threads[self.__bare_jid].join()
            self.__xmpp.start_stream(self.__bare_jid)
        return u'You are tracking words: %s. (comma seprated)' % self.__user['track_words']

    def func_help(self):
        return u'Please refer to following url to get more help.\nhttp://code.google.com/p/twiotaku/wiki/CommandsReferrence'