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

import logging
import httplib
import socket
import ssl
import threading

import config
import db
from lib import myjson
from lib import mythread
from lib import twitter
from lib import logdecorator

MAX_CONNECT_TIMEOUT = 5
MAX_DATA_TIMEOUT = 90
WAIT_TIMES = (0, 30, 60, 120, 240)

logger = logging.getLogger('user streaming')
contain = lambda strlist, s: any(x in s for x in strlist)

class Error(Exception):
    pass


class StreamThread(mythread.StoppableThread):
    def __init__(self, queue, bare_jid):
        super(StreamThread, self).__init__()
        self._user_changed = threading.Event()
        self._bare_jid = bare_jid
        self._queue = queue
        self.refresh_user()

    def user_changed(self):
        self.refresh_user()
        self._user_changed.set()

    def is_user_changed(self):
        return self._user_changed.is_set()

    def check_user_changed(self):
        if self.is_user_changed():
            self._user_changed = threading.Event()
            self.user = db.get_user_from_jid(self._bare_jid)

    def refresh_user(self):
        logger.debug('%s: refresh user.' % self._bare_jid)
        self.user = db.get_user_from_jid(self._bare_jid)

        self.blocked_ids = list()
        if self.user['blocked_ids']:
            for blocked_id in self.user['blocked_ids'].split(','):
                try:
                    blocked_id = int(blocked_id)
                except ValueError:
                    pass
                else:
                    self.blocked_ids.append(blocked_id)

        self.list_ids = list()
        if self.user['list_ids']:
            for list_id in self.user['list_ids'].split(','):
                try:
                    list_id = int(list_id)
                except ValueError:
                    pass
                else:
                    self.list_ids.append(list_id)

        self.track_words = [x.lower() for x in self.user['track_words'].split(',')] if self.user['track_words'] else []

        self.user_at_screen_name = '@%s' % self.user['screen_name']
        self.api = twitter.Api(consumer_key=config.OAUTH_CONSUMER_KEY, consumer_secret=config.OAUTH_CONSUMER_SECRET,
            access_token_key=self.user['access_key'], access_token_secret=self.user['access_secret'])

    @mythread.monitorstop
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
        s = ''
        data_len = 0
        failed_count = 0
        while data_len < size:
            self.check_stop()
            try:
                c = fp.read(1)
            except (httplib.HTTPException, socket.error), e:
                failed_count += MAX_CONNECT_TIMEOUT
                if failed_count > MAX_DATA_TIMEOUT:
                    raise Error(str(e))
            else:
                if c:
                    s += c
                    data_len += 1
                else:
                    raise Error
        return s

    def read_line(self, fp):
        s = ''
        while True:
            char = self.read(fp, 1)
            s += char
            if char == '\n':
                return s

    def read_data(self, fp):
        while True:
            # we should not directly use readline method of user_stream_handler,
            # because it has its own buffer which will cause block unintentionally
            length = self.read_line(fp).strip(' \r\n')
            if length:
                return myjson.loads(self.read(fp, int(length)))


    @logdecorator.debug
    def running(self):
        try:
            user_stream_handler = self.api.user_stream(timeout=MAX_CONNECT_TIMEOUT, track=self.user['track_words'])
            logger.debug('%s: connected.' % self.user['jid'])

            self.friend_ids = self.read_data(user_stream_handler)['friends']

            if self.wait_time_now_index:
                self.wait_time_now_index = 0

            while True:
                data = self.read_data(user_stream_handler)
                self.check_user_changed()
                if data:
                    self.process(data)
        except twitter.UnauthorizedError:
            logger.error('User %s OAuth unauthorized, exiting.' % self.user['jid'])
            db.update_user(self.user['id'], access_key=None, access_secret=None)
            self._queue.put(mythread.ThreadStop())
            raise mythread.ThreadStop
        except twitter.EnhanceYourCalmError:
            logger.warn('User %s Streaming connect too often!' % self.user['jid'])
            if not self.wait_time_now_index:
                self.wait_time_now_index = 1
        except (Error, twitter.Error), e:
            logger.warn('connection failed: %s' % str(e))

    @logdecorator.debug
    def process(self, data):
        event = data.get('event')
        job = {"jid": self.user['jid'], "not_always": True, "not_command": True}
        if event:
            title = None
            if self.user['timeline'] & db.MODE_EVENT:
                if event == 'follow':
                    if data['source']['screen_name'] != self.user['screen_name']:
                        title = '@%s is now following @%s.' % (
                            data['source']['screen_name'], data['target']['screen_name'])
                    else:
                        if data['target']['id'] not in self.friend_ids:
                            self.friend_ids.append(data['target']['id'])
                elif event == 'block':
                    if data['target']['id'] not in self.blocked_ids:
                        self.blocked_ids.append(data['target']['id'])
                    if data['target']['id'] in self.friend_ids:
                        self.friend_ids.remove(data['target']['id'])
                    title = '@%s has blocked @%s.' % (data['source']['screen_name'], data['target']['screen_name'])
                elif event == 'unblock':
                    if data['target']['id'] in self.blocked_ids:
                        self.blocked_ids.remove(data['target']['id'])
                    title = '@%s has unblocked @%s.' % (data['source']['screen_name'], data['target']['screen_name'])
                elif event == 'list_member_added':
                    if data['target']['id'] not in self.list_ids:
                        self.list_ids.append(data['target']['id'])
                elif event == 'list_member_removed':
                    if data['target']['id'] in self.list_ids:
                        self.list_ids.remove(data['target']['id'])
                elif event in ('favorite', 'unfavorite'):
                    if data['source']['screen_name'] != self.user['screen_name']:
                        title = '%s %sd %s\'s tweet:' % (
                            data['source']['screen_name'], data['event'], data['target']['screen_name'])
                        data['target_object']['user'] = data['target']
                        data = twitter.Status(data['target_object'])
                elif event == 'list_created':
                    pass
                elif event == 'list_updated':
                    pass
                elif event == 'list_destroyed':
                    pass
                elif event == 'list_user_subscribed':
                    pass
                elif event == 'list_user_unsubscribed':
                    pass
                elif event == 'user_update':
                    pass
                elif event == 'access_revoked':
                    pass
                else:
                    logger.error('Unmatched event %s.' % event)
            if title:
                job["title"] = title
                if isinstance(data, twitter.Status):
                    job["data"] = data
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
                if 'user' in data:
                    if data['user']['id'] in self.blocked_ids or\
                       ('retweeted_status' in data and data['retweeted_status']['user']['id'] in self.blocked_ids) or\
                       data['user']['screen_name'] == self.user['screen_name']:
                        data = None
                    else:
                        data = twitter.Status(data)
                        if (self.user['timeline'] & db.MODE_HOME and data['user']['id'] in self.friend_ids) or\
                           (self.user['timeline'] & db.MODE_MENTION and self.user_at_screen_name in data['text']) or\
                           (self.user['timeline'] & db.MODE_LIST and data['user']['id'] in self.list_ids) or\
                           (self.user['timeline'] & db.MODE_TRACK and contain(self.track_words, data['text'].lower())):
                            if "in_reply_to_status_id_str" in data:
                                data["in_reply_to_status"] = None
                        else:
                            data = None
                else:
                    logger.warn('Unknown stream: %s' % str(data))
                    data = None
            if data:
                job["title"] = title
                job["data"] = data
        self._queue.put(job)
