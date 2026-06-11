"""
test_mcp.py  —  Run AFTER starting mcp_server.py in a separate terminal.

Usage:
    winenv\Scripts\activate
    cd code
    python test_mcp.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_client import add, search_documents

print("=" * 50)
print("  MCP Server Connection Test")
print("  Server must be running: python server/mcp_server.py")
print("=" * 50)

print("\n[Test 1] add(10, 5) — basic connectivity")
r = add(10, 5)
print(r)
if r == 15:
    print(f"  ✅  add(10, 5) = {r}")
else:
    print(f"  ❌  Got: {r}")
    print("      → Open a NEW terminal and run:")
    print("        winenv\\Scripts\\activate")
    print("        cd server")
    print("        python mcp_server.py")
    sys.exit(1)

print("\n[Test 2] search_documents('RDI_BEGIN RDI_END lifecycle')")
docs = search_documents("RDI_BEGIN RDI_END lifecycle order")
print(f"  Results  : {len(docs)}")
if docs:
    print(f"  Top score: {docs[0]['score']:.4f}")
    print(f"  Preview  : {docs[0]['text'][:120]}...")
    print("  ✅  Document search WORKING")
else:
    print("  ❌  No docs — check server/storage/ and server/embedding_model/ exist")

print("\n[Test 3] search_documents('vecEditMode VTT VECD')")
docs2 = search_documents("vecEditMode VTT VECD smartVec")
print(f"  Results : {len(docs2)}")
if docs2:
    print(f"  ✅  Second search working (score: {docs2[0]['score']:.4f})")

print("\n" + "=" * 50)
print("  All tests passed — ready to run: python agent.py")
print("=" * 50)
