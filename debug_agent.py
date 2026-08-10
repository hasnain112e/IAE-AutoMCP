"""Direct test of ExplorerAgent outside the API server."""
import sys, io, csv, uuid, traceback
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()

try:
    from agents.db_explorer.connectors import connector_factory
    from agents.db_explorer.explorer_agent import ExplorerAgent

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerows([
        ["name", "department", "salary"],
        ["Alice", "Engineering", 90000],
        ["Bob", "Marketing", 70000],
        ["Carol", "Engineering", 95000],
        ["Dave", "Engineering", 85000],
        ["Eve", "HR", 65000],
    ])
    content = buf.getvalue().encode()

    conn = connector_factory("file", filename="test.csv", content=content)
    conn.connect()
    print("Connected, tables:", list(conn.get_schema().keys()))

    sid = str(uuid.uuid4())
    agent = ExplorerAgent(conn, sid)
    schema = agent.explore_schema()
    print("Schema explored:", schema["tables"])

    print("\n--- Running NL query ---")
    result = agent.query("Show all employees in Engineering with salaries")
    print("Success:", result.get("success"))
    print("Query:", result.get("generated_query"))
    print("Rows:", result.get("row_count"))
    print("Steps:", [s.get("node") for s in result.get("steps", [])])
    print("Answer:", str(result.get("query_explanation", ""))[:300])

except Exception as e:
    print("ERROR:", e)
    traceback.print_exc()
