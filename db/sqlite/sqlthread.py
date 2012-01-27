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
import Queue

from . import sqlcommand
from lib import mythread

logger = logging.getLogger('sqlite_thread')


class SQLThread(mythread.StoppableThread):
    def __init__(self, conn_user):
        super(SQLThread, self).__init__()
        self.__conn_user = conn_user
        self.__write_queue = Queue.Queue()

    def process(self, command):
        return self.__write_queue.put(command)

    @mythread.monitorstop
    def run(self):
        while True:
            self.check_stop()
            command = self.__write_queue.get()
            if isinstance(command, sqlcommand.SQLCommand):
                try:
                    func = getattr(self, command.name)
                except AttributeError, e:
                    result = e
                else:
                    try:
                        result = func(*command.args, **command.kwargs)
                    except Exception, e:
                        result = e
                command.result_queue.put(result)
            self.__write_queue.task_done()


    def update_user(self, id=None, jid=None, **kwargs):
        if id is None and jid is None:
            raise TypeError('The method takes at least one argument.')
        if kwargs:
            cols = list()
            values = list()
            for k, v in kwargs.iteritems():
                cols.append('%s=?' % k)
                values.append(v)
            if id:
                cond = 'id=?'
                values.append(id)
            else:
                cond = 'jid=?'
                values.append(jid)
            sql = 'UPDATE users SET %s WHERE %s' % (','.join(cols), cond)
            self.__conn_user.execute(sql, values)
            self.__conn_user.commit()


    def add_user(self, jid):
        sql = 'INSERT INTO users (jid) VALUES(?)'
        self.__conn_user.execute(sql, (jid,))
        self.__conn_user.commit()


    def add_invite_code(self, invite_code, create_time):
        sql = 'INSERT INTO invites (id, create_time) VALUES(?,?)'
        self.__conn_user.execute(sql, (invite_code, create_time))
        self.__conn_user.commit()


    def delete_invite_code(self, invite_code):
        sql = 'DELETE FROM invites WHERE id=?'
        self.__conn_user.execute(sql, (invite_code,))
        self.__conn_user.commit()


    def update_long_id_from_short_id(self, uid, short_id, long_id, single_type):
        sql = 'INSERT OR REPLACE INTO id_lists (uid, short_id, long_id, type) VALUES(?, ?, ?, ?)'
        self.__conn_user.execute(sql, (uid, short_id, long_id, single_type))
        self.__conn_user.commit()
