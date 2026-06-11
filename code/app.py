"""
app.py  —  Agentic Bug Hunter Web Server
Run:
    winenv\Scripts\activate
    cd code
    python app.py
Open: http://localhost:5000
"""

import os, sys, json, time, queue, threading
from pathlib import Path
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

_api_key = os.getenv("GROQ_API_KEY", "")
if not _api_key or "your_actual_key" in _api_key:
    print("ERROR: GROQ_API_KEY not set in .env")
    sys.exit(1)

from groq import Groq
from mcp_client import search_documents   # uses permanent-loop version

_groq      = Groq(api_key=_api_key)
GROQ_MODEL = "llama-3.3-70b-versatile"

app = Flask(__name__, template_folder="../templates", static_folder="../static")


# ── LLM call (Groq) ───────────────────────────────────────────────────────────

def call_llm(prompt: str, expect_json: bool = False) -> str:
    system = (
        "You are an expert C++ code reviewer specializing in hardware test RDI APIs. "
        "Be precise and follow instructions exactly."
        + (" Respond ONLY with valid JSON — no markdown, no extra text." if expect_json else "")
    )
    for attempt in range(3):
        try:
            resp = _groq.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0.1,
                max_tokens=400,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            err = str(e)
            if "429" in err or "rate_limit" in err.lower():
                wait = 15 * (attempt + 1)
                print(f"  [Groq rate-limit] waiting {wait}s...")
                time.sleep(wait)
            elif "401" in err:
                print("  [Groq] Invalid API key.")
                sys.exit(1)
            else:
                print(f"  [Groq error] {err}")
                if attempt == 2:
                    return ""
                time.sleep(3)
    return ""


# ── Agent pipeline ────────────────────────────────────────────────────────────

def run_pipeline(code: str, context: str, emit) -> dict:

    # ── Agent 1: Parser ───────────────────────────────────────────────────────
    emit("parser", "Parsing code and numbering lines...")
    lines        = code.split("\n")
    numbered     = "\n".join(f"{i+1:3}: {l}" for i, l in enumerate(lines))
    total        = len(lines)
    emit("parser", f"✓ {total} lines parsed")

    # ── Agent 2: Retriever ────────────────────────────────────────────────────
    emit("retriever", "Querying MCP documentation server...")
    seen, chunks = set(), []

    # Two query angles for better recall
    for q in [context.strip(), context.strip().split(".")[0]]:
        if not q:
            continue
        for r in search_documents(q)[:6]:          # ← permanent loop, never hangs
            t = r.get("text", "").strip()
            if t and t not in seen:
                seen.add(t)
                chunks.append(t)

    docs = "\n\n---\n\n".join(chunks[:5]) if chunks else "No documentation retrieved."
    emit("retriever", f"✓ Retrieved {len(chunks)} documentation chunks")

    # ── Agent 3: Detector ─────────────────────────────────────────────────────
    emit("detector", "Asking Groq LLM to find the bug line...")

    det_prompt = f"""You are analyzing C++ code that uses a hardware test RDI API.

CONTEXT: {context}

CODE WITH LINE NUMBERS:
{numbered}

RELEVANT API DOCUMENTATION:
{docs}

Find the single line number containing the bug.
Bugs: wrong enum/constant, wrong method name, wrong argument, wrong call order,
mismatched port/pin name, wrong mode constant, missing/extra call.
Use the documentation to verify correct usage.

Respond with ONLY this JSON and nothing else:
{{"bug_line": <integer 1 to {total}>}}"""

    raw = call_llm(det_prompt, expect_json=True)
    bug_line = 1
    if raw:
        clean = raw.replace("```json","").replace("```","").strip()
        try:
            bug_line = max(1, min(int(json.loads(clean)["bug_line"]), total))
        except Exception:
            for token in clean.split():
                t = token.strip("{}:,\"'")
                if t.isdigit() and 1 <= int(t) <= total:
                    bug_line = int(t)
                    break
    emit("detector", f"✓ Bug detected on line {bug_line}")

    # ── Agent 4: Explainer ────────────────────────────────────────────────────
    emit("explainer", "Generating explanation...")

    exp_prompt = f"""You are writing a bug report for C++ hardware test code.

CONTEXT: {context}

CODE:
{numbered}

BUG IS ON LINE {bug_line}.

DOCUMENTATION:
{docs}

Write ONE plain-text sentence (max 50 words):
1. What is wrong on line {bug_line}
2. What the correct value/method/order should be
3. Which documentation rule is violated

Plain text only — no markdown, no bullet points."""

    explanation = call_llm(exp_prompt, expect_json=False)
    explanation = explanation.replace("**","").replace("*","").replace("\n"," ").strip()
    if len(explanation) > 350:
        explanation = explanation[:347] + "..."
    if not explanation:
        explanation = "Bug detected on the specified line."
    emit("explainer", "✓ Explanation generated")

    return {
        "bug_line":      bug_line,
        "explanation":   explanation,
        "numbered_code": numbered,
        "total_lines":   total,
    }


# ── Flask routes ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    data    = request.get_json(force=True)
    code    = data.get("code", "").strip()
    context = data.get("context", "").strip()

    if not code:
        return jsonify({"error": "Code is required"}), 400
    if not context:
        context = "C++ hardware test RDI API code"

    q = queue.Queue()

    def emit(stage: str, message: str):
        q.put({"stage": stage, "message": message})

    def run():
        try:
            result = run_pipeline(code, context, emit)
            q.put({"done": True, **result})
        except Exception as e:
            import traceback
            traceback.print_exc()
            q.put({"error": str(e)})

    threading.Thread(target=run, daemon=True).start()

    def stream():
        while True:
            try:
                event = q.get(timeout=120)        # 2 min total max
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("done") or event.get("error"):
                    break
            except queue.Empty:
                yield 'data: {"error": "Pipeline timed out — is MCP server running?"}\n\n'
                break

    return Response(
        stream_with_context(stream()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    print("\n" + "="*55)
    print("  Agentic Bug Hunter — Web Interface")
    print("  Open : http://localhost:5000")
    print("  Needs: MCP server running on port 8003")
    print("="*55 + "\n")
    app.run(debug=False, host="0.0.0.0", port=5000, threaded=True)
