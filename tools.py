import os
import json
import time
from playwright.sync_api import sync_playwright

WORKSPACE_DIR = "workspace"
INVOICES_DIR = os.path.join(WORKSPACE_DIR, "invoices")
SOP_PATH = os.path.join(WORKSPACE_DIR, "company_sop.md")
MEMORY_PATH = os.path.join(WORKSPACE_DIR, "procedural_memory.json")
EVIDENCE_DIR = os.path.join(WORKSPACE_DIR, "evidence")


class BrowserSession:
    """Manages a persistent Playwright Chromium instance so the agent can operate web apps."""
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.page = None

    def start(self):
        if self.page is None:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(headless=self.headless, slow_mo=400)
            self.page = self.browser.new_page(viewport={"width": 1280, "height": 800})

    def stop(self):
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        self.page = None
        self.browser = None
        self.playwright = None

    def get_semantic_dom(self) -> dict:
        """Extracts actionable elements, status banners, and ledger rows from the live page."""
        self.start()
        try:
            state = self.page.evaluate("""() => {
                const banners = [];
                const err = document.querySelector('#login-error, #status-banner');
                if (err) banners.push(err.innerText.trim());

                const inputs = Array.from(document.querySelectorAll('input, select')).map(el => ({
                    tag: el.tagName.toLowerCase(),
                    id: el.id ? '#' + el.id : '',
                    name: el.name || '',
                    type: el.type || '',
                    value: el.value || '',
                    options: el.tagName.toLowerCase() === 'select'
                        ? Array.from(el.options).map(o => o.value).filter(Boolean)
                        : undefined
                }));

                const buttons = Array.from(document.querySelectorAll('button')).map(el => ({
                    id: el.id ? '#' + el.id : '',
                    text: el.innerText.trim()
                }));

                const ledgerRows = Array.from(document.querySelectorAll('#ledger-table tbody tr')).map(tr => {
                    const cells = Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim());
                    return {
                        invoice_id: cells[0] || '',
                        vendor: cells[1] || '',
                        department: cells[2] || '',
                        amount: cells[3] || '',
                        due_date: cells[4] || '',
                        status: cells[5] || ''
                    };
                });

                return {
                    url: window.location.href,
                    title: document.title,
                    banners: banners,
                    inputs: inputs,
                    buttons: buttons,
                    ledger_rows: ledgerRows
                };
            }""")
            return state
        except Exception as e:
            return {"error": f"Failed to inspect DOM: {str(e)}"}


class OperatorToolkit:
    def __init__(self, headless: bool = False):
        self.browser = BrowserSession(headless=headless)
        os.makedirs(EVIDENCE_DIR, exist_ok=True)

    def close(self):
        self.browser.stop()

    # --- 1. COMPANY CONTEXT & MEMORY TOOLS ---
    def read_company_sop(self, **kwargs) -> dict:
        """Reads the company Standard Operating Procedures (SOP) and learned operational rules."""
        sop_text = ""
        if os.path.exists(SOP_PATH):
            with open(SOP_PATH, "r") as f:
                sop_text = f.read()

        learnings = []
        if os.path.exists(MEMORY_PATH):
            with open(MEMORY_PATH, "r") as f:
                learnings = json.load(f).get("organization_learnings", [])

        return {
            "status": "success",
            "company_sop": sop_text,
            "learned_operational_rules": learnings
        }

    def save_organizational_learning(self, rule: str = "", **kwargs) -> dict:
        """Persists a newly discovered operational rule or system quirk into company memory."""
        # --- HIGHLIGHTED CHANGE: Accept flexible arg names from LLM ---
        rule_text = rule or kwargs.get("learning") or kwargs.get("lesson") or str(kwargs)
        # --------------------------------------------------------------
        data = {"organization_learnings": []}
        if os.path.exists(MEMORY_PATH):
            with open(MEMORY_PATH, "r") as f:
                data = json.load(f)

        if rule_text not in data["organization_learnings"]:
            data["organization_learnings"].append(rule_text)
            with open(MEMORY_PATH, "w") as f:
                json.dump(data, f, indent=2)

        return {"status": "saved", "learned_rule": rule_text}

    # --- 2. FILE SYSTEM TOOLS ---
    def list_invoice_files(self, **kwargs) -> dict:
        """Lists all raw invoice files in the company workspace."""
        if not os.path.exists(INVOICES_DIR):
            return {"status": "error", "message": "Invoices directory not found."}
        files = sorted(os.listdir(INVOICES_DIR))
        return {"status": "success", "files": files}

    def read_invoice_file(self, filename: str = "", **kwargs) -> dict:
        """Reads the full text content of a specific invoice file."""
        # --- HIGHLIGHTED CHANGE: Accept filename, file_path, path, or file_name ---
        target = filename or kwargs.get("file_path") or kwargs.get("path") or kwargs.get("file_name") or ""
        # --------------------------------------------------------------------------
        safe_name = os.path.basename(target)
        path = os.path.join(INVOICES_DIR, safe_name)
        if not os.path.exists(path):
            return {"status": "error", "message": f"File '{safe_name}' does not exist."}
        with open(path, "r") as f:
            content = f.read()
        return {"status": "success", "filename": safe_name, "content": content}

    # --- 3. BROWSER AUTOMATION TOOLS (PLAYWRIGHT) ---
    def browser_navigate(self, url: str = "http://127.0.0.1:8000", **kwargs) -> dict:
        """Navigates the browser to a target URL and returns the semantic DOM state."""
        self.browser.start()
        try:
            self.browser.page.goto(url, wait_until="domcontentloaded", timeout=10000)
            return {"status": "success", "dom_state": self.browser.get_semantic_dom()}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def browser_login(self, username: str = "", password: str = "", **kwargs) -> dict:
        """Logs into the AcmeCorp Internal ERP portal and returns the resulting page state."""
        # --- HIGHLIGHTED CHANGE: Fallback to SOP credentials if LLM passes alternative keys ---
        user = username or kwargs.get("email") or "operator@acmecorp.internal"
        pw = password or kwargs.get("pass") or "acme-secure-2026"
        # --------------------------------------------------------------------------------------
        self.browser.start()
        try:
            if "127.0.0.1:8000" not in self.browser.page.url:
                self.browser.page.goto("http://127.0.0.1:8000", wait_until="domcontentloaded")
            self.browser.page.fill("#username", user)
            self.browser.page.fill("#password", pw)
            self.browser.page.click("#login-btn")
            self.browser.page.wait_for_load_state("domcontentloaded")
            dom = self.browser.get_semantic_dom()
            is_error = any("Invalid" in b or "error" in b.lower() for b in dom.get("banners", []))
            return {
                "status": "error" if is_error else "success",
                "dom_state": dom
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def browser_submit_erp_invoice(
        self,
        invoice_id: str = "",
        vendor_name: str = "",
        department: str = "",
        amount: str = "",
        due_date: str = "",
        **kwargs
    ) -> dict:
        """Fills and submits the ERP invoice form and observes the resulting DOM banner and ledger."""
        # --- HIGHLIGHTED CHANGE: Accept alternative argument names from LLM ---
        inv_id = invoice_id or kwargs.get("id") or ""
        vendor = vendor_name or kwargs.get("vendor") or ""
        dept = department or kwargs.get("dept") or "Engineering"
        amt = str(amount or kwargs.get("total_amount") or kwargs.get("total_due") or "").replace("$", "").replace(",", "")
        due = due_date or kwargs.get("date") or ""
        # ----------------------------------------------------------------------

        self.browser.start()
        try:
            if "/dashboard" not in self.browser.page.url:
                self.browser.page.goto("http://127.0.0.1:8000", wait_until="domcontentloaded")
                if "/dashboard" not in self.browser.page.url:
                    self.browser.page.fill("#username", "operator@acmecorp.internal")
                    self.browser.page.fill("#password", "acme-secure-2026")
                    self.browser.page.click("#login-btn")
                    self.browser.page.wait_for_load_state("domcontentloaded")

            self.browser.page.fill("#invoice_id", str(inv_id))
            self.browser.page.fill("#vendor_name", str(vendor))
            self.browser.page.select_option("#department", str(dept))
            self.browser.page.fill("#amount", str(amt))
            self.browser.page.fill("#due_date", str(due))
            self.browser.page.click("#submit-invoice-btn")
            self.browser.page.wait_for_load_state("domcontentloaded")

            dom = self.browser.get_semantic_dom()
            banners = dom.get("banners", [])
            has_error = any("ERP_VALIDATION_ERROR" in b or "HTTP_503" in b for b in banners)

            return {
                "status": "error" if has_error else "success",
                "observed_banners": banners,
                "dom_state": dom
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # --- 4. VERIFICATION & EVIDENCE CAPTURE TOOL ---
    def verify_invoice_in_ledger(self, expected_invoice_id: str = "", **kwargs) -> dict:
        """Independently verifies that an Invoice ID exists in the live ERP ledger with status PROCESSED and captures screenshot evidence."""
        # --- HIGHLIGHTED CHANGE: Accept invoice_id or expected_invoice_id ---
        target_id = expected_invoice_id or kwargs.get("invoice_id") or ""
        # --------------------------------------------------------------------
        self.browser.start()
        try:
            if "/dashboard" not in self.browser.page.url:
                self.browser.page.goto("http://127.0.0.1:8000", wait_until="domcontentloaded")
                if "/dashboard" not in self.browser.page.url:
                    self.browser.page.fill("#username", "operator@acmecorp.internal")
                    self.browser.page.fill("#password", "acme-secure-2026")
                    self.browser.page.click("#login-btn")
                    self.browser.page.wait_for_load_state("domcontentloaded")

            dom = self.browser.get_semantic_dom()
            rows = dom.get("ledger_rows", [])
            matched_row = None
            for row in rows:
                if row.get("invoice_id") == target_id and row.get("status") == "PROCESSED":
                    matched_row = row
                    break

            screenshot_filename = f"evidence_{target_id}_{int(time.time())}.png"
            screenshot_path = os.path.join(EVIDENCE_DIR, screenshot_filename)
            self.browser.page.screenshot(path=screenshot_path, full_page=True)

            if matched_row:
                return {
                    "verified": True,
                    "message": f"Verified {target_id} is present in ERP ledger with status PROCESSED.",
                    "ledger_record": matched_row,
                    "evidence_screenshot": screenshot_path
                }
            else:
                return {
                    "verified": False,
                    "message": f"Verification FAILED: {target_id} was NOT found with status PROCESSED in the ledger.",
                    "current_ledger": rows,
                    "evidence_screenshot": screenshot_path
                }
        except Exception as e:
            return {"verified": False, "message": f"Verification error: {str(e)}"}