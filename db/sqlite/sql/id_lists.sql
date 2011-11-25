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