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

import Queue

import db
from lib import logdecorator
from lib import mythread
from lib import util

class Worker(mythread.StoppableThread):
    def __init__(self, xmpp):
        super(Worker, self).__init__()
        self._xmpp = xmpp
        self.job_queue = Queue.Queue()

    @mythread.monitorstop
    def run(self):
        while True:
            item = self.job_queue.get()
            self.job_queue.task_done()
            self.check_stop()
            if item is not None:
                self.running(item)

    @logdecorator.debug
    def running(self, item):
        if isinstance(item, mythread.ThreadStop):
            raise item
        bare_jid = self._xmpp.getjidbare(item["jid"]).lower()
        user = db.get_user_from_jid(bare_jid)
        if self._xmpp.get_presence(bare_jid) or not item.get("not_always") or (user and user['always']):
            data = item.get("data")
            title = item.get("title")
            if data is None:
                if title is not None:
                    self._xmpp.send_message(item["jid"], item["title"])
            else:
                _util = util.Util(user)
                _util.no_duplicate = item.get("no_duplicate")
                result = _util.parse_data(data)
                if result or (not result and title and not item.get("not_command")):
                    if title:
                        msg = u'%s\n%s' % (item["title"], '\n'.join(result) if isinstance(result, list) else result)
                        self._xmpp.send_message(item["jid"], msg)
                    else:
                        for m in result:
                            self._xmpp.send_message(item["jid"], m)
          
