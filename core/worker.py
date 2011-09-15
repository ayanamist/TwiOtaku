import db
from lib.util import Util
from lib.decorators import debug

class Job(object):
  def __init__(self, jid, data=None, title=None, reverse=True, allow_duplicate=True, include_reply=False, always=True):
    self.data = data
    self.jid = jid
    self.title = title
    self.reverse = reverse
    self.allow_duplicate = allow_duplicate
    self.include_reply = include_reply
    self.always = always # always send message no matter client is online or not


def worker(xmpp, q):
  @debug('worker')
  def real_worker(item):
    if not isinstance(item, Job):
      raise TypeError(str(item))
    bare_jid = xmpp.getjidbare(item.jid).lower()
    if bare_jid not in xmpp.online_clients and not item.always:
      pass
    else:
      if item.data is None:
        xmpp.send_message(item.jid, item.title)
      else:
        user = db.get_user_from_jid(bare_jid)
        util = Util(user)
        util.allow_duplicate = item.allow_duplicate
        try:
          result = util.parse_data(item.data, reverse=item.reverse)
        except Exception, e:
          if item.always:
            xmpp.send_message(item.jid, unicode(e))
        else:
          if result:
            if item.title:
              msg = u'%s\n%s' % (item.title, ''.join(result) if isinstance(result, list) else result)
              xmpp.send_message(item.jid, msg)
            else:
              for m in result:
                xmpp.send_message(item.jid, m)

  while True:
    item = q.get()
    if item is None:
      q.task_done()
      return
    real_worker(item)
    q.task_done()
