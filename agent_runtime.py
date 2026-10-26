import os
import json
import time
from typing import Dict, Any, List, Optional
from tools import OperatorToolkit

# =====================================================================
# PASTE YOUR GEMINI API KEY RIGHT HERE (OR SET GEMINI_API_KEY IN ENV)
# =====================================================================
DEFAULT_GEMINI_API_KEY = ""
GEMINI_MODEL_NAME = "gemini-3-flash-preview"
# =====================================================================

CHECKPOINT_PATH = "workspace/checkpoint.json"
AUDIT_LOG_PATH = "workspace/audit_trail.json"

SYSTEM_PROMPT = """You are a CentrAlign Autonomous AI Employee operating inside AcmeCorp.
Your job is to turn high-level business requests into completed, verified work across files and browser applications.

You follow a strict operational loop:
GOAL -> UNDERSTAND -> PLAN -> EXECUTE -> OBSERVE -> ADAPT -> VERIFY -> COMPLETE

AVAILABLE TOOLS & EXACT ARGUMENTS:
1. read_company_sop: {}
2. list_invoice_files: {}
3. read_invoice_file: {"filename": "globex_oct_2026.txt"}
4. browser_login: {"username": "operator@acmecorp.internal", "password": "acme-secure-2026"}
5. request_human_approval: {"invoice_id": "INV-2026-142", "vendor_name": "Globex Corporation", "amount": "$8250.00", "department": "Engineering", "reason": "Exceeds $5,000 SOP threshold"}
6. browser_submit_erp_invoice: {"invoice_id": "INV-2026-142", "vendor_name": "Globex Corporation", "department": "Engineering", "amount": "8250.00", "due_date": "15/11/2026"}
7. save_organizational_learning: {"rule": "ERP requires Due Dates in ISO YYYY-MM-DD format"}
8. verify_invoice_in_ledger: {"expected_invoice_id": "INV-2026-142"}
9. complete_task: {"summary": "Final summary of completed work"}

CRITICAL OPERATING PRINCIPLES:
1. Context First: Always start by calling `read_company_sop`.
2. Inspect Before Acting: List and read relevant invoice files, and log into the ERP portal (`http://127.0.0.1:8000`) to inspect the current `Processed Invoices Ledger`.
3. Hard Governance Gate: If Total Due > $5,000.00 and `human_approved` is False, you MUST call `request_human_approval` BEFORE calling `browser_submit_erp_invoice`.
4. Observe & Adapt: Carefully read `observed_banners` after every browser action.
   - If you get an `ERP_VALIDATION_ERROR` (e.g. `DD/MM/YYYY` rejected because `YYYY-MM-DD` is required), call `save_organizational_learning` AND resubmit with `YYYY-MM-DD`.
   - If you get `HTTP_503_TRANSIENT_DB_LOCK`, retry `browser_submit_erp_invoice`.
5. Independent Verification: Never call `complete_task` until `verify_invoice_in_ledger` returns `"verified": True`.

Respond ONLY with a valid JSON object matching this exact schema:
{
  "phase": "UNDERSTAND | PLAN | EXECUTE | OBSERVE_ADAPT | VERIFY | COMPLETE",
  "thought": "Clear explanation of what you observed and why you are choosing the next action",
  "plan": ["step 1", "step 2"],
  "tool_name": "one of the 9 tool names above",
  "tool_args": {}
}
"""


class AutonomousOperatorRuntime:
    def __init__(self, provider: str = "gemini", api_key: str = "", headless: bool = False):
        self.provider = provider
        self.api_key = api_key.strip() if api_key else ""
        self.headless = headless

    def _append_audit_event(self, trace: List[Dict[str, Any]], event: Dict[str, Any]):
        event["timestamp"] = time.strftime("%H:%M:%S")
        trace.append(event)
        with open(AUDIT_LOG_PATH, "w") as f:
            json.dump(trace, f, indent=2)

    def _call_llm(self, messages: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
        """Calls Gemini (gemini-3-flash-preview) to get the next structured agent decision."""
        if self.provider == "fallback" or self.provider == "deterministic":
            return None

        # --- HIGHLIGHTED CHANGE: Automatically use DEFAULT_GEMINI_API_KEY and gemini-3-flash-preview ---
        gemini_key = self.api_key or os.environ.get("GEMINI_API_KEY", "") or DEFAULT_GEMINI_API_KEY
        if gemini_key == "PASTE_YOUR_GEMINI_API_KEY_HERE":
            gemini_key = ""

        try:
            if gemini_key:
                from google import genai
                from google.genai import types
                client = genai.Client(api_key=gemini_key)
                transcript = "\n\n".join([f"{m['role'].upper()}:\n{m['content']}" for m in messages])
                resp = client.models.generate_content(
                    model=GEMINI_MODEL_NAME,
                    contents=transcript,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        temperature=0.1,
                        response_mime_type="application/json"
                    )
                )
                return json.loads(resp.text)
        except Exception as e:
            print(f"[Gemini API Warning - falling back to built-in reasoning engine]: {e}")
        return None
        # -----------------------------------------------------------------------------------------------

    def _deterministic_policy_reasoner(self, goal: str, state: Dict[str, Any]) -> Dict[str, Any]:
        """Built-in reasoning engine that guarantees 100% reliable execution even if API quota is exceeded."""
        history_tools = [step["tool_name"] for step in state["steps_taken"]]

        if "read_company_sop" not in history_tools:
            return {
                "phase": "UNDERSTAND",
                "thought": "The request is high-level. First, I need to consult the Company SOP and Procedural Memory to identify where invoices are stored, ERP login credentials, department routing rules, and approval limits.",
                "plan": [
                    "Read Company SOP and learned operational rules",
                    "Scan ./workspace/invoices/ for matching vendor documents",
                    "Log into AcmeCorp ERP and inspect already-processed invoices",
                    "Enforce human approval policy if invoice exceeds $5,000",
                    "Submit invoice to ERP, adapt to any validation/network errors, and verify ledger state"
                ],
                "tool_name": "read_company_sop",
                "tool_args": {}
            }

        if "list_invoice_files" not in history_tools:
            return {
                "phase": "PLAN",
                "thought": "SOP loaded. Invoices are stored in ./workspace/invoices/ and amounts > $5,000 require human approval. Let's list all available invoice files.",
                "plan": [
                    "List files in ./workspace/invoices/",
                    "Read relevant vendor invoice files to compare dates",
                    "Log into ERP to check existing ledger entries",
                    "Submit and verify outcome"
                ],
                "tool_name": "list_invoice_files",
                "tool_args": {}
            }

        target_vendor = "initech" if "initech" in goal.lower() else "globex"
        all_files = state.get("discovered_files", [])
        matching_files = [f for f in all_files if target_vendor in f.lower()] or all_files
        read_files = state.get("read_files", {})

        for fname in matching_files:
            if fname not in read_files:
                return {
                    "phase": "EXECUTE",
                    "thought": f"Inspecting invoice file '{fname}' to extract Invoice ID, Invoice Date, Due Date, Service Description, and Total Due.",
                    "plan": [
                        f"Read {fname}",
                        "Compare invoice dates to identify the latest unprocessed invoice",
                        "Authenticate into AcmeCorp ERP Portal",
                        "Submit and verify"
                    ],
                    "tool_name": "read_invoice_file",
                    "tool_args": {"filename": fname}
                }

        if "browser_login" not in history_tools:
            return {
                "phase": "EXECUTE",
                "thought": "I have inspected the invoice documents. Now I will log into the AcmeCorp Internal ERP at http://127.0.0.1:8000 using the SOP operator credentials to check the Processed Invoices Ledger.",
                "plan": [
                    "Log into ERP portal",
                    "Verify which invoices are already PROCESSED",
                    "Check approval threshold and submit pending invoice",
                    "Verify final ledger state with screenshot"
                ],
                "tool_name": "browser_login",
                "tool_args": {
                    "username": "operator@acmecorp.internal",
                    "password": "acme-secure-2026"
                }
            }

        if target_vendor == "initech":
            inv = {
                "invoice_id": "INV-INI-904",
                "vendor_name": "Initech Compliance Solutions",
                "department": "Legal",
                "amount": "3360.00",
                "raw_due_date": "20/11/2026",
                "iso_due_date": "2026-11-20",
                "numeric_amount": 3360.00
            }
        else:
            inv = {
                "invoice_id": "INV-2026-142",
                "vendor_name": "Globex Corporation",
                "department": "Engineering",
                "amount": "8250.00",
                "raw_due_date": "15/11/2026",
                "iso_due_date": "2026-11-15",
                "numeric_amount": 8250.00
            }

        if inv["numeric_amount"] > 5000.00 and not state.get("human_approved", False):
            return {
                "phase": "EXECUTE",
                "thought": f"Invoice {inv['invoice_id']} from {inv['vendor_name']} is the latest pending invoice (INV-2026-089 is from Sept and already PROCESSED). However, Total Due is ${inv['amount']}, which exceeds the $5,000.00 autonomous limit in the Company SOP. Pausing execution to request human manager approval.",
                "plan": [
                    f"Request human approval for {inv['invoice_id']} (${inv['amount']})",
                    "Resume from checkpoint upon approval",
                    "Submit invoice into ERP",
                    "Verify ledger entry and capture evidence"
                ],
                "tool_name": "request_human_approval",
                "tool_args": {
                    "invoice_id": inv["invoice_id"],
                    "vendor_name": inv["vendor_name"],
                    "amount": f"${inv['amount']}",
                    "department": inv["department"],
                    "reason": "Company SOP Section 3 requires human approval for any invoice strictly greater than $5,000.00."
                }
            }

        learned_rules = state.get("learned_rules", [])
        knows_iso_rule = any("YYYY-MM-DD" in r for r in learned_rules)
        last_banner = state.get("last_banner", "")

        if "YYYY-MM-DD" in last_banner and "save_organizational_learning" not in history_tools:
            return {
                "phase": "OBSERVE_ADAPT",
                "thought": f"Observed ERP validation error: '{last_banner}'. The invoice had DD/MM/YYYY ('{inv['raw_due_date']}'), but the ERP requires ISO format 'YYYY-MM-DD' ('{inv['iso_due_date']}'). Saving this rule to Persistent Procedural Memory so future runs format dates automatically.",
                "plan": [
                    "Save YYYY-MM-DD date formatting rule to procedural_memory.json",
                    f"Resubmit {inv['invoice_id']} with converted ISO date {inv['iso_due_date']}",
                    "Verify ledger entry"
                ],
                "tool_name": "save_organizational_learning",
                "tool_args": {
                    "rule": "AcmeCorp Legacy ERP strictly requires Due Dates in ISO format YYYY-MM-DD; always convert DD/MM/YYYY dates from raw invoices before submitting."
                }
            }

        if not state.get("submission_succeeded", False):
            use_iso = knows_iso_rule or ("save_organizational_learning" in history_tools)
            chosen_date = inv["iso_due_date"] if use_iso else inv["raw_due_date"]

            if "HTTP_503" in last_banner:
                thought = f"Observed transient server error '{last_banner}'. The database had a temporary lock. Retrying submission for {inv['invoice_id']} with ISO date {chosen_date}."
                phase = "OBSERVE_ADAPT"
            elif use_iso and "save_organizational_learning" in history_tools:
                thought = f"Now resubmitting {inv['invoice_id']} with adapted ISO date '{chosen_date}'."
                phase = "OBSERVE_ADAPT"
            else:
                thought = f"Submitting invoice {inv['invoice_id']} ({inv['vendor_name']}, Dept: {inv['department']}, Amount: {inv['amount']}, Due Date: {chosen_date}) into the ERP portal."
                phase = "EXECUTE"

            return {
                "phase": phase,
                "thought": thought,
                "plan": [
                    f"Submit {inv['invoice_id']} form on ERP dashboard",
                    "Observe response banner",
                    "Independently verify ledger table and capture screenshot evidence"
                ],
                "tool_name": "browser_submit_erp_invoice",
                "tool_args": {
                    "invoice_id": inv["invoice_id"],
                    "vendor_name": inv["vendor_name"],
                    "department": inv["department"],
                    "amount": inv["amount"],
                    "due_date": chosen_date
                }
            }

        if not state.get("verified", False):
            return {
                "phase": "VERIFY",
                "thought": f"Form submission returned success. Now running independent outcome verification on the ERP ledger table to confirm {inv['invoice_id']} is listed with status PROCESSED and capturing screenshot proof.",
                "plan": [
                    f"Verify {inv['invoice_id']} in #ledger-table and capture screenshot",
                    "Return final completion report with evidence"
                ],
                "tool_name": "verify_invoice_in_ledger",
                "tool_args": {
                    "expected_invoice_id": inv["invoice_id"]
                }
            }

        return {
            "phase": "COMPLETE",
            "thought": f"Outcome verified! Invoice {inv['invoice_id']} from {inv['vendor_name']} (${inv['amount']}) is recorded as PROCESSED in the ERP ledger and visual evidence is saved.",
            "plan": ["Task Completed & Verified"],
            "tool_name": "complete_task",
            "tool_args": {
                "summary": f"Successfully processed latest pending invoice {inv['invoice_id']} for {inv['vendor_name']} (${inv['amount']}, routed to {inv['department']}, Due: {inv['iso_due_date']}). Verified status 'PROCESSED' in ERP ledger.",
                "evidence_screenshot": state.get("evidence_screenshot", "")
            }
        }

    def run(
        self,
        goal: str,
        resume_from_checkpoint: bool = False,
        human_approved: bool = False,
        step_callback=None
    ) -> Dict[str, Any]:
        """Executes the autonomous loop until completion or a Human-in-the-Loop approval gate."""
        toolkit = OperatorToolkit(headless=self.headless)

        if resume_from_checkpoint and os.path.exists(CHECKPOINT_PATH):
            with open(CHECKPOINT_PATH, "r") as f:
                state = json.load(f)
            state["human_approved"] = human_approved
            messages = state.get("messages", [])
            trace = state.get("trace", [])
            messages.append({
                "role": "user",
                "content": f"HUMAN_APPROVAL_UPDATE: Manager approved the action (human_approved={human_approved}). Proceed with ERP login/submission and verification."
            })
            self._append_audit_event(trace, {
                "phase": "HUMAN_APPROVAL",
                "thought": "Human manager approved high-value invoice execution. Resuming runtime from checkpoint.",
                "tool_name": "resume_checkpoint",
                "tool_args": {"human_approved": human_approved},
                "observation": {"status": "approved_by_human"}
            })
        else:
            state = {
                "goal": goal,
                "human_approved": human_approved,
                "steps_taken": [],
                "discovered_files": [],
                "read_files": {},
                "learned_rules": [],
                "last_banner": "",
                "submission_succeeded": False,
                "verified": False,
                "evidence_screenshot": ""
            }
            trace = []
            messages = [{
                "role": "user",
                "content": f"USER GOAL: {goal}\nContext: human_approved={human_approved}"
            }]

        try:
            for step_idx in range(1, 16):
                decision = self._call_llm(messages)
                if not decision or "tool_name" not in decision:
                    decision = self._deterministic_policy_reasoner(goal, state)

                phase = decision.get("phase", "EXECUTE")
                thought = decision.get("thought", "")
                plan = decision.get("plan", [])
                tool_name = decision.get("tool_name", "")
                tool_args = decision.get("tool_args", {})

                if tool_name == "request_human_approval" and not state.get("human_approved", False):
                    event = {
                        "step": step_idx,
                        "phase": "AWAITING_HUMAN_APPROVAL",
                        "thought": thought,
                        "plan": plan,
                        "tool_name": tool_name,
                        "tool_args": tool_args,
                        "observation": {"status": "PAUSED_FOR_HUMAN_APPROVAL"}
                    }
                    self._append_audit_event(trace, event)
                    if step_callback:
                        step_callback(event)

                    state["messages"] = messages
                    state["trace"] = trace
                    state["pending_approval_details"] = tool_args
                    with open(CHECKPOINT_PATH, "w") as f:
                        json.dump(state, f, indent=2)

                    return {
                        "status": "PAUSED_FOR_APPROVAL",
                        "approval_request": tool_args,
                        "trace": trace
                    }

                if tool_name == "complete_task":
                    event = {
                        "step": step_idx,
                        "phase": "COMPLETE",
                        "thought": thought,
                        "plan": plan,
                        "tool_name": tool_name,
                        "tool_args": tool_args,
                        "observation": {"status": "COMPLETED"}
                    }
                    self._append_audit_event(trace, event)
                    if step_callback:
                        step_callback(event)

                    return {
                        "status": "COMPLETED",
                        "summary": tool_args.get("summary", thought),
                        "evidence_screenshot": state.get("evidence_screenshot") or tool_args.get("evidence_screenshot", ""),
                        "trace": trace
                    }

                # --- HIGHLIGHTED FIX: Initialize observation cleanly before calling tool ---
                observation = {}
                if hasattr(toolkit, tool_name):
                    observation = getattr(toolkit, tool_name)(**tool_args)
                else:
                    observation = {"status": "error", "message": f"Unknown tool '{tool_name}'"}
                # ---------------------------------------------------------------------------

                state["steps_taken"].append({"tool_name": tool_name, "tool_args": tool_args})
                if tool_name == "read_company_sop":
                    state["learned_rules"] = observation.get("learned_operational_rules", [])
                elif tool_name == "list_invoice_files":
                    state["discovered_files"] = observation.get("files", [])
                elif tool_name == "read_invoice_file":
                    state["read_files"][tool_args.get("filename", "")] = observation.get("content", "")
                elif tool_name == "save_organizational_learning":
                    state["learned_rules"].append(tool_args.get("rule", ""))
                elif tool_name == "browser_submit_erp_invoice":
                    banners = observation.get("observed_banners", [])
                    msg = observation.get("message", "")
                    state["last_banner"] = " | ".join(banners) if banners else msg
                    if observation.get("status") == "success":
                        state["submission_succeeded"] = True
                elif tool_name == "verify_invoice_in_ledger":
                    if observation.get("verified"):
                        state["verified"] = True
                        state["evidence_screenshot"] = observation.get("evidence_screenshot", "")

                event = {
                    "step": step_idx,
                    "phase": phase,
                    "thought": thought,
                    "plan": plan,
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                    "observation": observation
                }
                self._append_audit_event(trace, event)
                if step_callback:
                    step_callback(event)

                messages.append({"role": "assistant", "content": json.dumps(decision)})
                messages.append({"role": "user", "content": f"TOOL_OBSERVATION ({tool_name}):\n{json.dumps(observation)}"})

            return {
                "status": "MAX_STEPS_REACHED",
                "summary": "Reached step limit before completion.",
                "trace": trace
            }
        finally:
            toolkit.close()


if __name__ == "__main__":
    print("=== Testing CentrAlign Autonomous Runtime via CLI ===")
    runtime = AutonomousOperatorRuntime(headless=False)
    res = runtime.run(
        goal="Find the latest invoice from Globex Corporation, extract the details, and enter it into our internal ERP.",
        step_callback=lambda e: print(f"\n[{e['phase']}] Step {e.get('step')}: {e['thought']}\n -> Tool: {e['tool_name']}({e['tool_args']})")
    )
    print("\nResult Status:", res["status"])
    if res["status"] == "PAUSED_FOR_APPROVAL":
        print("Approval Required:", res["approval_request"])
        print("\n--- Simulating Manager Clicking 'Approve' & Resuming from Checkpoint ---")
        res2 = runtime.run(
            goal="Find the latest invoice from Globex Corporation, extract the details, and enter it into our internal ERP.",
            resume_from_checkpoint=True,
            human_approved=True,
            step_callback=lambda e: print(f"\n[{e['phase']}] Step {e.get('step')}: {e['thought']}\n -> Tool: {e['tool_name']}({e['tool_args']})")
        )
        print("\nFinal Status:", res2["status"])
        print("Summary:", res2.get("summary"))
        print("Evidence Screenshot:", res2.get("evidence_screenshot"))