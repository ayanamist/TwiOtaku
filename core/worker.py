import db
from lib.util import Util, StoppableThread
from lib.decorators import debug, threadstop

class Job(object):
  def __init__(self, jid, data=None, title=None, reverse=True, allow_duplicate=True, include_reply=False, always=True):
    self.data = data
    self.jid = jid
    self.title = title
    self.reverse = reverse
    self.allow_duplicate = allow_duplicate
    self.include_reply = include_reply
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
      self.check_stop()
      self.queue.task_done()
      if item is not None:
        self.real_worker(item)

  @debug()
  def real_worker(self, item):
    if not isinstance(item, Job):
      raise TypeError(str(item))
    bare_jid = self.xmpp.getjidbare(item.jid).lower()
    user = db.get_user_from_jid(bare_jid)
    if bare_jid not in self.xmpp.online_clients and not item.always and not user['always']:
      pass
    else:
      if item.data is None:
        self.xmpp.send_message(item.jid, item.title)
      else:
        util = Util(user)
        util.allow_duplicate = item.allow_duplicate
        result = util.parse_data(item.data, reverse=item.reverse)
        if result:
          if item.title:
            msg = u'%s\n%s' % (item.title, '\n'.join(result) if isinstance(result, list) else result)
            self.xmpp.send_message(item.jid, msg)
          else:
            for m in result:
              self.xmpp.send_message(item.jid, m)

  def stop(self):
    super(Worker, self).stop()
    self.queue.put(None)