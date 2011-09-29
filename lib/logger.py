import logging
import sys
import traceback
from functools import wraps
from StringIO import StringIO

LOGGING_FORMAT = '%(asctime)-15s %(name)-8s %(levelname)-8s %(message)s'
LOGGING_DATEFMT = '%m-%d %H:%M:%S'

def debug(f):
  @wraps(f)
  def wrap(*args, **kwds):
    try:
      return f(*args, **kwds)
    except Exception:
      err = StringIO()
      traceback.print_exc(file=err)
      logging.error(err.getvalue())

  return wrap

logging.basicConfig(level=logging.DEBUG, format=LOGGING_FORMAT, datefmt=LOGGING_DATEFMT, stream=sys.stdout)
logging_stderr = logging.StreamHandler(sys.stderr)
logging_stderr.setLevel(logging.WARNING)
formatter = logging.Formatter(LOGGING_FORMAT, datefmt=LOGGING_DATEFMT)
logging_stderr.setFormatter(formatter)
logging.getLogger('').addHandler(logging_stderr)
