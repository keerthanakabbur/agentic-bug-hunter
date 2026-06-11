# 🐛 Agentic Bug Hunter — Groq + MCP + Windows Guide

## Project Structure
```
agentic_bug_hunter/
│
├── .env.example        ← Copy to .env and add your Groq key
├── requirements.txt    ← All pip packages
├── samples.csv         ← Dataset (already here)
├── output.csv          ← Generated after running agent.py
│
├── server/
│   ├── mcp_server.py       ← MCP server (given by organizers)
│   ├── embedding_model/    ← From organizers (BAAI/bge-base-en-v1.5)
│   └── storage/            ← From organizers (vector index)
│
└── code/
    ├── agent.py        ← Main 4-agent system (uses Groq)
    ├── mcp_client.py   ← Talks to MCP server via HTTP
    ├── test_mcp.py     ← Verify MCP server is working
    └── test_groq.py    ← Verify Groq API key is working
```

---

## Step 1 — Get Your FREE Groq API Key

1. Go to → **https://console.groq.com/keys**
2. Sign up (free, no credit card)
3. Click **"Create API Key"** → copy the key (starts with `gsk_`)

**Why Groq?**
- Completely free
- 30 requests/minute, 14,400/day
- `llama-3.3-70b-versatile` is extremely fast and accurate
- No billing setup required

---

## Step 2 — Install Dependencies into your winenv

```cmd
REM Activate your existing virtual environment
winenv\Scripts\activate

REM Install all packages
pip install -r requirements.txt
```

---

## Step 3 — Create your .env file

In the project root folder, create a file named exactly `.env` (no other extension):

```
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
MCP_SERVER_URL=http://localhost:8003
DATASET_PATH=samples.csv
OUTPUT_PATH=output.csv
```

> **Windows tip:** In File Explorer, name it `.env` — Windows may warn about
> "no file extension", just click Yes.

---

## Step 4 — Place the organizer files

The MCP server needs two folders that the organizers provide:

```
server\embedding_model\     ← BAAI/bge-base-en-v1.5 model files
server\storage\             ← pre-built vector index
```

Copy `mcp_server.py` into the `server\` folder as well.

---

## Step 5 — Test Groq API Key

```cmd
winenv\Scripts\activate
cd code
python test_groq.py
```

Expected output:
```
✅  Groq is working! Ready to run agent.py
```

---

## Step 6 — Start the MCP Server (Terminal 1 — keep open)

```cmd
winenv\Scripts\activate
cd server
python mcp_server.py
```

Expected output:
```
Current working directory: ...\server
The directory './embedding_model' exists.
Starting MCP Server....
```

Leave this terminal open. The server runs on **port 8003**.

---

## Step 7 — Test MCP Connection (Terminal 2)

```cmd
winenv\Scripts\activate
cd code
python test_mcp.py
```

Expected output:
```
✅  add(10, 5) = 15 — server is reachable!
✅  Document search WORKING
✅  All tests complete — ready to run agent.py!
```

---

## Step 8 — Run the Bug Hunter Agent (Terminal 2)

```cmd
winenv\Scripts\activate
cd code
python agent.py
```

It processes all 20 rows. Expected output per row:
```
[01/20] ID=16
    → [Parser] numbering 13 lines
    → [Retriever] querying MCP server...
       1842 chars of docs retrieved
    → [Detector] asking Groq for bug line...
       Bug line: 1  (diff hints: [1])
    → [Explainer] generating explanation...
       Line 1 uses TA::VECD but the documentation states...

✅  Done! 20 rows written to: output.csv
```

---

## Output

`output.csv` will look like:
```
ID,Bug Line,Explanation
16,1,Line 1 uses TA::VECD instead of TA::VTT; the documentation states VTT mode is required when copyLabel() is used in smartVec().
25,6,RDI_END() is called before RDI_BEGIN() on line 6; the correct lifecycle order per documentation is RDI_BEGIN() first.
```

---

## Submission Package

```cmd
REM From the project root
powershell Compress-Archive -Path output.csv,requirements.txt,code -DestinationPath TeamName_Submission.zip
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `winenv\Scripts\activate` fails | Run as Administrator or check path |
| `ModuleNotFoundError: groq` | Run `pip install groq` inside winenv |
| `GROQ_API_KEY not set` | Check `.env` is in project root, not inside `code\` |
| MCP `Connection refused` | Start `mcp_server.py` in Terminal 1 first |
| `storage/ not found` error in server | Get `storage/` and `embedding_model/` from organizers |
| Groq `429` rate limit | Agent auto-waits and retries — just let it run |
| `Event loop is closed` (Windows) | Fixed automatically in `mcp_client.py` |
