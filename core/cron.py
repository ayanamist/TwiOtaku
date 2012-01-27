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
import operator
import time
import Queue

import config
import db
from lib import job
from lib import logdecorator
from lib import mythread
from lib import twitter

MAX_IDLE_TIME = 120
CRON_INTERVAL = 60
CRON_BLOCKED_IDS_INTERVAL = 3600
CRON_LIST_IDS_INTERVAL = 3600
CRON_VERIFY_CREDENTIAL_INTERVAL = 3600

logger = logging.getLogger('cron')

class CronStart(mythread.StoppableThread):
    __pool_size = db.get_users_count() // 20 + 1

    def __init__(self, queues):
        super(CronStart, self).__init__()
        self.queues = queues

    @mythread.monitorstop
    def run(self):
        while True:
            last = time.time()
            self.running()
            now = time.time()
            if now - last >= CRON_INTERVAL and self.__pool_size <= db.get_users_count():
                self.__pool_size += 1
            else:
                remain = CRON_INTERVAL - (now - last)
                logger.debug('Sleep %.2f seconds.' % remain)
                self.sleep(remain)
            self.check_stop()


    def running(self):
        cron_queue = Queue.Queue()
        for user in db.get_all_users():
            if user['access_key'] and user['access_secret'] and (user['timeline'] & ~db.MODE_EVENT):
                if time.time() - user['last_update'] > MAX_IDLE_TIME:
                    # if it's a long time since last update, we should abandon these old data.
                    logger.debug('%s: Exceed %s seconds, all results won\'t be shown.' % (user['jid'], MAX_IDLE_TIME))
                    queue = Queue.Queue()
                else:
                    queue = self.queues[user['jid']]
                cron_queue.put((queue, user))
        for _ in range(self.__pool_size):
            t = CronGetTimeline(cron_queue)
            t.start()
        cron_queue.join()


class CronGetTimeline(mythread.StoppableThread):
    def __init__(self, queue):
        super(CronGetTimeline, self).__init__()
        self.__queue = queue

    def run(self):
        @logdecorator.silent
        def fetch_home():
            data = api.get_home_timeline(since_id=user['last_home_id'])
            if data and isinstance(data, list) and isinstance(data[0], twitter.Status):
                db.update_user(jid=user_jid, last_home_id=data[0]['id_str'])
                if not user_timeline & db.MODE_HOME:
                    if user_timeline & db.MODE_MENTION:
                        return [x for x in data if user_at_screen_name in x['text']]
                else:
                    return data

        @logdecorator.silent
        def fetch_mention():
            # TODO: use activity api instead of this one. add event support
            if user_timeline & db.MODE_MENTION:
                data = api.get_mentions(since_id=user['last_mention_id'])
                if data and isinstance(data, list) and isinstance(data[0], twitter.Status):
                    db.update_user(jid=user_jid, last_mention_id=data[0]['id_str'])
                    return data

        @logdecorator.silent
        def fetch_dm():
            if user_timeline & db.MODE_DM:
                data = api.get_direct_messages(since_id=user['last_dm_id'])
                if data and isinstance(data, list) and isinstance(data[0], twitter.DirectMessage):
                    db.update_user(jid=user_jid, last_dm_id=data[0]['id_str'])
                    return data

        @logdecorator.silent
        def fetch_list():
            if user_timeline & db.MODE_LIST:
                if user['list_user'] and user['list_name']:
                    try:
                        data = api.get_list_statuses(screen_name=user['list_user'], slug=user['list_name'],
                            since_id=user['last_list_id'])
                    except twitter.NotFoundError:
                        user['timeline'] &= ~db.MODE_LIST
                        db.update_user(id=user['id'], timeline=user['timeline'])
                        queue.put(job.Job(user['jid'],
                            title='List %s/%s not exists, disable List update.' % (
                                user['list_user'], user['list_name'])))
                    else:
                        if data and isinstance(data, list) and isinstance(data[0], twitter.Status):
                            db.update_user(jid=user_jid, last_list_id=data[0]['id_str'])
                            return data

        @logdecorator.silent
        def fetch_search():
            if user_timeline & db.MODE_TRACK and user['track_words']:
                q = user['track_words'].replace(',', ' ')
                data = api.get_search(q, since_id=user['last_search_id'])
                if data and isinstance(data, list) and isinstance(data[0], twitter.Status):
                    db.update_user(jid=user_jid, last_search_id=data[0]['id_str'])
                    return data

        def all_statuses_add(iterable):
            if not iterable:
                return
            for x in iterable:
                if x['id'] not in all_data_ids and x['user']['screen_name'] != user['screen_name']:
                    all_data_ids.append(x['id'])
                    all_data.append(x)


        while not self.__queue.empty():
            queue, user = self.__queue.get()
            user_jid = user['jid']
            user_timeline = user['timeline']
            db.update_user(id=user['id'], last_update=int(time.time()))

            api = twitter.Api(consumer_key=config.OAUTH_CONSUMER_KEY,
                consumer_secret=config.OAUTH_CONSUMER_SECRET,
                access_token_key=user['access_key'],
                access_token_secret=user['access_secret'])
            user_at_screen_name = '@%s' % user['screen_name']

            data = fetch_dm()
            if data:
                queue.put(job.Job(user_jid, data=data, title='Direct Message:', allow_duplicate=False, always=False,
                    xmpp_command=False))
            all_data = list()
            all_data_ids = list()
            all_statuses_add(fetch_list())
            all_statuses_add(fetch_mention())
            all_statuses_add(fetch_home())
            all_statuses_add(fetch_search())

            for data in all_data:
                if user_at_screen_name in data['text'] and data['user']['screen_name'] != user['screen_name']:
                    retweeted_status = data.get('retweeted_status')
                    if retweeted_status and retweeted_status.get('in_reply_to_status_id_str'):
                        data['retweeted_status']['in_reply_to_status'] = None
                    elif data.get('in_reply_to_status_id_str'):
                        data['in_reply_to_status'] = None

            if all_data:
                queue.put(job.Job(user_jid, data=all_data.sort(key=operator.itemgetter('id')), allow_duplicate=False,
                    always=False, reverse=False, xmpp_command=False))

            self.__queue.task_done()


class CronMisc(mythread.StoppableThread):
    # this cron check credentials, list ids, blocked_ids
    def __init__(self, xmpp):
        super(CronMisc, self).__init__()
        self.__xmpp = xmpp

    @mythread.monitorstop
    def run(self):
        while True:
            last = time.time()
            self.running()
            now = time.time()
            if now - last < CRON_INTERVAL:
                remain = CRON_INTERVAL - (now - last)
                logger.debug('Sleep %.2f seconds.' % remain)
                self.sleep(remain)
            self.check_stop()

    def running(self):
        for user in db.get_all_users():
            if user['access_key'] and user['access_secret']:
                self.__api = twitter.Api(consumer_key=config.OAUTH_CONSUMER_KEY,
                    consumer_secret=config.OAUTH_CONSUMER_SECRET,
                    access_token_key=user['access_key'],
                    access_token_secret=user['access_secret'])
                self.__now = int(time.time())
                self.__thread = self.__xmpp.stream_threads.get(user['jid'])
                self.check_stop()
                if self.verify_credential(user):
                    self.check_stop()
                    self.refresh_blocked_ids(user)
                    self.refresh_list_ids(user)
        self.check_stop()
        self.clean_expired_cache()

    @logdecorator.debug
    def verify_credential(self, user):
        if self.__now - user['last_verified'] > CRON_VERIFY_CREDENTIAL_INTERVAL:
            logger.debug('%s: check credential.' % user['jid'])
            try:
                twitter_user = self.__api.verify_credentials()
            except twitter.UnauthorizedError:
                logger.debug('%s: credential is invalid.' % user['jid'])
                db.update_user(access_key=None, access_secret=None)
                if self.__thread:
                    self.__thread.stop()
                    return False
            else:
                if user['screen_name'] != twitter_user['screen_name']:
                    logger.debug('%s: screen_name has been changed from %s to %s.' %
                                 (user['jid'], user['screen_name'], twitter_user['screen_name']))
                    db.update_user(id=user['id'], screen_name=twitter_user['screen_name'])
                return True
            finally:
                db.update_user(id=user['id'], last_verified=self.__now)
        else:
            return True

    @logdecorator.debug
    def refresh_blocked_ids(self, user):
        if self.__now - user['blocked_ids_last_update'] > CRON_BLOCKED_IDS_INTERVAL:
            logger.debug('%s: refresh blocked ids.' % user['jid'])
            blocked_ids = self.__api.get_blocking_ids(stringify_ids=True)
            if (blocked_ids and user['blocked_ids'] is None) or\
               (set(blocked_ids) - set(user['blocked_ids'].split(',') if user['blocked_ids'] else tuple())):
                db.update_user(id=user['id'], blocked_ids=','.join(blocked_ids), blocked_ids_last_update=self.__now)
                self.__thread.user_changed()
            else:
                db.update_user(id=user['id'], blocked_ids_last_update=self.__now)

    @logdecorator.debug
    def refresh_list_ids(self, user):
        if user['list_user'] and user['list_name'] and self.__now - user[
                                                                    'list_ids_last_update'] > CRON_LIST_IDS_INTERVAL:
            logger.debug('%s: refresh list ids.' % user['jid'])
            cursor = -1
            list_ids = set()
            while cursor:
                self.check_stop()
                result = self.__api.get_list_members(user['list_user'], user['list_name'], cursor=cursor)
                for x in result['users']:
                    list_ids.add(x['id_str'])
                cursor = result['next_cursor']
            user = db.get_user_from_jid(user['jid'])
            if (list_ids and user['list_ids'] is None) or (list_ids ^ set(user['list_ids'].split(','))):
                db.update_user(id=user['id'], list_ids=','.join(list_ids), list_ids_last_update=self.__now)
                self.__thread.user_changed()
            else:
                db.update_user(id=user['id'], list_ids_last_update=self.__now)

    @logdecorator.silent
    def clean_expired_cache(self):
        from_stamp = int(time.time()) - config.MAX_STATUS_CACHE_TIME
        db.purge_old_statuses(from_stamp)