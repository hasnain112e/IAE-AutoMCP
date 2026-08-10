"""Mock Database Setup for Testing"""
import json
from typing import List, Dict, Any
from datetime import datetime, timedelta
import random

class MockMongoDB:
    """Mock MongoDB instance for testing"""

    def __init__(self):
        self.db_name = "test_mcp_db"
        self.collections = {
            "employees": self._init_employees(),
            "payrolls": self._init_payrolls(),
            "departments": self._init_departments(),
        }

    def _init_employees(self) -> List[Dict[str, Any]]:
        """Initialize employee data"""
        return [
            {
                "_id": "emp_001",
                "name": "Ahmed Khan",
                "department_id": "dept_001",
                "position": "Senior Developer",
                "email": "ahmed@company.com",
                "salary": 120000,
                "hire_date": "2020-01-15",
                "status": "active"
            },
            {
                "_id": "emp_002",
                "name": "Fatima Ali",
                "department_id": "dept_001",
                "position": "Backend Engineer",
                "email": "fatima@company.com",
                "salary": 100000,
                "hire_date": "2021-06-01",
                "status": "active"
            },
            {
                "_id": "emp_003",
                "name": "Hassan Malik",
                "department_id": "dept_002",
                "position": "Product Manager",
                "email": "hassan@company.com",
                "salary": 110000,
                "hire_date": "2019-03-20",
                "status": "active"
            },
        ]

    def _init_payrolls(self) -> List[Dict[str, Any]]:
        """Initialize payroll data"""
        return [
            {
                "_id": "payroll_001",
                "emp_id": "emp_001",
                "month": "2024-05",
                "base_salary": 120000,
                "bonus": 5000,
                "deductions": 15000,
                "net_salary": 110000,
                "status": "paid"
            },
            {
                "_id": "payroll_002",
                "emp_id": "emp_002",
                "month": "2024-05",
                "base_salary": 100000,
                "bonus": 3000,
                "deductions": 12000,
                "net_salary": 91000,
                "status": "paid"
            },
            {
                "_id": "payroll_003",
                "emp_id": "emp_003",
                "month": "2024-05",
                "base_salary": 110000,
                "bonus": 4000,
                "deductions": 13500,
                "net_salary": 100500,
                "status": "pending"
            },
        ]

    def _init_departments(self) -> List[Dict[str, Any]]:
        """Initialize department data"""
        return [
            {
                "_id": "dept_001",
                "name": "Engineering",
                "budget": 500000,
                "manager_id": "emp_001"
            },
            {
                "_id": "dept_002",
                "name": "Product",
                "budget": 300000,
                "manager_id": "emp_003"
            },
        ]

    def find(self, collection: str, query: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Find documents in collection"""
        if collection not in self.collections:
            return []

        if query is None:
            return self.collections[collection]

        results = []
        for doc in self.collections[collection]:
            if self._matches_query(doc, query):
                results.append(doc)
        return results

    def find_one(self, collection: str, query: Dict[str, Any]) -> Dict[str, Any] or None:
        """Find single document"""
        results = self.find(collection, query)
        return results[0] if results else None

    def _matches_query(self, doc: Dict, query: Dict) -> bool:
        """Check if document matches query"""
        for key, value in query.items():
            if key not in doc or doc[key] != value:
                return False
        return True


class MockPostgreSQL:
    """Mock PostgreSQL instance for testing"""

    def __init__(self):
        self.db_name = "test_mcp_postgres"
        self.tables = {
            "employees": self._init_employees_table(),
            "payrolls": self._init_payrolls_table(),
            "departments": self._init_departments_table(),
        }

    def _init_employees_table(self) -> List[Dict[str, Any]]:
        """Initialize PostgreSQL employees table"""
        return [
            {
                "id": 1,
                "name": "Ahmed Khan",
                "department_id": 1,
                "position": "Senior Developer",
                "email": "ahmed@company.com",
                "salary": 120000,
                "hire_date": "2020-01-15",
                "status": "active"
            },
            {
                "id": 2,
                "name": "Fatima Ali",
                "department_id": 1,
                "position": "Backend Engineer",
                "email": "fatima@company.com",
                "salary": 100000,
                "hire_date": "2021-06-01",
                "status": "active"
            },
            {
                "id": 3,
                "name": "Hassan Malik",
                "department_id": 2,
                "position": "Product Manager",
                "email": "hassan@company.com",
                "salary": 110000,
                "hire_date": "2019-03-20",
                "status": "active"
            },
        ]

    def _init_payrolls_table(self) -> List[Dict[str, Any]]:
        """Initialize PostgreSQL payrolls table"""
        return [
            {
                "id": 1,
                "emp_id": 1,
                "month": "2024-05",
                "base_salary": 120000,
                "bonus": 5000,
                "deductions": 15000,
                "net_salary": 110000,
                "status": "paid"
            },
            {
                "id": 2,
                "emp_id": 2,
                "month": "2024-05",
                "base_salary": 100000,
                "bonus": 3000,
                "deductions": 12000,
                "net_salary": 91000,
                "status": "paid"
            },
            {
                "id": 3,
                "emp_id": 3,
                "month": "2024-05",
                "base_salary": 110000,
                "bonus": 4000,
                "deductions": 13500,
                "net_salary": 100500,
                "status": "pending"
            },
        ]

    def _init_departments_table(self) -> List[Dict[str, Any]]:
        """Initialize PostgreSQL departments table"""
        return [
            {
                "id": 1,
                "name": "Engineering",
                "budget": 500000,
                "manager_id": 1
            },
            {
                "id": 2,
                "name": "Product",
                "budget": 300000,
                "manager_id": 3
            },
        ]

    def select(self, table: str, where: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Select rows from table (READ-ONLY)"""
        if table not in self.tables:
            return []

        if where is None:
            return self.tables[table]

        results = []
        for row in self.tables[table]:
            if self._matches_where(row, where):
                results.append(row)
        return results

    def select_one(self, table: str, where: Dict[str, Any]) -> Dict[str, Any] or None:
        """Select single row (READ-ONLY)"""
        results = self.select(table, where)
        return results[0] if results else None

    def _matches_where(self, row: Dict, where: Dict) -> bool:
        """Check if row matches WHERE clause"""
        for key, value in where.items():
            if key not in row or row[key] != value:
                return False
        return True

    def get_schema(self) -> Dict[str, List[str]]:
        """Get database schema"""
        return {
            "employees": ["id", "name", "department_id", "position", "email", "salary", "hire_date", "status"],
            "payrolls": ["id", "emp_id", "month", "base_salary", "bonus", "deductions", "net_salary", "status"],
            "departments": ["id", "name", "budget", "manager_id"],
        }


class DatabaseManager:
    """Manage both mock databases"""

    def __init__(self):
        self.mongodb = MockMongoDB()
        self.postgresql = MockPostgreSQL()
        self.query_history = []

    def get_mongodb(self):
        return self.mongodb

    def get_postgresql(self):
        return self.postgresql

    def log_query(self, db_type: str, operation: str, details: Dict[str, Any]):
        """Log all queries for audit trail"""
        self.query_history.append({
            "timestamp": datetime.now().isoformat(),
            "db_type": db_type,
            "operation": operation,
            "details": details
        })

    def get_audit_trail(self) -> List[Dict[str, Any]]:
        """Get all queries executed"""
        return self.query_history
