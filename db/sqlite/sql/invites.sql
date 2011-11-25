CREATE TABLE "invites" (
        "id"  TEXT NOT NULL,
        "create_time"   INTEGER NOT NULL,
        PRIMARY KEY ("id") ON CONFLICT FAIL
        );
        CREATE UNIQUE INDEX "invite_id"
        ON "invites" ("id");
