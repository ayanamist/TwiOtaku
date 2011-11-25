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

CREATE TABLE "id_lists" (
            "uid"  INTEGER NOT NULL,
            "short_id"  INTEGER NOT NULL,
            "long_id"  TEXT NOT NULL,
            "type"  INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX "id_lists_uid_longid_type"
            ON "id_lists" ("uid", "long_id", "type");
            CREATE INDEX "is_lists_uid_shortid_type"
            ON "id_lists" ("uid", "short_id");