"""Comprehensive tests for Database Agent and Safety Checks"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agents.database_agent import (
    DatabaseAgent, database_agent, DatabaseManager,
    SafetyCheckEngine, QueryValidator
)


class TestRunner:
    """Run comprehensive tests"""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.results = []

    def test(self, name: str, condition: bool, details: str = ""):
        """Record test result"""
        status = "[PASS]" if condition else "[FAIL]"
        print(f"{status}: {name}")
        if details:
            print(f"     {details}")

        if condition:
            self.passed += 1
        else:
            self.failed += 1

        self.results.append({
            "name": name,
            "passed": condition,
            "details": details
        })

    def summary(self):
        """Print test summary"""
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"Test Summary: {self.passed}/{total} passed")
        print(f"{'='*60}\n")


def test_mock_mongodb():
    """Test Mock MongoDB functionality"""
    print("\n[TEST 1] Mock MongoDB Setup")
    print("-" * 60)
    runner = TestRunner()

    db_manager = DatabaseManager()
    mongo = db_manager.mongodb

    # Test collections exist
    runner.test(
        "MongoDB collections initialized",
        all(coll in mongo.collections for coll in ["employees", "payrolls", "departments"])
    )

    # Test find operations
    employees = mongo.find("employees")
    runner.test(
        "MongoDB find() returns employees",
        len(employees) == 3,
        f"Expected 3 employees, got {len(employees)}"
    )

    # Test find with query
    ahmed = mongo.find_one("employees", {"name": "Ahmed Khan"})
    runner.test(
        "MongoDB find_one() with query",
        ahmed is not None and ahmed["name"] == "Ahmed Khan"
    )

    runner.summary()
    return runner.passed, runner.failed


def test_mock_postgresql():
    """Test Mock PostgreSQL functionality"""
    print("\n[TEST 2] Mock PostgreSQL Setup")
    print("-" * 60)
    runner = TestRunner()

    db_manager = DatabaseManager()
    pg = db_manager.postgresql

    # Test schema
    schema = pg.get_schema()
    runner.test(
        "PostgreSQL schema contains tables",
        all(table in schema for table in ["employees", "payrolls", "departments"]),
        f"Tables: {list(schema.keys())}"
    )

    # Test select operations
    employees = pg.select("employees")
    runner.test(
        "PostgreSQL select() returns employees",
        len(employees) == 3,
        f"Expected 3 employees, got {len(employees)}"
    )

    # Test select with WHERE
    fatima = pg.select_one("employees", {"name": "Fatima Ali"})
    runner.test(
        "PostgreSQL select_one() with WHERE",
        fatima is not None and fatima["name"] == "Fatima Ali"
    )

    runner.summary()
    return runner.passed, runner.failed


def test_query_validation():
    """Test SQL Query Validation"""
    print("\n[TEST 3] SQL Query Validation")
    print("-" * 60)
    runner = TestRunner()

    validator = QueryValidator()

    # Test safe SELECT
    is_safe, msg = validator.is_safe_sql_query("SELECT * FROM employees")
    runner.test(
        "SELECT query is safe",
        is_safe and "Safe" in msg
    )

    # Test DELETE is blocked
    is_safe, msg = validator.is_safe_sql_query("DELETE FROM employees WHERE id = 1")
    runner.test(
        "DELETE query is blocked",
        not is_safe and "DELETE" in msg,
        f"Message: {msg}"
    )

    # Test DROP is blocked
    is_safe, msg = validator.is_safe_sql_query("DROP TABLE employees")
    runner.test(
        "DROP query is blocked",
        not is_safe and "DROP" in msg
    )

    # Test UPDATE is blocked
    is_safe, msg = validator.is_safe_sql_query("UPDATE employees SET salary = 200000")
    runner.test(
        "UPDATE query is blocked",
        not is_safe and "UPDATE" in msg
    )

    # Test INSERT is blocked
    is_safe, msg = validator.is_safe_sql_query("INSERT INTO employees VALUES (...)")
    runner.test(
        "INSERT query is blocked",
        not is_safe and "INSERT" in msg
    )

    runner.summary()
    return runner.passed, runner.failed


def test_mongo_operation_validation():
    """Test MongoDB Operation Validation"""
    print("\n[TEST 4] MongoDB Operation Validation")
    print("-" * 60)
    runner = TestRunner()

    validator = QueryValidator()

    # Test safe operations
    is_safe, msg = validator.is_safe_mongo_operation("find", {})
    runner.test(
        "find() operation is safe",
        is_safe
    )

    # Test deleteOne is blocked
    is_safe, msg = validator.is_safe_mongo_operation("deleteOne", {})
    runner.test(
        "deleteOne() is blocked",
        not is_safe and "deleteOne" in msg
    )

    # Test updateMany is blocked
    is_safe, msg = validator.is_safe_mongo_operation("updateMany", {})
    runner.test(
        "updateMany() is blocked",
        not is_safe and "updateMany" in msg
    )

    runner.summary()
    return runner.passed, runner.failed


async def test_database_agent_exploration():
    """Test Database Agent Exploration Phase"""
    print("\n[TEST 5] Database Agent - Exploration Phase")
    print("-" * 60)
    runner = TestRunner()

    agent = DatabaseAgent()

    # Test exploration
    result = await agent.explore_schema()
    runner.test(
        "explore_schema() succeeds",
        result.get("success") == True
    )

    runner.test(
        "Schema discovery returns PostgreSQL tables",
        "postgresql_schema" in result and len(result["postgresql_schema"]) > 0
    )

    runner.test(
        "Schema discovery returns MongoDB collections",
        "mongodb_collections" in result and len(result["mongodb_collections"]) > 0
    )

    status = result.get("status", {})
    runner.test(
        "Schema marked as explored",
        status.get("schema_discovered") == True
    )

    runner.summary()
    return runner.passed, runner.failed


async def test_database_agent_queries():
    """Test Database Agent Queries"""
    print("\n[TEST 6] Database Agent - Read Queries")
    print("-" * 60)
    runner = TestRunner()

    agent = DatabaseAgent()

    # First explore
    await agent.explore_schema()

    # Test query_employees
    result = await agent.query_employees(db_type="postgresql")
    runner.test(
        "query_employees() succeeds",
        result.get("success") == True
    )
    runner.test(
        "query_employees() returns data",
        len(result.get("data", [])) > 0,
        f"Got {len(result.get('data', []))} employees"
    )

    # Test query_payrolls
    result = await agent.query_payrolls(db_type="postgresql")
    runner.test(
        "query_payrolls() succeeds",
        result.get("success") == True
    )

    # Test query_departments
    result = await agent.query_departments(db_type="mongodb")
    runner.test(
        "query_departments() from MongoDB succeeds",
        result.get("success") == True
    )

    runner.summary()
    return runner.passed, runner.failed


async def test_safety_freeze():
    """Test Safety Checks and Freeze Phase"""
    print("\n[TEST 7] Safety Engine - Freeze Phase")
    print("-" * 60)
    runner = TestRunner()

    agent = DatabaseAgent()

    # First explore
    await agent.explore_schema()

    # Test query works in exploration phase
    result = await agent.query_employees()
    runner.test(
        "Query succeeds in exploration phase",
        result.get("success") == True
    )

    # Freeze operations
    freeze_result = await agent.freeze_operations()
    runner.test(
        "freeze_operations() succeeds",
        freeze_result.get("success") == True
    )

    # Try query in freeze phase
    result = await agent.query_employees()
    runner.test(
        "Query fails in freeze phase",
        result.get("success") == False and "frozen" in result.get("error", "").lower()
    )

    runner.summary()
    return runner.passed, runner.failed


async def test_destructive_blocking():
    """Test Destructive Query Blocking"""
    print("\n[TEST 8] Destructive Query Blocking")
    print("-" * 60)
    runner = TestRunner()

    agent = DatabaseAgent()
    await agent.explore_schema()

    # Test DELETE blocking
    result = await agent.try_destructive_query("delete")
    runner.test(
        "DELETE query is blocked",
        result.get("success") == False and "DELETE" in result.get("blocked_reason", "")
    )

    # Test DROP blocking
    result = await agent.try_destructive_query("drop")
    runner.test(
        "DROP query is blocked",
        result.get("success") == False and "DROP" in result.get("blocked_reason", "")
    )

    # Test UPDATE blocking
    result = await agent.try_destructive_query("update")
    runner.test(
        "UPDATE query is blocked",
        result.get("success") == False and "UPDATE" in result.get("blocked_reason", "")
    )

    runner.summary()
    return runner.passed, runner.failed


async def test_safety_report():
    """Test Safety Report Generation"""
    print("\n[TEST 9] Safety Report and Audit Trail")
    print("-" * 60)
    runner = TestRunner()

    agent = DatabaseAgent()
    await agent.explore_schema()
    await agent.query_employees()
    await agent.query_payrolls()
    await agent.try_destructive_query("delete")

    report = await agent.get_safety_report()

    runner.test(
        "Safety report generated",
        "safety_metrics" in report
    )

    metrics = report.get("safety_metrics", {})
    runner.test(
        "Report shows query count",
        metrics.get("total_queries_attempted", 0) > 0,
        f"Total queries: {metrics.get('total_queries_attempted')}"
    )

    runner.test(
        "Report shows blocked queries",
        metrics.get("blocked_queries", 0) > 0,
        f"Blocked: {metrics.get('blocked_queries')}"
    )

    runner.test(
        "Phase status included",
        "phase_status" in report
    )

    runner.summary()
    return runner.passed, runner.failed


async def run_all_tests():
    """Run all tests"""
    print("\n" + "="*60)
    print("MCPValidator3 - Database Agent Test Suite")
    print("="*60)

    total_passed = 0
    total_failed = 0

    # Synchronous tests
    p, f = test_mock_mongodb()
    total_passed += p
    total_failed += f

    p, f = test_mock_postgresql()
    total_passed += p
    total_failed += f

    p, f = test_query_validation()
    total_passed += p
    total_failed += f

    p, f = test_mongo_operation_validation()
    total_passed += p
    total_failed += f

    # Async tests
    p, f = await test_database_agent_exploration()
    total_passed += p
    total_failed += f

    p, f = await test_database_agent_queries()
    total_passed += p
    total_failed += f

    p, f = await test_safety_freeze()
    total_passed += p
    total_failed += f

    p, f = await test_destructive_blocking()
    total_passed += p
    total_failed += f

    p, f = await test_safety_report()
    total_passed += p
    total_failed += f

    # Final summary
    print("\n" + "="*60)
    print(f"FINAL RESULTS: {total_passed}/{total_passed + total_failed} tests passed")
    print("="*60 + "\n")

    return total_passed, total_failed


if __name__ == "__main__":
    asyncio.run(run_all_tests())
