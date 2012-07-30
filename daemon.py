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
import logging
import sys
import signal
import time

logging.basicConfig(level=logging.ERROR, format='%(asctime)-15s %(name)-8s %(levelname)-8s %(message)s',
    datefmt='%m-%d %H:%M:%S', stream=sys.stderr)

import db
from core import bot

xmpp_bot = bot.XMPPBot()

def sigterm_handler(*_):
    xmpp_bot.stop_streams()
    xmpp_bot.stop_cron()
    xmpp_bot.stop_workers()
    db.close()
    sys.exit(0)


if __name__ == '__main__':
    if sys.version_info[0] != 2 or sys.version_info[1] < 6:
        print 'TwiOtaku needs Python 2.6 or later. Python 3.X is not supported yet.'
        exit(2)

    signal.signal(signal.SIGTERM, sigterm_handler)
    xmpp_bot.start(block=True)
    last_connected_time = time.time()
    flag = True
    while flag:
        now = time.time()
        if now - last_connected_time > 60:
            xmpp_bot.reconnect()
            last_connected_time = now
        else:
            flag = False
    sys.exit(1)
