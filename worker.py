import traceback
import logging
from StringIO import StringIO

import db
from util import Util

class Job(object):
  def __init__(self, data, jid, title=None, reverse=True, allow_duplicate=True, include_reply=False):
    self.data = data
    self.jid = jid
    self.title = title
    self.reverse = reverse
    self.allow_duplicate = allow_duplicate
    self.include_reply = include_reply

  def __str__(self):
    return 'data=%s\njid=%s,title=%s,reverse=%s,allow_duplicate=%s,include_reply=%s' % \
           (str(self.data), str(self.jid), str(self.title), str(self.reverse), str(self.allow_duplicate), str(self.include_reply))


def worker(xmpp, q):
  while True:
    item = q.get()
    if item is None:
      q.task_done()
      return
    try:
      if not isinstance(item, Job):
        raise TypeError(str(item))
      bare_jid = item.jid.split('/')[0].lower()
      user = db.get_user_from_jid(bare_jid)
      util = Util(user)
      util.allow_duplicate = item.allow_duplicate
      result = util.parse_data(item.data, reverse=item.reverse)
      if result:
        if item.title:
          msg = '%s\n%s' % (item.title, '\n\n'.join(result))
          xmpp.send_message(item.jid, msg)
        else:
          for m in result:
            xmpp.send_message(item.jid, m)
    except BaseException:
      err = StringIO()
      traceback.print_exc(file=err)
      logger = logging.getLogger('worker')
      logger.error(err.getvalue())
    finally:
      q.task_done()
