#!/usr/bin/env python
import sys
import signal
import logging

logging.basicConfig(level=logging.WARNING, format='%(asctime)-15s %(name)-8s %(levelname)-8s %(message)s',
                    datefmt='%m-%d %H:%M:%S', stream=sys.stderr)

from core.bot import XMPPBot

if __name__ == '__main__':
  if sys.version_info[0] != 2 or sys.version_info[1] < 6:
    print 'TwiOtaku needs Python 2.6 or later. Python 3.X is not supported yet.'
    exit(1)

  bot = XMPPBot()
  signal.signal(signal.SIGTERM, bot.sigterm_handler)
  bot.start(block=True)