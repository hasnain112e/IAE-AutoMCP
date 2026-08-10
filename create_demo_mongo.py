import os
import sqlite3
import pymongo
from datetime import datetime

# Paths – adjust if you move the repo
DB_PATH = os.path.join(os.path.dirname(__file__), "demo_database.db")

# MongoDB connection – reads from .env or defaults
MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
client = pymongo.MongoClient(MONGO_URI)
# Use a dedicated database for the demo to avoid clashes
mdb = client["demo"]

# Helper to clear previous demo collections
for coll in ["departments", "employees", "products", "orders", "payroll"]:
    mdb.drop_collection(coll)

# Open SQLite and fetch each table
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

def fetch_table(name):
    cur.execute(f"SELECT * FROM {name}")
    rows = cur.fetchall()
    # Convert sqlite Row objects to plain dicts (JSON‑serialisable)
    return [dict(row) for row in rows]

# Load each table and insert into MongoDB
for table in ["departments", "employees", "products", "orders", "payroll"]:
    docs = fetch_table(table)
    if docs:
        mdb[table].insert_many(docs)
        print(f"Inserted {len(docs)} documents into collection '{table}'.")

conn.close()
print("Demo MongoDB database 'demo' populated successfully.")
