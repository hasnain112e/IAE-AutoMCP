"""Creates demo_database.db with realistic sample data for testing the AI agent."""
import sqlite3
import random
import os
from datetime import datetime, timedelta

DB_PATH = "demo_database.db"
random.seed(42)

if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# ── Departments ───────────────────────────────────────────────────────────────
cur.execute("""
CREATE TABLE departments (
    id       INTEGER PRIMARY KEY,
    name     TEXT NOT NULL,
    location TEXT,
    budget   REAL
)
""")
cur.executemany("INSERT INTO departments VALUES (?,?,?,?)", [
    (1, "Engineering", "Karachi",   5000000),
    (2, "Sales",       "Lahore",    3000000),
    (3, "HR",          "Islamabad", 1500000),
    (4, "Marketing",   "Karachi",   2000000),
    (5, "Finance",     "Lahore",    2500000),
])

# ── Employees ─────────────────────────────────────────────────────────────────
cur.execute("""
CREATE TABLE employees (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    email         TEXT,
    department_id INTEGER,
    salary        REAL,
    hire_date     TEXT,
    status        TEXT,
    FOREIGN KEY(department_id) REFERENCES departments(id)
)
""")
names = [
    "Ali Hassan", "Sara Ahmed", "Usman Khan", "Fatima Malik", "Bilal Sheikh",
    "Ayesha Noor", "Hamza Raza", "Zara Butt", "Omar Farooq", "Hina Javed",
    "Ahmed Siddiqui", "Sana Tariq", "Raza Mirza", "Nadia Qureshi", "Tariq Mehmood",
    "Maria Baig", "Imran Shah", "Layla Ansari", "Faisal Iqbal", "Amna Chaudhry",
]
employees = []
for i, name in enumerate(names, 1):
    dept      = (i % 5) + 1
    salary    = round(random.uniform(60000, 200000), 2)
    days_ago  = random.randint(30, 1500)
    hire_date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
    status    = "active" if random.random() > 0.15 else "inactive"
    email     = name.lower().replace(" ", ".") + "@company.com"
    employees.append((i, name, email, dept, salary, hire_date, status))
cur.executemany("INSERT INTO employees VALUES (?,?,?,?,?,?,?)", employees)

# ── Products ──────────────────────────────────────────────────────────────────
cur.execute("""
CREATE TABLE products (
    id             INTEGER PRIMARY KEY,
    name           TEXT NOT NULL,
    category       TEXT,
    price          REAL,
    stock_quantity INTEGER,
    supplier       TEXT
)
""")
products_data = [
    (1,  "Laptop Pro 15",       "Electronics",    150000, 45,  "TechCorp PK"),
    (2,  "Wireless Mouse",      "Electronics",      2500, 200, "TechCorp PK"),
    (3,  "Office Chair",        "Furniture",        25000,  30, "FurnishPro"),
    (4,  "Standing Desk",       "Furniture",        45000,  15, "FurnishPro"),
    (5,  "A4 Paper (Ream)",     "Stationery",         800, 500, "PaperWorks"),
    (6,  "Ballpoint Pens Box",  "Stationery",         350, 300, "PaperWorks"),
    (7,  "USB-C Hub",           "Electronics",       3500,  80, "TechCorp PK"),
    (8,  "Monitor 27 inch",     "Electronics",      55000,  20, "TechCorp PK"),
    (9,  "Whiteboard",          "Office Supplies",   8000,  25, "OfficeDepot"),
    (10, "Projector",           "Electronics",      85000,   8, "TechCorp PK"),
    (11, "Mechanical Keyboard", "Electronics",      12000,  60, "TechCorp PK"),
    (12, "Webcam HD",           "Electronics",       7500,  45, "TechCorp PK"),
    (13, "Filing Cabinet",      "Furniture",        18000,  12, "FurnishPro"),
    (14, "Notebook Pack",       "Stationery",         500, 400, "PaperWorks"),
    (15, "Headphones",          "Electronics",       9000,  55, "TechCorp PK"),
]
cur.executemany("INSERT INTO products VALUES (?,?,?,?,?,?)", products_data)

# ── Orders ────────────────────────────────────────────────────────────────────
cur.execute("""
CREATE TABLE orders (
    id           INTEGER PRIMARY KEY,
    employee_id  INTEGER,
    product_id   INTEGER,
    quantity     INTEGER,
    total_amount REAL,
    order_date   TEXT,
    status       TEXT,
    FOREIGN KEY(employee_id) REFERENCES employees(id),
    FOREIGN KEY(product_id)  REFERENCES products(id)
)
""")
statuses = ["completed", "pending", "cancelled", "shipped"]
orders = []
for i in range(1, 101):
    emp_id     = random.randint(1, 20)
    prod_id    = random.randint(1, 15)
    qty        = random.randint(1, 5)
    price      = products_data[prod_id - 1][3]
    total      = round(qty * price, 2)
    days_ago   = random.randint(1, 365)
    order_date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
    status     = random.choice(statuses)
    orders.append((i, emp_id, prod_id, qty, total, order_date, status))
cur.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?,?)", orders)

# ── Payroll ───────────────────────────────────────────────────────────────────
cur.execute("""
CREATE TABLE payroll (
    id          INTEGER PRIMARY KEY,
    employee_id INTEGER,
    month       TEXT,
    basic_salary REAL,
    bonus       REAL,
    deductions  REAL,
    net_salary  REAL,
    FOREIGN KEY(employee_id) REFERENCES employees(id)
)
""")
payroll = []
pid = 1
for emp in employees:
    for month_offset in range(6):
        month      = (datetime.now() - timedelta(days=30 * month_offset)).strftime("%Y-%m")
        basic      = emp[4]
        bonus      = round(basic * random.uniform(0, 0.1), 2)
        deductions = round(basic * 0.05, 2)
        net        = round(basic + bonus - deductions, 2)
        payroll.append((pid, emp[0], month, basic, bonus, deductions, net))
        pid += 1
cur.executemany("INSERT INTO payroll VALUES (?,?,?,?,?,?,?)", payroll)

conn.commit()
conn.close()

print("=" * 50)
print("  demo_database.db created successfully!")
print("=" * 50)
print("  Tables:")
print("    departments  —  5 rows")
print("    employees    — 20 rows")
print("    products     — 15 rows")
print("    orders       — 100 rows")
print("    payroll      — 120 rows")
print("=" * 50)
print(f"  File: {os.path.abspath(DB_PATH)}")
