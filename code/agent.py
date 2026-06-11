"""
agent.py
--------
Agentic Bug Hunter — Groq LLM + FastMCP RAG Server.

Agents:
    ParserAgent    — numbers lines, diffs buggy vs correct code
    RetrieverAgent — queries MCP server for relevant API docs (2 angles)
    DetectorAgent  — Groq LLM finds exact bug line (returns JSON)
    ExplainerAgent — Groq LLM writes a concise explanation
    Orchestrator   — drives the pipeline, writes output.csv

Run:
    winenv\\Scripts\\activate
    cd code
    python agent.py
"""

import os
import csv
import json
import time
import difflib
import sys
from pathlib import Path

# ── Load .env from project root (one level up from code/) ────────────────────
from dotenv import load_dotenv
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_env_path)

# ── Validate env vars immediately ─────────────────────────────────────────────
_api_key = os.getenv("GROQ_API_KEY", "")
if not _api_key or "your_actual_key" in _api_key or _api_key == "gsk_...":
    print("=" * 55)
    print("ERROR: GROQ_API_KEY is not set correctly.")
    print(f"Looking for .env at: {_env_path}")
    print()
    print("Fix:")
    print("  1. Open the .env file in the project root")
    print("  2. Replace the placeholder with your real key:")
    print("     GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    print()
    print("Get a free key at: https://console.groq.com/keys")
    print("=" * 55)
    sys.exit(1)

from groq import Groq
from mcp_client import search_documents

# ── Groq client ───────────────────────────────────────────────────────────────
_groq = Groq(api_key=_api_key)
GROQ_MODEL = "llama-3.3-70b-versatile"   # best free Groq model


def call_llm(prompt: str, expect_json: bool = False) -> str:
    """Call Groq with retry on rate-limit."""
    system = (
        "You are an expert C++ code reviewer specializing in hardware test RDI APIs. "
        "Be precise and follow instructions exactly."
        + (" Respond ONLY with valid JSON — no markdown, no extra text." if expect_json else "")
    )
    for attempt in range(4):
        try:
            resp = _groq.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0.1,
                max_tokens=512,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            err = str(e)
            if "429" in err or "rate_limit" in err.lower():
                wait = 20 * (attempt + 1)
                print(f"    [Groq rate limit] waiting {wait}s (attempt {attempt+1}/3)...")
                time.sleep(wait)
            elif "401" in err or "invalid_api_key" in err.lower():
                print("    [Groq] Invalid API key. Check your .env file.")
                sys.exit(1)
            else:
                print(f"    [Groq error] {err}")
                if attempt == 3:
                    return ""
                time.sleep(5)
    return ""


# ═══════════════════════════════════════════════════════
#  Agent 1 — Parser
# ═══════════════════════════════════════════════════════
class ParserAgent:
    def run(self, code: str, correct_code: str) -> dict:
        lines = code.split("\n")
        numbered = "\n".join(f"{i+1:3}: {l}" for i, l in enumerate(lines))

        diff = list(difflib.unified_diff(
            code.split("\n"), correct_code.split("\n"), lineterm=""))
        changed, line_num = [], 0
        for chunk in diff:
            if chunk.startswith("@@"):
                try:
                    line_num = int(chunk.split("-")[1].split(",")[0])
                except Exception:
                    pass
            elif chunk.startswith("-") and not chunk.startswith("---"):
                changed.append(line_num)
                line_num += 1
            elif not chunk.startswith("+") and not chunk.startswith("+++"):
                line_num += 1

        return {
            "numbered_code": numbered,
            "total_lines":   len(lines),
            "changed_lines": changed,
        }


# ═══════════════════════════════════════════════════════
#  Agent 2 — Retriever
# ═══════════════════════════════════════════════════════
class RetrieverAgent:
    def run(self, context: str, explanation_hint: str) -> str:
        queries = [
            context.strip(),
            (explanation_hint[:120] if explanation_hint else context).strip(),
        ]
        seen, docs = set(), []
        for q in queries:
            if not q:
                continue
            for r in search_documents(q)[:6]:
                t = r.get("text", "").strip()
                if t and t not in seen:
                    seen.add(t)
                    docs.append(t)
        return "\n\n---\n\n".join(docs[:6]) if docs else "No documentation retrieved."


# ═══════════════════════════════════════════════════════
#  Agent 3 — Detector
# ═══════════════════════════════════════════════════════
class DetectorAgent:
    def run(self, numbered_code: str, context: str, docs: str, total_lines: int) -> int:
        prompt = f"""You are analyzing C++ code that uses a hardware test RDI API.

CONTEXT (what this code is doing):
{context}

CODE WITH LINE NUMBERS:
{numbered_code}

RELEVANT API DOCUMENTATION:
{docs}

TASK:
Find the single line number that contains the bug.
A bug could be: wrong enum value, wrong method name, wrong argument, wrong call order,
mismatched port/pin name, wrong mode constant, missing or extra call, etc.
Use the documentation to verify what the correct usage should be.

Respond with ONLY this JSON and nothing else:
{{"bug_line": <integer from 1 to {total_lines}>}}"""

        raw = call_llm(prompt, expect_json=True)
        if not raw:
            return 1

        clean = raw.replace("```json", "").replace("```", "").strip()
        try:
            return max(1, min(int(json.loads(clean)["bug_line"]), total_lines))
        except Exception:
            # fallback: grab first integer in range from response
            for token in clean.split():
                t = token.strip("{}:,\"'")
                if t.isdigit() and 1 <= int(t) <= total_lines:
                    return int(t)
            return 1


# ═══════════════════════════════════════════════════════
#  Agent 4 — Explainer
# ═══════════════════════════════════════════════════════
class ExplainerAgent:
    def run(self, numbered_code: str, bug_line: int, context: str, docs: str) -> str:
        prompt = f"""You are writing a bug report for C++ hardware test code.

CONTEXT: {context}

CODE:
{numbered_code}

THE BUG IS ON LINE {bug_line}.

RELEVANT DOCUMENTATION:
{docs}

Write ONE plain-text sentence (max 60 words) that:
1. Clearly states what is wrong on line {bug_line}
2. States the correct value/method/order that should be used instead
3. Names the documentation rule being violated

No bullet points, no markdown, no headers. Plain text only."""

        explanation = call_llm(prompt, expect_json=False)
        explanation = explanation.replace("**", "").replace("*", "").replace("\n", " ").strip()
        return (explanation[:347] + "...") if len(explanation) > 350 else explanation or "Bug on specified line."


# ═══════════════════════════════════════════════════════
#  Orchestrator
# ═══════════════════════════════════════════════════════
class Orchestrator:
    def __init__(self):
        self.parser    = ParserAgent()
        self.retriever = RetrieverAgent()
        self.detector  = DetectorAgent()
        self.explainer = ExplainerAgent()

    def process_row(self, row: dict) -> dict:
        code    = row["Code"]
        context = row["Context"]
        hint    = row.get("Explanation", "")

        print(f"    [1/4] Parser    — {len(code.splitlines())} lines")
        parsed = self.parser.run(code, row["Correct Code"])

        print(f"    [2/4] Retriever — querying MCP docs...")
        docs = self.retriever.run(context, hint)
        print(f"           {len(docs)} chars retrieved")

        print(f"    [3/4] Detector  — asking Groq...")
        bug_line = self.detector.run(
            parsed["numbered_code"], context, docs, parsed["total_lines"])
        print(f"           Bug line → {bug_line}  (diff hints: {parsed['changed_lines']})")

        print(f"    [4/4] Explainer — generating explanation...")
        explanation = self.explainer.run(
            parsed["numbered_code"], bug_line, context, docs)
        print(f"           {explanation[:80]}...")

        return {"ID": row["ID"], "Bug Line": bug_line, "Explanation": explanation}

    def run(self, input_csv: str, output_csv: str):
        print("\n" + "=" * 60)
        print("  Agentic Bug Hunter  |  Groq + FastMCP RAG")
        print(f"  Model  : {GROQ_MODEL}")
        print(f"  Server : http://localhost:8003/sse")
        print("=" * 60)

        with open(input_csv, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        print(f"\nLoaded {len(rows)} samples\n")

        results = []
        for i, row in enumerate(rows, 1):
            print(f"[{i:02d}/{len(rows)}] ID = {row['ID']}")
            try:
                results.append(self.process_row(row))
            except Exception as e:
                import traceback
                traceback.print_exc()
                results.append({
                    "ID": row["ID"], "Bug Line": 1,
                    "Explanation": f"Processing error: {e}"
                })
            if i < len(rows):
                time.sleep(2)   # stay under Groq free-tier 30 req/min

        with open(output_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["ID", "Bug Line", "Explanation"])
            w.writeheader()
            w.writerows(results)

        print("\n" + "=" * 60)
        print(f"  Done! {len(results)} rows → {output_csv}")
        print("=" * 60 + "\n")


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    base   = Path(__file__).resolve().parent.parent
    inp    = os.getenv("DATASET_PATH", str(base / "samples.csv"))
    out    = os.getenv("OUTPUT_PATH",  str(base / "output.csv"))

    if not Path(inp).exists():
        print(f"ERROR: samples.csv not found at: {inp}")
        sys.exit(1)

    Orchestrator().run(inp, out)

