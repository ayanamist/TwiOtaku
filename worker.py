import traceback
import logging
from StringIO import StringIO

import db
from util import Util

def worker(xmpp, q):
  while True:
    item = q.get()
    reverse = False
    if item is None:
      break
    data = jid = title = None
    length = len(item)
    try:
      if length == 2:
        data, jid = item
      elif length == 3:
        data, jid, title = item
      elif length == 4:
        data, jid, title, reverse = item
      else:
        raise ValueError('Unexpected job item with length %d: %s' % (length, unicode(item)))
      bare_jid = jid.split('/')[0].lower()
      user = db.get_user_from_jid(bare_jid)
      util = Util(user)
      util.allow_duplicate = False
      result = util.parse_data(data, reverse=reverse)
      if result:
        if title:
          msg = '%s\n%s' % (title, '\n'.join(result))
          xmpp.send_message(jid, msg)
        else:
          for m in result:
            xmpp.send_message(jid, m)
    except BaseException:
      err = StringIO()
      traceback.print_exc(file=err)
      logger = logging.getLogger('worker')
      logger.error(err.getvalue())
    finally:
      q.task_done()
