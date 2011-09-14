import logging
import traceback
from StringIO import StringIO

try:
  import ujson as json
except ImportError:
  import json

import db
import twitter

# decorator for logging
def debug(logger_name=__name__):
  def wrap(f):
    def newf(*args, **kwds):
      try:
        return f(*args, **kwds)
      except BaseException:
        err = StringIO()
        traceback.print_exc(file=err)
        logger = logging.getLogger(logger_name)
        logger.error(err.getvalue())

    return newf

  return wrap

# decorator for auto cache status
def store_status(f):
  def newf(*args, **kwds):
    result = f(*args, **kwds)
    if isinstance(result, list):
      db.begin_transaction()
      for x in result:
        if isinstance(x, twitter.Status):
          db.add_status(x['id_str'], json.dumps(x))
      db.commit_transaction()
    elif isinstance(result, twitter.Status):
      db.add_status(result['id_str'], json.dumps(result))
    elif isinstance(result, twitter.Result):
      db.begin_transaction()
      for x in result[0]['results']:
        db.add_status(x['value']['id_str'], json.dumps(x['value']))
      db.commit_transaction()
    return result

  return newf
  