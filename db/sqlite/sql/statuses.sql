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
