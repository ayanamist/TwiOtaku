#!/usr/bin/env python
# Copyright 2011 ayanamist
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
import functools
import logging
import sys
import signal

logging.basicConfig(level=logging.ERROR, format='%(asctime)-15s %(name)-8s %(levelname)-8s %(message)s',
    datefmt='%m-%d %H:%M:%S', stream=sys.stderr)

import db
from core import bot

xmpp_bot = bot.XMPPBot()

def sigterm_handler(errno, *_):
    xmpp_bot.stop_streams()
    xmpp_bot.stop_cron()
    xmpp_bot.stop_workers()
    db.close()
    sys.exit(errno)


if __name__ == '__main__':
    if sys.version_info[0] != 2 or sys.version_info[1] < 7:
        print 'TwiOtaku needs Python 2.7 or later. Python 3.X is not supported yet.'
        sys.exit(2)

    signal.signal(signal.SIGTERM, functools.partial(sigterm_handler, 0))
    xmpp_bot.start(block=True)
    sigterm_handler(1)
