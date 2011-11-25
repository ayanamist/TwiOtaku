# Copyright 2011 ayanamist aka gh05tw01f
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

import db
from lib.data import Util
from lib.logger import debug
from lib.thread import StoppableThread, threadstop

class Job(object):
  def __init__(self, jid, data=None, title=None, reverse=True, allow_duplicate=True, xmpp_command=True, always=True):
    self.data = data
    self.jid = jid
    self.title = title
    self.reverse = reverse
    self.allow_duplicate = allow_duplicate
    self.xmpp_command = xmpp_command
    self.always = always # always send message no matter client is online or not


class Worker(StoppableThread):
  def __init__(self, xmpp, queue):
    super(Worker, self).__init__()
    self.xmpp = xmpp
    self.queue = queue

  @threadstop
  def run(self):
    while True:
      item = self.queue.get()
      self.queue.task_done()
      self.check_stop()
      if item is not None:
        self.running(item)

  @debug
  def running(self, item):
    if not isinstance(item, Job):
      raise TypeError(str(item))
    bare_jid = self.xmpp.getjidbare(item.jid).lower()
    user = db.get_user_from_jid(bare_jid)
    if self.xmpp.get_presence(bare_jid) or item.always or user['always']:
      if item.data is None:
        self.xmpp.send_message(item.jid, item.title)
      else:
        util = Util(user)
        util.allow_duplicate = item.allow_duplicate
        result = util.parse_data(item.data, reverse=item.reverse)
        if result or (not result and item.title and item.xmpp_command):
          if item.title:
            msg = u'%s\n%s' % (item.title, '\n'.join(result) if type(result) is list else result)
            self.xmpp.send_message(item.jid, msg)
          else:
            for m in result:
              self.xmpp.send_message(item.jid, m)
          
