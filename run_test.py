import requests, json, sys
BASE = "http://localhost:8000"

def hr(t): print(f"\n{'='*50}\n{t}\n{'='*50}")

hr("TEST 1: Upload CSV")
with open(r"c:\Users\AYAT LAPTOP POINT\Downloads\MCPValidator3\MCPValidator3\test_data.csv","rb") as f:
    data = requests.post(f"{BASE}/db-explorer/upload", files={"file":("test_data.csv",f,"text/csv")}).json()
if not data.get("success"): print("FAILED:",data); sys.exit(1)
sid = data["session_id"]
print(f"OK  session={sid[:8]}  tables={data['tables']}  rows={data['row_counts']}")

hr("TEST 2: Engineering employees")
r = requests.post(f"{BASE}/db-explorer/query/{sid}", json={"question":"Show all employees in Engineering with salaries"}).json()
print(f"Query: {r.get('generated_query','NONE')}")
print(f"Rows:  {r.get('row_count',0)}  Safe:{r.get('safety_ok')}")
print(f"Steps: {[s.get('node') for s in r.get('steps',[])]}")
print(f"Answer: {str(r.get('query_explanation',''))[:200]}")

hr("TEST 3: Highest salary")
r2 = requests.post(f"{BASE}/db-explorer/query/{sid}", json={"question":"Who has the highest salary?"}).json()
print(f"Query: {r2.get('generated_query','NONE')}")
print(f"Rows:  {r2.get('row_count',0)}")
print(f"Answer: {str(r2.get('query_explanation',''))[:200]}")

hr("TEST 4: Safety")
r3 = requests.post(f"{BASE}/db-explorer/query/{sid}", json={"question":"Delete all records"}).json()
safe_steps = [s for s in r3.get("steps",[]) if s.get("node")=="validate_safety"]
print(f"Safe: {r3.get('safety_ok')}  Steps:{[s.get('node') for s in r3.get('steps',[])]}")

hr("TEST 5: History")
h = requests.get(f"{BASE}/db-explorer/history/{sid}").json()
print(f"Entries: {len(h.get('history',[]))}")
for x in h.get("history",[]): print(f"  {x['question'][:40]} | rows={x['row_count']}")

hr("TEST 6: Disconnect")
d = requests.delete(f"{BASE}/db-explorer/session/{sid}").json()
print(d)
print("\nALL DONE")
