-- Copyright 2011 ayanamist aka gh05tw01f
-- the program is distributed under the terms of the GNU General Public License
-- This file is part of TwiOtaku.
--
--    Foobar is free software: you can redistribute it and/or modify
--    it under the terms of the GNU General Public License as published by
--    the Free Software Foundation, either version 3 of the License, or
--    (at your option) any later version.
--
--    TwiOtaku is distributed in the hope that it will be useful,
--    but WITHOUT ANY WARRANTY; without even the implied warranty of
--    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
--    GNU General Public License for more details.
--
--    You should have received a copy of the GNU General Public License
--    along with TwiOtaku.  If not, see <http://www.gnu.org/licenses/>.

CREATE TABLE "statuses" (
            "id_str"  TEXT NOT NULL,
            "timestamp"  INTEGER NOT NULL,
            "data"  BLOB NOT NULL,
            PRIMARY KEY ("id_str") ON CONFLICT REPLACE
            );
            CREATE UNIQUE INDEX "status_id"
            ON "statuses" ("id_str");
            CREATE INDEX "timestamp"
            ON "statuses" ("timestamp");
