from api import db, permission

permission.create("lock", "Filter lock", True, False)

db.table(
    "sonny_proxy$profiles",
    [
        "userid BIGINT NOT NULL",
        "name TEXT NOT NULL",
        "avatar TEXT",
        "prefix TEXT",
        "filter JSONB",
        "PRIMARY KEY (userId, name)",
    ],
)