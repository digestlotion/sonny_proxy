from api import db, permission

permission.create("filter_lock", "Filter lock", True, False)

db.table(
    "profiles",[
        "userid BIGINT NOT NULL",
        "name TEXT NOT NULL",
        "avatar TEXT",
        "prefix TEXT",
        "filter JSONB",
        "PRIMARY KEY (userId, name)",
    ],
)

db.table(
    "locks",[
        "serverid BIGINT NOT NULL",
        "userid BIGINT NOT NULL",
        "filter JSONB",
        "PRIMARY KEY (serverid, userid)",
    ],
)