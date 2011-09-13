import logging
import sys

LOGGING_FORMAT = '%(asctime)-15s %(name)-8s %(levelname)-8s %(message)s'
LOGGING_DATEFMT = '%m-%d %H:%M:%S'

class DetailHandler(logging.StreamHandler):
  def __init__(self, strm=None):
    logging.StreamHandler.__init__(self, strm=strm)
    formatter = logging.Formatter(LOGGING_FORMAT, datefmt=LOGGING_DATEFMT)
    self.setFormatter(formatter)


class DetailLogger(logging.Logger):
  def __init__(self, name, level=logging.NOTSET):
    logging.Logger.__init__(self, name, level=level)

    logging_stderr = DetailHandler()
    logging_stderr.setLevel(logging.ERROR)
    self.addHandler(logging_stderr)

    logging_stdout = DetailHandler(sys.stdout)
    self.addHandler(logging_stdout)