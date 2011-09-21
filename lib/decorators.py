import logging
import traceback
from StringIO import StringIO

from util import ThreadStop
# decorator for logging
def debug(logger_name=__name__):
  def wrap(f):
    def newf(*args, **kwds):
      try:
        return f(*args, **kwds)
      except Exception:
        err = StringIO()
        traceback.print_exc(file=err)
        logger = logging.getLogger(logger_name)
        logger.error(err.getvalue())

    return newf

  return wrap


def threadstop(f):
  def wrap(*args, **kwds):
    try:
      return f(*args, **kwds)
    except ThreadStop:
      return

  return wrap