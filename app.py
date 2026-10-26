import os
import json
import requests
import streamlit as st
from agent_runtime import AutonomousOperatorRuntime, CHECKPOINT_PATH, AUDIT_LOG_PATH
from setup_workspace import init_workspace

st.set_page_config(
    page_title="CentrAlign AI — Autonomous Company Operator",
    layout="wide"
)

# Initialize session state
if "run_result" not in st.session_state:
    st.session_state.run_result = None
if "live_events" not in st.session_state:
    st.session_state.live_events = []

st.title("CentrAlign AI — Autonomous Enterprise Operator")
st.caption("Core Loop: Goal → Understand → Plan → Execute → Observe → Adapt → Verify → Complete")

# --- SIDEBAR: CONFIGURATION & SANDBOX CONTROLS ---
with st.sidebar:
    st.header("Runtime Configuration")
    provider = st.selectbox(
        "Reasoning Engine",
        ["auto", "gemini", "groq", "openai", "deterministic"],
        index=0,
        help="Select LLM provider or use built-in deterministic fallback."
    )
    api_key = st.text_input(
        "LLM API Key (Optional if set in env)",
        type="password",
        placeholder="Paste Gemini / Groq / OpenAI key"
    )
    headless_mode = st.checkbox("Run Browser Headless", value=False, help="Keep unchecked so Chromium pops up visibly during demo!")

    st.divider()
    st.header("Sandbox Environment Controls")
    st.markdown("Target ERP Portal: `http://127.0.0.1:8000`")

    if st.button("Reset ERP Database & Clear Memory", use_container_width=True):
        init_workspace()
        with open("workspace/procedural_memory.json", "w") as f:
            json.dump({"organization_learnings": []}, f, indent=2)
        if os.path.exists(CHECKPOINT_PATH):
            os.remove(CHECKPOINT_PATH)
        try:
            requests.post("http://127.0.0.1:8000/api/reset", timeout=3)
            st.success("ERP Database, 503 Chaos Trigger, and Procedural Memory reset!")
        except Exception:
            st.warning("Workspace files reset. Make sure erp_sandbox.py is running on port 8000.")
        st.session_state.run_result = None
        st.session_state.live_events = []

    st.divider()
    st.subheader("Persistent Procedural Memory")
    mem_path = "workspace/procedural_memory.json"
    if os.path.exists(mem_path):
        with open(mem_path, "r") as f:
            learnings = json.load(f).get("organization_learnings", [])
        if learnings:
            for idx, rule in enumerate(learnings, 1):
                st.info(f"**Learned Rule #{idx}:** {rule}")
        else:
            st.caption("No operational rules learned yet. Run a task to watch the agent learn from ERP errors!")

# --- MAIN LAYOUT ---
col_left, col_right = st.columns([1.25, 1])

with col_left:
    st.subheader("1. Assign Business Objective")
    preset = st.selectbox(
        "Choose Demo Scenario:",
        [
            "Scenario A (Founding Eng - High Value + Policy Gate + Error Recovery): Process the latest pending invoice from Globex Corporation into our internal ERP.",
            "Scenario B (Intern - Fully Autonomous Under $5k Limit): Find the latest invoice from Initech, extract the amount and due date, enter it into our internal system, and verify.",
            "Custom Natural Language Request"
        ]
    )

    if "Scenario A" in preset:
        default_goal = "Find the latest pending invoice from Globex Corporation, extract the required details, enter it into our internal ERP system, and verify completion."
    elif "Scenario B" in preset:
        default_goal = "Find the latest invoice from Initech, extract the amount and due date, enter it into our internal ERP system, and tell me once it is done."
    else:
        default_goal = ""

    goal_input = st.text_area("Operator Instruction:", value=default_goal, height=85)

    start_btn = st.button("Launch Autonomous Operator", type="primary", use_container_width=True)

    trace_container = st.container()

    if start_btn and goal_input.strip():
        st.session_state.live_events = []
        runtime = AutonomousOperatorRuntime(
            provider=" fallback" if provider == "deterministic" else provider,
            api_key=api_key,
            headless=headless_mode
        )

        with st.status("Autonomous Operator Executing...", expanded=True) as status_box:
            def on_step(event):
                st.session_state.live_events.append(event)
                phase = event.get("phase", "EXECUTE")
                step_num = event.get("step", "?")
                st.markdown(f"**Step {step_num} [{phase}]** — `{event.get('tool_name')}`")
                st.write(event.get("thought", ""))

            result = runtime.run(
                goal=goal_input,
                resume_from_checkpoint=False,
                human_approved=False,
                step_callback=on_step
            )
            st.session_state.run_result = result
            if result["status"] == "PAUSED_FOR_APPROVAL":
                status_box.update(label="Paused at Governance Gate — Awaiting Human Approval", state="error")
            elif result["status"] == "COMPLETED":
                status_box.update(label="Task Completed & Verified!", state="complete")
            else:
                status_box.update(label=f"Stopped: {result['status']}", state="error")
        st.rerun()

    # --- HUMAN-IN-THE-LOOP APPROVAL GATE ---
    res = st.session_state.run_result
    if res and res.get("status") == "PAUSED_FOR_APPROVAL":
        req = res.get("approval_request", {})
        st.warning("### Governance Gate Triggered: Human Approval Required")
        st.markdown(f"""
        * **Invoice ID:** `{req.get('invoice_id')}`
        * **Vendor:** `{req.get('vendor_name')}`
        * **Department:** `{req.get('department')}`
        * **Total Amount:** `{req.get('amount')}`
        * **Policy Reason:** {req.get('reason')}
        """)
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Approve & Resume from Checkpoint", type="primary", use_container_width=True):
                runtime = AutonomousOperatorRuntime(
                    provider="fallback" if provider == "deterministic" else provider,
                    api_key=api_key,
                    headless=headless_mode
                )
                with st.status("Resuming from Checkpoint after Manager Approval...", expanded=True) as status_box:
                    def on_resume_step(event):
                        st.session_state.live_events.append(event)
                        st.markdown(f"**Step {event.get('step')} [{event.get('phase')}]** — `{event.get('tool_name')}`")
                        st.write(event.get("thought", ""))

                    res2 = runtime.run(
                        goal=goal_input,
                        resume_from_checkpoint=True,
                        human_approved=True,
                        step_callback=on_resume_step
                    )
                    st.session_state.run_result = res2
                    status_box.update(label="Task Completed & Verified!", state="complete")
                st.rerun()
        with c2:
            if st.button("Reject & Abort Task", use_container_width=True):
                st.session_state.run_result = {
                    "status": "ABORTED_BY_HUMAN",
                    "summary": "Execution aborted by human supervisor at policy gate.",
                    "trace": res.get("trace", [])
                }
                st.rerun()

    # --- STEP-BY-STEP EXECUTION TRACE ---
    st.subheader("2. Live Execution & Reasoning Trace")
    events_to_show = (res.get("trace") if res else None) or st.session_state.live_events
    if events_to_show:
        for ev in events_to_show:
            phase_badge = ev.get("phase", "STEP")
            tool = ev.get("tool_name", "")
            with st.expander(f"[{phase_badge}] Tool: {tool} ({ev.get('timestamp', '')})", expanded=True):
                st.markdown(f"**Reasoning:** {ev.get('thought', '')}")
                if ev.get("plan"):
                    st.markdown("**Current Plan:** " + " → ".join(ev["plan"]))
                st.code(json.dumps(ev.get("tool_args", {}), indent=2), language="json")
                obs = ev.get("observation", {})
                if obs:
                    st.caption("Tool Observation:")
                    st.json(obs, expanded=False)
    else:
        st.info("Click 'Launch Autonomous Operator' above to start a live run.")

with col_right:
    st.subheader("3. Verification & Evidence Packet")
    if res and res.get("status") == "COMPLETED":
        st.success(f"**Verified Outcome:** {res.get('summary')}")
        shot = res.get("evidence_screenshot", "")
        if shot and os.path.exists(shot):
            st.image(shot, caption=f"Independent Verification Screenshot ({shot})", use_container_width=True)
    elif res and res.get("status") == "PAUSED_FOR_APPROVAL":
        st.info("Execution is paused at checkpoint `workspace/checkpoint.json`. Approve on the left to complete and generate verification evidence.")
    else:
        st.caption("Verification screenshot and audit report will appear here upon completion.")

    st.divider()
    st.subheader("4. Company Context (SOP & Raw Invoices)")
    tab1, tab2, tab3 = st.tabs(["company_sop.md", "globex_oct_2026.txt", "initech_oct_2026.txt"])
    with tab1:
        if os.path.exists("workspace/company_sop.md"):
            st.markdown(open("workspace/company_sop.md").read())
    with tab2:
        if os.path.exists("workspace/invoices/globex_oct_2026.txt"):
            st.code(open("workspace/invoices/globex_oct_2026.txt").read())
    with tab3:
        if os.path.exists("workspace/invoices/initech_oct_2026.txt"):
            st.code(open("workspace/invoices/initech_oct_2026.txt").read())