#!/usr/bin/env python
# Copyright 2011 ayanamist aka gh05tw01f
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

import sys
import signal
import logging

logging.basicConfig(level=logging.ERROR, format='%(asctime)-15s %(name)-8s %(levelname)-8s %(message)s',
    datefmt='%m-%d %H:%M:%S', stream=sys.stderr)

from core import bot

if __name__ == '__main__':
    if sys.version_info[0] != 2 or sys.version_info[1] < 6:
        print 'TwiOtaku needs Python 2.6 or later. Python 3.X is not supported yet.'
        exit(1)

    bot = bot.XMPPBot()
    signal.signal(signal.SIGTERM, bot.sigterm_handler)
    bot.start(block=True)