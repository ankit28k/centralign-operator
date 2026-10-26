# CentrAlign AI — Autonomous Enterprise Operator & Task Worker

An end-to-end prototype of an **Autonomous AI Employee & Computer-Use Runtime** designed for both the **Founding Engineer** and **AI Engineering Intern** problem statements at CentrAlign AI.

Rather than mocking tool execution or returning text-only plans, this system operates a real Chromium browser via Playwright, inspects local enterprise file systems, consults persistent organizational memory (SOPs & learned rules), enforces hard Human-in-the-Loop governance gates with state checkpointing, recovers from live DOM validation and transient server errors (`HTTP 503`), and independently verifies final outcomes with visual screenshot evidence.

---

## 1. Core Operational Loop

The runtime implements a stateful, resumable execution loop:

```text
GOAL ──► UNDERSTAND ──► PLAN ──► EXECUTE ──► OBSERVE ──► ADAPT ──► VERIFY ──► COMPLETE
            │                       │           │          │          │
     [Company SOP &         [Governance Gate]   └──► [Save Learning]  └──► [DOM + Screenshot
    Procedural Memory]      (Pause / Resume)         to Memory JSON         Audit Evidence]
```

### How One Unified Architecture Addresses Both Roles

| Capability | AI Engineering Intern Scope | Founding Engineer Scope |
| :--- | :--- | :--- |
| **Task Execution** | End-to-end execution of natural language requests across local files (`./workspace/invoices/`) and web applications (`http://127.0.0.1:8000`). | Stateful, checkpointed agent runtime capable of pausing at policy gates and resuming from serialized disk state (`workspace/checkpoint.json`). |
| **Context & Memory** | Maintains working state across multi-step extraction and browser navigation. | Combines declarative Company SOP (`company_sop.md`) with self-updating Persistent Procedural Memory (`procedural_memory.json`) so the AI employee learns from failures across runs. |
| **Failure Recovery** | Detects `ERP_VALIDATION_ERROR` (e.g., date format mismatch `DD/MM/YYYY` vs `YYYY-MM-DD`) and `HTTP_503_TRANSIENT_DB_LOCK` in live DOM banners, adapting inputs and retrying automatically. | Persists discovered environment constraints into organizational memory so subsequent runs never repeat the same formatting error. |
| **Governance & Verification** | Queries live ledger table `#ledger-table` to confirm completion before finishing. | Enforces hard financial approval thresholds (pausing execution when Invoice Total > $5,000) and generates an immutable Audit Trail (`audit_trail.json`) + full-page Verification Screenshot (`workspace/evidence/`). |

---

## 2. System Architecture

```plaintext
centralign-operator/
├── setup_workspace.py   # Initializes Company SOP, raw vendor invoices, and procedural memory store
├── erp_sandbox.py       # Target Enterprise Web App (FastAPI + SQLite) with validation & 503 chaos modes
├── tools.py             # Computer-Use Layer: Playwright Browser Controller, Semantic DOM Extractor, File & Memory Tools
├── agent_runtime.py     # Core State Machine Runtime (Gemini 3 Flash + Deterministic Fallback Reasoner)
└── app.py               # Streamlit Operator Console (Live Trace, Approval Gate UI, Evidence Packet Viewer)
```

---

## 3. Setup & Run Instructions

### Prerequisites
- Python 3.10+
- Google Gemini API Key (`GEMINI_API_KEY`) — *Note: The runtime also includes a built-in deterministic fallback reasoning engine so the system can be tested offline or if API rate limits occur.*

### Installation

```bash
git clone <your-repo-url>
cd centralign-operator
python3 -m venv venv
source venv/bin/activate

pip install fastapi uvicorn playwright pydantic google-genai openai streamlit requests
playwright install chromium
```

### Running the Prototype (2 Terminals)

**Terminal 1 — Start the Target Enterprise ERP Sandbox (Port 8000):**
```bash
python setup_workspace.py
python erp_sandbox.py
```

**Terminal 2 — Launch the Live Operator Console (Port 8501):**
```bash
export GEMINI_API_KEY="your-gemini-api-key"
streamlit run app.py
```

*(Alternatively, run `python agent_runtime.py` to execute the full end-to-end flow directly in the CLI).*

---

## 4. Key Technical & Design Decisions

- **Semantic DOM Distillation Over Raw HTML Dumps (`tools.py`):**
  Feeding raw HTML into an LLM wastes context tokens and causes hallucinated selectors. `BrowserSession.get_semantic_dom()` executes an in-browser JS extraction that distills the live page into actionable inputs, buttons, status banners (`#status-banner`), and structured table rows (`#ledger-table`).

- **Self-Healing Procedural Memory (`procedural_memory.json`):**
  Raw vendor invoices contain dates in `DD/MM/YYYY` format (`15/11/2026`), whereas the legacy ERP strictly requires ISO `YYYY-MM-DD` (`2026-11-15`). On its first run, the agent observes the DOM validation error, adapts the date format, and calls `save_organizational_learning`. On all subsequent runs, the agent reads this learned rule during the UNDERSTAND phase and formats dates correctly on the first try.

- **Serialized Checkpointing for Human-in-the-Loop (`checkpoint.json`):**
  Rather than blocking a thread while waiting for human input, `request_human_approval` serializes the runtime state, message transcript, and audit trace to disk and cleanly yields control. When a manager clicks Approve in the UI, the runtime rehydrates from `checkpoint.json` and completes execution.

- **Decoupled Outcome Verification (`verify_invoice_in_ledger`):**
  An HTTP 200 or form click does not guarantee business completion. The runtime prohibits calling `complete_task` until `verify_invoice_in_ledger` independently inspects the live DOM table, confirms the specific `invoice_id` has status `PROCESSED`, and captures a full-page PNG screenshot as audit evidence.

- **Hybrid Reasoning Resilience (`gemini-3-flash-preview` + Deterministic Policy Fallback):**
  Cloud LLM APIs can experience transient 503 UNAVAILABLE spikes. `AutonomousOperatorRuntime` pairs `gemini-3-flash-preview` structured JSON generation with a deterministic policy fallback engine so live browser execution never stalls mid-workflow.

---

## 5. Models, Frameworks & Components Used

- **LLM:** Google Gemini (`gemini-3-flash-preview` via `google-genai` SDK) with structured JSON output enforcement; optional OpenAI/Groq support.
- **Browser Automation / Computer Use:** Playwright (`playwright.sync_api` driving Chromium).
- **Target Enterprise Sandbox:** FastAPI + Uvicorn + SQLite3 (`erp_sandbox.py`).
- **Operator Control Plane UI:** Streamlit (`app.py`).

---

## 6. Assumptions Made

- Enterprise workflows are governed by an explicit or discoverable set of Standard Operating Procedures (`company_sop.md`) that define system URLs, credentials, routing logic, and financial escalation thresholds.
- Incoming vendor artifacts arrive in a designated shared directory (`./workspace/invoices/`) and may include already-processed historical files (`globex_sep_2026.txt`) alongside pending files (`globex_oct_2026.txt`).
- Browser sessions may disconnect between long-running human approval pauses; therefore, tools must transparently re-verify session state on resume.

---

## 7. Known Limitations

- **DOM-Scoped Computer Use:** Browser interaction currently relies on DOM selectors extracted via `get_semantic_dom()` rather than pixel-level Vision/GUI coordinate clicking for native OS desktop apps.
- **Single-Worker Sequential Execution:** The prototype executes one task loop at a time using local JSON state files rather than a distributed task queue.
- **File Format Scope:** Sample invoices are structured text documents; multi-page scanned PDFs with complex tables would require an OCR/VLM document parsing stage.

---

## 8. What I Would Build Next (Production Roadmap)

- **Vision + OS-Level Desktop Grounding:** Combine Playwright DOM trees with multimodal screenshot grounding to operate non-browser desktop applications (e.g., legacy Windows ERPs, Excel macros).
- **Durable Distributed Execution Engine:** Migrate JSON checkpointing to Temporal or Celery + Redis + Postgres so thousands of long-running agent workflows can pause for days awaiting Slack/Email approvals and resume reliably.
- **Graph-Backed Organizational Memory:** Upgrade `procedural_memory.json` into a hybrid Vector + Knowledge Graph store (pgvector / Neo4j) scoped by tenant, department, and application, with confidence scoring and human review of learned rules.
- **Shadow Mode & Counterfactual Evaluation Suite:** Allow new AI employees to run in "Shadow Mode" alongside human operators, comparing proposed agent actions against actual human actions before granting autonomous write permissions.
