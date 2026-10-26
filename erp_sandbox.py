from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
import sqlite3
import datetime
import re

app = FastAPI(title="AcmeCorp Internal ERP Portal")
DB_PATH = "workspace/erp_database.db"

# Track transient failure simulation per invoice so first attempt can fail if chaos_mode is active
CHAOS_STATE = {"simulate_503_once": True}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id TEXT UNIQUE,
            vendor_name TEXT,
            department TEXT,
            amount REAL,
            due_date TEXT,
            status TEXT,
            created_at TEXT
        )
    """)
    # Seed with the old September Globex invoice so the agent can see it's already PROCESSED
    c.execute("""
        INSERT OR IGNORE INTO invoices (invoice_id, vendor_name, department, amount, due_date, status, created_at)
        VALUES ('INV-2026-089', 'Globex Corporation', 'Engineering', 3080.00, '2026-10-10', 'PROCESSED', '2026-09-12 10:15:00')
    """)
    conn.commit()
    conn.close()

@app.on_event("startup")
def startup():
    init_db()

LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>AcmeCorp ERP - Login</title>
    <style>
        body { font-family: Arial, sans-serif; background: #f4f6f9; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .card { background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); width: 360px; }
        h2 { margin-top: 0; color: #1e293b; }
        label { display: block; margin-top: 12px; font-size: 14px; color: #475569; }
        input { width: 100%; padding: 10px; margin-top: 5px; box-sizing: border-box; border: 1px solid #cbd5e1; border-radius: 4px; }
        button { width: 100%; padding: 10px; margin-top: 20px; background: #2563eb; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; }
        .error { background: #fee2e2; color: #b91c1c; padding: 10px; border-radius: 4px; margin-bottom: 12px; font-size: 14px; }
    </style>
</head>
<body>
    <div class="card">
        <h2>AcmeCorp Internal ERP</h2>
        {error_block}
        <form method="POST" action="/login">
            <label>Employee Email</label>
            <input type="text" id="username" name="username" placeholder="operator@acmecorp.internal" required />
            <label>Password</label>
            <input type="password" id="password" name="password" required />
            <button type="submit" id="login-btn">Sign In to Portal</button>
        </form>
    </div>
</body>
</html>
"""

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>AcmeCorp ERP - Accounts Payable</title>
    <style>
        body { font-family: Arial, sans-serif; background: #f8fafc; margin: 0; padding: 24px; color: #1e293b; }
        .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #e2e8f0; padding-bottom: 12px; margin-bottom: 20px; }
        .grid { display: grid; grid-template-columns: 1fr 1.4fr; gap: 24px; }
        .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }
        label { display: block; margin-top: 10px; font-size: 13px; font-weight: bold; color: #334155; }
        input, select { width: 100%; padding: 8px; margin-top: 4px; box-sizing: border-box; border: 1px solid #cbd5e1; border-radius: 4px; }
        button { margin-top: 16px; padding: 10px 16px; background: #16a34a; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; width: 100%; }
        table { width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 14px; }
        th, td { border: 1px solid #e2e8f0; padding: 8px 10px; text-align: left; }
        th { background: #f1f5f9; }
        .status-badge { background: #dcfce7; color: #166534; padding: 3px 8px; border-radius: 12px; font-size: 12px; font-weight: bold; }
        .alert-error { background: #fef2f2; border: 1px solid #f87171; color: #991b1b; padding: 12px; border-radius: 6px; margin-bottom: 16px; font-weight: bold; }
        .alert-success { background: #f0fdf4; border: 1px solid #4ade80; color: #166534; padding: 12px; border-radius: 6px; margin-bottom: 16px; font-weight: bold; }
    </style>
</head>
<body>
    <div class="header">
        <h2>AcmeCorp ERP — Accounts Payable & Invoice Ledger</h2>
        <span>Logged in as: <strong>operator@acmecorp.internal</strong></span>
    </div>

    {banner_block}

    <div class="grid">
        <div class="card">
            <h3>Submit New Vendor Invoice</h3>
            <form method="POST" action="/submit-invoice">
                <label>Invoice ID</label>
                <input type="text" id="invoice_id" name="invoice_id" placeholder="e.g. INV-2026-142" required />

                <label>Vendor Official Name</label>
                <input type="text" id="vendor_name" name="vendor_name" placeholder="e.g. Globex Corporation" required />

                <label>Department Routing</label>
                <select id="department" name="department">
                    <option value="">-- Select Department --</option>
                    <option value="Engineering">Engineering</option>
                    <option value="Legal">Legal</option>
                    <option value="People">People</option>
                    <option value="Finance">Finance</option>
                </select>

                <label>Total Amount Due (USD Numeric)</label>
                <input type="text" id="amount" name="amount" placeholder="e.g. 8250.00" required />

                <label>Due Date</label>
                <input type="text" id="due_date" name="due_date" placeholder="Enter Due Date" required />

                <button type="submit" id="submit-invoice-btn">Record & Process Invoice</button>
            </form>
        </div>

        <div class="card">
            <h3>Processed Invoices Ledger</h3>
            <table id="ledger-table">
                <thead>
                    <tr>
                        <th>Invoice ID</th>
                        <th>Vendor</th>
                        <th>Dept</th>
                        <th>Amount ($)</th>
                        <th>Due Date</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def login_page(error: str = ""):
    err_html = f'<div class="error" id="login-error">{error}</div>' if error else ""
    return LOGIN_HTML.replace("{error_block}", err_html)

@app.post("/login")
def login(username: str = Form(...), password: str = Form(...)):
    if username.strip() == "operator@acmecorp.internal" and password.strip() == "acme-secure-2026":
        return RedirectResponse(url="/dashboard", status_code=303)
    return RedirectResponse(url="/?error=Invalid+credentials.+Check+Company+SOP+for+operator+login.", status_code=303)

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(error: str = "", success: str = ""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT invoice_id, vendor_name, department, amount, due_date, status FROM invoices ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()

    rows_html = ""
    for r in rows:
        rows_html += f"""
        <tr data-invoice-id="{r[0]}">
            <td>{r[0]}</td>
            <td>{r[1]}</td>
            <td>{r[2]}</td>
            <td>${r[3]:,.2f}</td>
            <td>{r[4]}</td>
            <td><span class="status-badge">{r[5]}</span></td>
        </tr>
        """

    banner = ""
    if error:
        banner = f'<div class="alert-error" id="status-banner">ERP_VALIDATION_ERROR: {error}</div>'
    elif success:
        banner = f'<div class="alert-success" id="status-banner">ERP_SUCCESS: {success}</div>'

    html = DASHBOARD_HTML.replace("{banner_block}", banner).replace("{table_rows}", rows_html)
    return html

@app.post("/submit-invoice")
def submit_invoice(
    invoice_id: str = Form(...),
    vendor_name: str = Form(...),
    department: str = Form(""),
    amount: str = Form(...),
    due_date: str = Form(...)
):
    # 1. Validate Department
    if not department:
        return RedirectResponse(
            url="/dashboard?error=Department+field+cannot+be+empty.+Select+valid+department.",
            status_code=303
        )

    # 2. Validate Amount is pure numeric (strip $ or commas if agent included them, or throw error so agent adapts)
    cleaned_amount = amount.strip()
    if "$" in cleaned_amount or "," in cleaned_amount:
        return RedirectResponse(
            url="/dashboard?error=Amount+must+be+strict+numeric+value+without+currency+symbols+or+commas+(e.g.+8250.00).",
            status_code=303
        )

    try:
        numeric_amount = float(cleaned_amount)
    except ValueError:
        return RedirectResponse(url="/dashboard?error=Invalid+numeric+amount.", status_code=303)

    # 3. Validate Date Format strictly as ISO YYYY-MM-DD (Triggers Observe -> Adapt when invoice has DD/MM/YYYY)
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", due_date.strip()):
        return RedirectResponse(
            url=f"/dashboard?error=Invalid+Due+Date+format+'{due_date}'.+Legacy+ERP+strictly+requires+ISO+format+YYYY-MM-DD.",
            status_code=303
        )

    # 4. Simulated Transient Server Glitch on first valid try (Tests Retry Resilience)
    if CHAOS_STATE.get("simulate_503_once", False):
        CHAOS_STATE["simulate_503_once"] = False
        return RedirectResponse(
            url="/dashboard?error=HTTP_503_TRANSIENT_DB_LOCK:+Database+temporarily+busy.+Please+retry+submission.",
            status_code=303
        )

    # 5. Insert into SQLite
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO invoices (invoice_id, vendor_name, department, amount, due_date, status, created_at) VALUES (?, ?, ?, ?, ?, 'PROCESSED', ?)",
            (invoice_id.strip(), vendor_name.strip(), department.strip(), numeric_amount, due_date.strip(), datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return RedirectResponse(
            url=f"/dashboard?error=Duplicate+Entry:+Invoice+{invoice_id}+is+already+PROCESSED+in+the+ledger.",
            status_code=303
        )
    conn.close()

    return RedirectResponse(
        url=f"/dashboard?success=Invoice+{invoice_id}+for+{vendor_name}+(${numeric_amount:.2f})+successfully+recorded+with+status+PROCESSED.",
        status_code=303
    )

@app.post("/api/reset")
def reset_sandbox():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM invoices WHERE invoice_id != 'INV-2026-089'")
    conn.commit()
    conn.close()
    CHAOS_STATE["simulate_503_once"] = True
    return JSONResponse({"status": "reset_complete"})

if __name__ == "__main__":
    import uvicorn
    init_db()
    uvicorn.run(app, host="127.0.0.1", port=8000)