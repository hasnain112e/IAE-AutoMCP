"""
Seeds a local MongoDB instance with demo data matching the SQLite demo schema.
Run once before testing: python create_mongo_demo.py

Requires: pip install pymongo
MongoDB must be running on localhost:27017 (default).
Database created: demo_db
Collections: departments, employees, products, orders, payroll
"""
import random
from datetime import datetime, timedelta

MONGO_URI = "mongodb://localhost:27017"
DB_NAME   = "demo_db"
random.seed(42)


def main():
    try:
        import pymongo
    except ImportError:
        print("ERROR: pymongo not installed. Run: pip install pymongo")
        return

    client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
    except Exception as e:
        print(f"ERROR: Cannot connect to MongoDB at {MONGO_URI}\n{e}")
        print("Make sure MongoDB is running: https://www.mongodb.com/docs/manual/installation/")
        return

    db = client[DB_NAME]

    # Drop existing collections for a clean seed
    for col in ["departments", "employees", "products", "orders", "payroll"]:
        db[col].drop()

    # ── Departments ──────────────────────────────────────────────────────────
    departments = [
        {"id": 1, "name": "Engineering", "location": "Karachi",   "budget": 5000000},
        {"id": 2, "name": "Sales",       "location": "Lahore",    "budget": 3000000},
        {"id": 3, "name": "HR",          "location": "Islamabad", "budget": 1500000},
        {"id": 4, "name": "Marketing",   "location": "Karachi",   "budget": 2000000},
        {"id": 5, "name": "Finance",     "location": "Lahore",    "budget": 2500000},
    ]
    db["departments"].insert_many(departments)

    # ── Employees ────────────────────────────────────────────────────────────
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
        employees.append({
            "id": i, "name": name, "email": email,
            "department_id": dept, "salary": salary,
            "hire_date": hire_date, "status": status,
        })
    db["employees"].insert_many(employees)

    # ── Products ─────────────────────────────────────────────────────────────
    products = [
        {"id":  1, "name": "Laptop Pro 15",       "category": "Electronics",    "price": 150000, "stock_quantity": 45,  "supplier": "TechCorp PK"},
        {"id":  2, "name": "Wireless Mouse",       "category": "Electronics",    "price":   2500, "stock_quantity": 200, "supplier": "TechCorp PK"},
        {"id":  3, "name": "Office Chair",         "category": "Furniture",      "price":  25000, "stock_quantity":  30, "supplier": "FurnishPro"},
        {"id":  4, "name": "Standing Desk",        "category": "Furniture",      "price":  45000, "stock_quantity":  15, "supplier": "FurnishPro"},
        {"id":  5, "name": "A4 Paper (Ream)",      "category": "Stationery",     "price":    800, "stock_quantity": 500, "supplier": "PaperWorks"},
        {"id":  6, "name": "Ballpoint Pens Box",   "category": "Stationery",     "price":    350, "stock_quantity": 300, "supplier": "PaperWorks"},
        {"id":  7, "name": "USB-C Hub",            "category": "Electronics",    "price":   3500, "stock_quantity":  80, "supplier": "TechCorp PK"},
        {"id":  8, "name": "Monitor 27 inch",      "category": "Electronics",    "price":  55000, "stock_quantity":  20, "supplier": "TechCorp PK"},
        {"id":  9, "name": "Whiteboard",           "category": "Office Supplies","price":   8000, "stock_quantity":  25, "supplier": "OfficeDepot"},
        {"id": 10, "name": "Projector",            "category": "Electronics",    "price":  85000, "stock_quantity":   8, "supplier": "TechCorp PK"},
        {"id": 11, "name": "Mechanical Keyboard",  "category": "Electronics",    "price":  12000, "stock_quantity":  60, "supplier": "TechCorp PK"},
        {"id": 12, "name": "Webcam HD",            "category": "Electronics",    "price":   7500, "stock_quantity":  45, "supplier": "TechCorp PK"},
        {"id": 13, "name": "Filing Cabinet",       "category": "Furniture",      "price":  18000, "stock_quantity":  12, "supplier": "FurnishPro"},
        {"id": 14, "name": "Notebook Pack",        "category": "Stationery",     "price":    500, "stock_quantity": 400, "supplier": "PaperWorks"},
        {"id": 15, "name": "Headphones",           "category": "Electronics",    "price":   9000, "stock_quantity":  55, "supplier": "TechCorp PK"},
    ]
    db["products"].insert_many(products)

    # ── Orders ───────────────────────────────────────────────────────────────
    statuses = ["completed", "pending", "cancelled", "shipped"]
    orders = []
    for i in range(1, 101):
        prod     = products[random.randint(0, 14)]
        qty      = random.randint(1, 5)
        days_ago = random.randint(1, 365)
        orders.append({
            "id":           i,
            "employee_id":  random.randint(1, 20),
            "product_id":   prod["id"],
            "quantity":     qty,
            "total_amount": round(qty * prod["price"], 2),
            "order_date":   (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d"),
            "status":       random.choice(statuses),
        })
    db["orders"].insert_many(orders)

    # ── Payroll ──────────────────────────────────────────────────────────────
    payroll = []
    pid = 1
    for emp in employees:
        for month_offset in range(6):
            month      = (datetime.now() - timedelta(days=30 * month_offset)).strftime("%Y-%m")
            basic      = emp["salary"]
            bonus      = round(basic * random.uniform(0, 0.1), 2)
            deductions = round(basic * 0.05, 2)
            net        = round(basic + bonus - deductions, 2)
            payroll.append({
                "id":          pid,
                "employee_id": emp["id"],
                "month":       month,
                "basic_salary": basic,
                "bonus":       bonus,
                "deductions":  deductions,
                "net_salary":  net,
            })
            pid += 1
    db["payroll"].insert_many(payroll)

    client.close()

    print("=" * 50)
    print(f"  MongoDB demo_db seeded successfully!")
    print("=" * 50)
    print(f"  URI:      {MONGO_URI}")
    print(f"  Database: {DB_NAME}")
    print("  Collections:")
    print(f"    departments  —  {len(departments)} documents")
    print(f"    employees    —  {len(employees)} documents")
    print(f"    products     —  {len(products)} documents")
    print(f"    orders       —  {len(orders)} documents")
    print(f"    payroll      —  {len(payroll)} documents")
    print("=" * 50)
    print("  Connect in AI DB Explorer:")
    print(f"    db_type = mongodb")
    print(f"    host    = localhost")
    print(f"    port    = 27017")
    print(f"    dbname  = {DB_NAME}")


if __name__ == "__main__":
    main()
