"""Two-phase test suite for the Database MCP Server.

Phase A — Direct Python tests: verify DatabaseAgent + safety logic works.
Phase B — MCP protocol tests: verify tools are callable via FastMCP Client.
"""
import asyncio
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.database_agent.database_agent import DatabaseAgent
from agents.database_agent.mock_databases import DatabaseManager
from agents.database_agent.safety_checks import QueryValidator, SafetyCheckEngine


# ---------------------------------------------------------------------------
# Simple test runner
# ---------------------------------------------------------------------------

class TestRunner:
    def __init__(self, phase: str):
        self.phase = phase
        self.passed = 0
        self.failed = 0

    def check(self, name: str, condition: bool, detail: str = ""):
        status = "[PASS]" if condition else "[FAIL]"
        print(f"  {status} {name}")
        if detail:
            print(f"        {detail}")
        if condition:
            self.passed += 1
        else:
            self.failed += 1

    def summary(self) -> tuple:
        total = self.passed + self.failed
        print(f"\n  {self.phase}: {self.passed}/{total} passed\n")
        return self.passed, self.failed


# ---------------------------------------------------------------------------
# Phase A — Direct Agent tests (no MCP involved)
# ---------------------------------------------------------------------------

def phase_a_sync_tests() -> tuple:
    """Synchronous safety-layer tests."""
    print("\n" + "=" * 60)
    print("[Phase A] Direct Agent Tests")
    print("=" * 60)

    r = TestRunner("Phase A sync")

    # --- Mock databases ---
    db = DatabaseManager()

    emps = db.mongodb.find("employees")
    r.check("MongoDB find() returns 3 employees", len(emps) == 3, f"got {len(emps)}")

    ahmed = db.mongodb.find_one("employees", {"name": "Ahmed Khan"})
    r.check("MongoDB find_one() filters correctly", ahmed is not None and ahmed["salary"] == 120000)

    schema = db.postgresql.get_schema()
    r.check(
        "PostgreSQL schema has 3 tables",
        all(t in schema for t in ["employees", "payrolls", "departments"])
    )

    pg_emps = db.postgresql.select("employees")
    r.check("PostgreSQL select() returns 3 employees", len(pg_emps) == 3)

    fatima = db.postgresql.select_one("employees", {"name": "Fatima Ali"})
    r.check("PostgreSQL select_one() WHERE works", fatima is not None and fatima["department_id"] == 1)

    # --- SQL safety validator ---
    v = QueryValidator()

    ok, _ = v.is_safe_sql_query("SELECT * FROM employees")
    r.check("SELECT is allowed by validator", ok)

    ok, msg = v.is_safe_sql_query("DELETE FROM employees WHERE id = 1")
    r.check("DELETE is blocked by validator", not ok and "DELETE" in msg)

    ok, msg = v.is_safe_sql_query("DROP TABLE employees")
    r.check("DROP is blocked by validator", not ok and "DROP" in msg)

    ok, msg = v.is_safe_sql_query("UPDATE employees SET salary=0")
    r.check("UPDATE is blocked by validator", not ok and "UPDATE" in msg)

    ok, msg = v.is_safe_sql_query("INSERT INTO employees VALUES (99,'x',1,'x','x',0,'2024-01-01','active')")
    r.check("INSERT is blocked by validator", not ok and "INSERT" in msg)

    # --- MongoDB safety validator ---
    ok, _ = v.is_safe_mongo_operation("find", {})
    r.check("find() is allowed by validator", ok)

    ok, msg = v.is_safe_mongo_operation("deleteOne", {})
    r.check("deleteOne() is blocked by validator", not ok and "deleteOne" in msg)

    ok, msg = v.is_safe_mongo_operation("updateMany", {})
    r.check("updateMany() is blocked by validator", not ok and "updateMany" in msg)

    return r.summary()


async def phase_a_async_tests() -> tuple:
    """Async DatabaseAgent tests."""
    r = TestRunner("Phase A async")

    agent = DatabaseAgent()

    # exploration
    result = await agent.explore_schema()
    r.check("explore_schema() succeeds", result.get("success") is True)
    r.check(
        "explore_schema() returns postgresql_schema",
        "postgresql_schema" in result and len(result["postgresql_schema"]) >= 3
    )
    r.check(
        "explore_schema() returns mongodb_collections",
        "mongodb_collections" in result and len(result["mongodb_collections"]) >= 3
    )
    r.check(
        "schema marked as explored after call",
        result.get("status", {}).get("schema_discovered") is True
    )

    # read queries
    emp = await agent.query_employees("postgresql")
    r.check("query_employees(postgresql) succeeds", emp.get("success") is True)
    r.check("query_employees returns 3 records", emp.get("count") == 3, f"got {emp.get('count')}")

    pay = await agent.query_payrolls(db_type="mongodb")
    r.check("query_payrolls(mongodb) succeeds", pay.get("success") is True)

    dept = await agent.query_departments("postgresql")
    r.check("query_departments(postgresql) succeeds", dept.get("success") is True)

    # destructive blocking
    del_result = await agent.try_destructive_query("delete")
    r.check("try_destructive_query(delete) is blocked", del_result.get("success") is False)

    drop_result = await agent.try_destructive_query("drop")
    r.check("try_destructive_query(drop) is blocked", drop_result.get("success") is False)

    # freeze phase
    freeze = await agent.freeze_operations()
    r.check("freeze_operations() succeeds", freeze.get("success") is True)

    emp_frozen = await agent.query_employees()
    r.check(
        "query_employees() blocked after freeze",
        emp_frozen.get("success") is False and "frozen" in emp_frozen.get("error", "").lower()
    )

    # safety report
    report_agent = DatabaseAgent()
    await report_agent.explore_schema()
    await report_agent.query_employees()
    await report_agent.try_destructive_query("delete")
    report = await report_agent.get_safety_report()
    metrics = report.get("safety_metrics", {})
    r.check("safety_report has metrics", "total_queries_attempted" in metrics)
    r.check("safety_report shows blocked queries", metrics.get("blocked_queries", 0) > 0)

    return r.summary()


# ---------------------------------------------------------------------------
# Phase B — MCP protocol tests (via FastMCP Client)
# ---------------------------------------------------------------------------

async def phase_b_mcp_tests() -> tuple:
    """Test the actual MCP server using FastMCP Client in-process."""
    print("\n" + "=" * 60)
    print("[Phase B] MCP Protocol Tests")
    print("=" * 60)

    r = TestRunner("Phase B MCP")

    try:
        from fastmcp import Client
        # Import the server module to get the mcp instance
        # We re-import to get a fresh agent state for MCP tests
        import importlib
        import agents.database_agent.database_mcp_server as srv_module
        # Reset agent state for clean test
        srv_module._agent = DatabaseAgent()
        mcp_server = srv_module.mcp
    except ImportError as e:
        print(f"  [SKIP] FastMCP Client not available: {e}")
        print("         Install with: pip install fastmcp")
        return 0, 0

    async with Client(mcp_server) as client:

        # --- list tools ---
        tools = await client.list_tools()
        tool_names = {t.name for t in tools}
        expected_tools = {
            "explore_schema", "query_employees", "query_payrolls",
            "query_departments", "execute_sql_query", "execute_mongo_find",
            "freeze_database", "get_safety_report"
        }
        r.check(
            f"MCP server exposes {len(expected_tools)} tools",
            expected_tools.issubset(tool_names),
            f"found: {tool_names}"
        )

        # --- explore_schema ---
        res = await client.call_tool("explore_schema", {})
        content = _extract(res)
        r.check(
            "explore_schema tool returns schema via MCP",
            content.get("success") is True and "postgresql_schema" in content
        )

        # --- query_employees (postgresql) ---
        res = await client.call_tool("query_employees", {"db_type": "postgresql"})
        content = _extract(res)
        r.check(
            "query_employees(postgresql) returns 3 records via MCP",
            content.get("success") is True and content.get("count") == 3,
            f"count={content.get('count')}"
        )

        # --- query_employees (mongodb) ---
        res = await client.call_tool("query_employees", {"db_type": "mongodb"})
        content = _extract(res)
        r.check(
            "query_employees(mongodb) returns records via MCP",
            content.get("success") is True and content.get("count", 0) > 0
        )

        # --- query_payrolls ---
        res = await client.call_tool("query_payrolls", {"db_type": "postgresql"})
        content = _extract(res)
        r.check(
            "query_payrolls returns payroll data via MCP",
            content.get("success") is True and content.get("count", 0) > 0
        )

        # --- query_payrolls filtered by emp_id ---
        res = await client.call_tool("query_payrolls", {"emp_id": "1", "db_type": "postgresql"})
        content = _extract(res)
        r.check(
            "query_payrolls filtered by emp_id=1 returns 1 record",
            content.get("success") is True and content.get("count") == 1
        )

        # --- query_departments ---
        res = await client.call_tool("query_departments", {"db_type": "mongodb"})
        content = _extract(res)
        r.check(
            "query_departments(mongodb) returns data via MCP",
            content.get("success") is True and content.get("count", 0) > 0
        )

        # --- execute_sql_query SAFE ---
        res = await client.call_tool("execute_sql_query", {"query": "SELECT * FROM employees"})
        content = _extract(res)
        r.check(
            "execute_sql_query SELECT * FROM employees is allowed",
            content.get("success") is True and content.get("count") == 3
        )

        # --- execute_sql_query BLOCKED (DELETE) ---
        res = await client.call_tool("execute_sql_query", {"query": "DELETE FROM employees WHERE id=1"})
        content = _extract(res)
        r.check(
            "execute_sql_query DELETE is blocked via MCP",
            content.get("success") is False and content.get("blocked") is True,
            f"reason: {content.get('reason')}"
        )

        # --- execute_sql_query BLOCKED (DROP) ---
        res = await client.call_tool("execute_sql_query", {"query": "DROP TABLE payrolls"})
        content = _extract(res)
        r.check(
            "execute_sql_query DROP is blocked via MCP",
            content.get("success") is False and content.get("blocked") is True
        )

        # --- execute_mongo_find ---
        res = await client.call_tool("execute_mongo_find", {
            "collection": "employees",
            "filter_json": '{"status": "active"}'
        })
        content = _extract(res)
        r.check(
            "execute_mongo_find with filter returns active employees",
            content.get("success") is True and content.get("count", 0) > 0
        )

        # --- execute_mongo_find invalid collection ---
        res = await client.call_tool("execute_mongo_find", {
            "collection": "nonexistent",
            "filter_json": "{}"
        })
        content = _extract(res)
        r.check(
            "execute_mongo_find unknown collection returns error",
            content.get("success") is False and "error" in content
        )

        # --- safety report (should show blocked queries) ---
        res = await client.call_tool("get_safety_report", {})
        content = _extract(res)
        metrics = content.get("safety_metrics", {})
        r.check(
            "get_safety_report shows blocked queries via MCP",
            metrics.get("blocked_queries", 0) >= 2,
            f"blocked={metrics.get('blocked_queries')}"
        )

        # --- freeze_database ---
        res = await client.call_tool("freeze_database", {})
        content = _extract(res)
        r.check(
            "freeze_database succeeds via MCP",
            content.get("success") is True
        )

        # --- queries blocked after freeze ---
        res = await client.call_tool("query_employees", {"db_type": "postgresql"})
        content = _extract(res)
        r.check(
            "query_employees blocked after freeze via MCP",
            content.get("success") is False and "frozen" in content.get("error", "").lower()
        )

        res = await client.call_tool("execute_sql_query", {"query": "SELECT * FROM departments"})
        content = _extract(res)
        r.check(
            "execute_sql_query blocked after freeze via MCP",
            content.get("success") is False and content.get("blocked") is True
        )

    return r.summary()


def _extract(mcp_result) -> dict:
    """Pull the dict payload out of a FastMCP CallToolResult."""
    if mcp_result is None:
        return {}
    # FastMCP 2.x: CallToolResult has .data (already parsed dict) or .structured_content
    if hasattr(mcp_result, "data") and isinstance(mcp_result.data, dict):
        return mcp_result.data
    if hasattr(mcp_result, "structured_content") and isinstance(mcp_result.structured_content, dict):
        return mcp_result.structured_content
    # Fallback: parse first TextContent item
    content = getattr(mcp_result, "content", None)
    if content:
        item = content[0] if isinstance(content, list) else content
        text = getattr(item, "text", None)
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"_raw": text}
    return {}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    print("\n" + "=" * 60)
    print("MCPValidator3 — Database MCP Server Test Suite")
    print("=" * 60)

    total_passed = 0
    total_failed = 0

    # Phase A sync
    p, f = phase_a_sync_tests()
    total_passed += p
    total_failed += f

    # Phase A async
    p, f = await phase_a_async_tests()
    total_passed += p
    total_failed += f

    # Phase B MCP
    p, f = await phase_b_mcp_tests()
    total_passed += p
    total_failed += f

    print("\n" + "=" * 60)
    print(f"FINAL: {total_passed}/{total_passed + total_failed} tests passed")
    print("=" * 60 + "\n")
    return total_failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
