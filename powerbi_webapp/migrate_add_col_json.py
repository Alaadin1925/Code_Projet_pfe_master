import sqlite3, os

db = os.path.join(os.path.dirname(__file__), "app.db")
con = sqlite3.connect(db)
cur = con.cursor()
cols = [row[1] for row in cur.execute("PRAGMA table_info(job_run)")]
print("existing cols:", cols)

to_add = [
    ("col_depot_json",     "TEXT DEFAULT '[]'"),
    ("col_livraison_json", "TEXT DEFAULT '[]'"),
    ("cat_depot_json",      "TEXT DEFAULT '[]'"),
    ("cat_livraison_json",  "TEXT DEFAULT '[]'"),
    ("region_next_json",    "TEXT DEFAULT '[]'"),
]
for col_name, col_def in to_add:
    if col_name not in cols:
        cur.execute(f"ALTER TABLE job_run ADD COLUMN {col_name} {col_def}")
        print(f"added {col_name}")
    else:
        print(f"{col_name} already exists")

con.commit()
con.close()
print("Done.")
