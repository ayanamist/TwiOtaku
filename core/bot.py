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
import logging

import sleekxmpp

import config
import db
from core import command
from core import cron
from core import stream
from core import worker
from lib import logdecorator

logger = logging.getLogger('xmpp')

class XMPPBot(sleekxmpp.ClientXMPP):
    def __init__(self):
        sleekxmpp.ClientXMPP.__init__(self, config.XMPP_USERNAME, config.XMPP_PASSWORD)
        self.worker_threads = dict()
        self.stream_threads = dict()
        self.online_clients = dict() # this save available roster using ref count
        self.auto_authorize = True
        self.auto_subscribe = True
        self.use_ipv6 = False
        self.first_run = True
        self.add_event_handler('session_start', self.on_start)
        self.add_event_handler('message', self.on_message)
        self.add_event_handler('changed_status', self.on_changed_status)
        self._sched = None

    def on_start(self, _):
        self.get_roster()
        if self.first_run:
            self.first_run = False
            self.start_workers()
            self.start_streams()
            self.start_cron()
        self.send_presence()

    @logdecorator.debug
    def on_message(self, msg):
        if msg['type'] == 'chat':
            command.XMPPMessageHandler(self).process(msg)
        elif msg['type'] == 'error':
            if msg['error']['type'] == 'cancel':
                # we can do nothing because if we resend this message, some of them will always fail.
                logger.warning('xmpp failed: %s', str(msg))
            else:
                logger.info('%s -> %s: %s' % (msg['from'], msg['to'], str(msg['error'])))

    def on_changed_status(self, presence):
        bare_jid = self.getjidbare(str(presence['from'])).lower()
        n = self.online_clients.get(bare_jid, 0)
        if presence['type'] in presence.types:
            if presence['type'] == 'available':
                self.online_clients[bare_jid] = n + 1
            else:
                self.online_clients[bare_jid] = n - 1

    def get_presence(self, jid):
        bare_jid = self.getjidbare(jid).lower()
        n = self.online_clients.get(bare_jid, 0)
        if n > 0:
            return True
        else:
            return False

    def send_message(self, mto, mbody, msubject=None, mtype=None, mhtml=None, mfrom=None, mnick=None):
        if mtype is None:
            mtype = 'chat' # we must set this so that messages can be saved into gmail.
        super(XMPPBot, self).send_message(mto, mbody, msubject=msubject, mtype=mtype, mhtml=mhtml, mfrom=mfrom,
            mnick=mnick)

    def add_online_user(self, bare_jid):
        self.start_worker(bare_jid)
        self.start_stream(bare_jid)
        queue = self.worker_threads[bare_jid].job_queue
        user = db.get_user_from_jid(bare_jid)
        self._sched.add_interval_job(functools.partial(cron.cron_timeline, user=user, queue=queue),
            seconds=cron.CRON_INTERVAL)
        self._sched.add_interval_job(functools.partial(cron.cron_block, user=user, xmpp=self),
            seconds=cron.CRON_BLOCKED_IDS_INTERVAL)
        self._sched.add_interval_job(functools.partial(cron.cron_list, user=user, xmpp=self),
            seconds=cron.CRON_LIST_IDS_INTERVAL)


    def start(self, *args, **kwargs):
        if self.connect(('talk.google.com', 5222)):
            self.process(*args, **kwargs)
        else:
            logger.error('Can not connect to server.')

    def start_worker(self, bare_jid):
        w = self.worker_threads.get(bare_jid)
        if w and w.is_alive():
            pass
        else:
            logger.debug('%s: start worker.' % bare_jid)
            w = self.worker_threads[bare_jid] = worker.Worker(self)
            w.start()

    def start_workers(self):
        for user in db.get_all_users():
            if user['access_key'] and user['access_secret']:
                self.start_worker(user['jid'])

    def stop_workers(self):
        logger.info('shutdown workers.')
        for t in self.worker_threads.itervalues():
            t.stop()
        for t in self.worker_threads.itervalues():
            t.join()

    def stop_worker(self, jid):
        t = self.worker_threads.get(jid)
        if t:
            t.stop()
            t.join()
            return True
        return False

    def start_cron(self):
        self._sched = cron.cron_start(self)

    def stop_cron(self):
        if self._sched:
            self._sched.shutdown()

    def start_stream(self, bare_jid):
        t = self.stream_threads.get(bare_jid)
        if t and t.is_alive():
            t.user_changed()
        else:
            logger.debug('%s: start user streaming.' % bare_jid)
            t = stream.StreamThread(self.worker_threads[bare_jid].job_queue, bare_jid)
            t.start()
            self.stream_threads[bare_jid] = t

    def start_streams(self):
        for user in db.get_all_users():
            if user['access_key'] and user['access_secret']:
                self.start_stream(user['jid'])

    def stop_stream(self, jid):
        t = self.stream_threads.get(jid)
        if t:
            t.stop()
            t.join()
            return True
        return False

    def stop_streams(self):
        logger.info('shutdown stream.')
        for t in self.stream_threads.values():
            t.stop()
        for t in self.stream_threads.values():
            t.join()


  