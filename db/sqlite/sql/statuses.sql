-- Copyright 2012 ayanamist
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
  "id"  TEXT PRIMARY KEY NOT NULL,
  "value"  BLOB
);
CREATE UNIQUE INDEX "statuses_id" ON "statuses" ("id");
