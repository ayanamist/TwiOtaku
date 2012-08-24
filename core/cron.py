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

import functools
import operator
import time

import apscheduler.scheduler

import config
import db
from lib import logdecorator
from lib import twitter

MAX_IDLE_TIME = 120
CRON_INTERVAL = 60
CRON_BLOCKED_IDS_INTERVAL = 3600
CRON_LIST_IDS_INTERVAL = 3600


def cron_start(xmpp):
    sched = apscheduler.scheduler.Scheduler()
    for user in db.get_all_users():
        if user['access_key'] and user['access_secret'] and (user['timeline'] & ~db.MODE_EVENT):
            queue = xmpp.worker_threads[user['jid']].job_queue
            sched.add_interval_job(functools.partial(cron_timeline, user=user, queue=queue), seconds=CRON_INTERVAL)
            sched.add_interval_job(functools.partial(cron_block, user=user, xmpp=xmpp),
                seconds=CRON_BLOCKED_IDS_INTERVAL)
            sched.add_interval_job(functools.partial(cron_list, user=user, xmpp=xmpp), seconds=CRON_LIST_IDS_INTERVAL)
    sched.start()
    return sched


def cron_timeline(user, queue):
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
        if user_timeline & db.MODE_LIST and user['list_user'] and user['list_name']:
            try:
                data = api.get_list_statuses(screen_name=user['list_user'], slug=user['list_name'],
                    since_id=user['last_list_id'])
            except twitter.NotFoundError:
                user['timeline'] &= ~db.MODE_LIST
                db.update_user(id=user['id'], timeline=user['timeline'])
                queue.put({"jid": user['jid'], "title": 'List %s/%s not exists, disable List update.' % (
                    user['list_user'], user['list_name'])})
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
        queue.put({"jid": user_jid, "data": data, "title": 'Direct Message:', "no_duplicate": True,
                   "not_always": True, "not_command": True})

    all_data = list()
    all_data_ids = list()
    all_statuses_add(fetch_list())
    all_statuses_add(fetch_mention())
    all_statuses_add(fetch_home())
    all_statuses_add(fetch_search())

    for status in all_data:
        if "in_reply_to_status_id_str" in status:
            status["in_reply_to_status"] = None

    if all_data:
        queue.put({"jid": user_jid, "data": all_data.sort(key=operator.itemgetter('id')), "no_duplicate": True,
                   "not_always": True, "not_command": True})


def cron_block(user, xmpp):
    api = twitter.Api(consumer_key=config.OAUTH_CONSUMER_KEY,
        consumer_secret=config.OAUTH_CONSUMER_SECRET,
        access_token_key=user['access_key'],
        access_token_secret=user['access_secret'])
    thread = xmpp.stream_threads.get(user['jid'])
    try:
        blocked_ids = api.get_blocking_ids(stringify_ids=True)
    except twitter.UnauthorizedError:
        db.update_user(user['id'], access_key=None, access_secret=None)
        if thread:
            thread.stop()
    else:
        if (blocked_ids and user['blocked_ids'] is None) or\
           (set(blocked_ids) - set(user['blocked_ids'].split(',') if user['blocked_ids'] else tuple())):
            db.update_user(id=user['id'], blocked_ids=','.join(blocked_ids))
            thread.user_changed()
        else:
            db.update_user(id=user['id'])


def cron_list(user, xmpp):
    if user['list_user'] and user['list_name']:
        api = twitter.Api(consumer_key=config.OAUTH_CONSUMER_KEY,
            consumer_secret=config.OAUTH_CONSUMER_SECRET,
            access_token_key=user['access_key'],
            access_token_secret=user['access_secret'])
        thread = xmpp.stream_threads.get(user['jid'])
        cursor = -1
        list_ids = set()
        while cursor:
            try:
                result = api.get_list_members(user['list_user'], user['list_name'], cursor=cursor)
            except twitter.NotFoundError:
                break
            for x in result['users']:
                list_ids.add(x['id_str'])
            cursor = result['next_cursor']
        user = db.get_user_from_jid(user['jid'])
        if (list_ids and user['list_ids'] is None) or (list_ids ^ set((user['list_ids'] or '').split(','))):
            db.update_user(id=user['id'], list_ids=','.join(list_ids))
            thread.user_changed()
