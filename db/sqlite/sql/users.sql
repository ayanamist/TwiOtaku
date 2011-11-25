CREATE TABLE "users" (
        "id"  INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
        "jid"  TEXT NOT NULL,
        "screen_name"  TEXT,
        "access_key"  TEXT,
        "access_secret"  TEXT,
        "last_verified"  INTEGER NOT NULL DEFAULT 0,
        "list_user"  TEXT,
        "list_name"  TEXT,
        "last_home_id"  TEXT,
        "last_mention_id"  TEXT,
        "last_dm_id"  TEXT,
        "last_list_id"  TEXT,
        "last_search_id"  TEXT,
        "last_update"  INTEGER NOT NULL DEFAULT 0,
        "timeline"  INTEGER NOT NULL DEFAULT 3,
        "id_list_ptr"  INTEGER NOT NULL DEFAULT 0,
        "msg_tpl"  BLOB,
        "date_fmt"  TEXT,
        "always"  INTEGER NOT NULL DEFAULT 0,
        "track_words"  TEXT,
        "list_ids"  TEXT,
        "list_ids_last_update"  INTEGER NOT NULL DEFAULT 0,
        "blocked_ids" TEXT,
        "blocked_ids_last_update" INTEGER NOT NULL DEFAULT 0
        );
        CREATE UNIQUE INDEX "users_id"
        ON "users" ("id");
        CREATE UNIQUE INDEX "users_jid"
        ON "users" ("jid");
