"""
BAND Code Assistant — Streamlit UI
====================================
Launch with:  uv run streamlit run src/streamlit_app.py
"""

from __future__ import annotations

import asyncio
import json
import os
import queue
import sys
import threading
from datetime import datetime
from pathlib import Path

# ── path setup ────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import streamlit as st
from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

# ── page config (must be first) ───────────────────────────────────
st.set_page_config(
    page_title="BAND Code Assistant",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ═══════════════════════════════════════════════════════════════════
#  DESIGN TOKENS  (mirrors the reference palette exactly)
# ═══════════════════════════════════════════════════════════════════
BG      = "#0f0f12"
BG2     = "#17171c"
BG3     = "#1e1e26"
BG4     = "#242430"
TEXT    = "#f0f0f8"
SEC     = "#7b7b8d"
MUTED   = "#4a4a5a"
ACCENT  = "#f5c518"          # gold — same as reference
SUCCESS = "#22c55e"
WARN    = "#ef4444"
INFO    = "#60a5fa"

AGENT_COLORS = {
    "conductor":     "#93c5fd",
    "planner":       "#fdba74",
    "plan_reviewer": "#c4b5fd",
    "coder":         "#86efac",
    "code_reviewer": "#fca5a5",
    "test_engineer": "#38bdf8",
    "debugger":      "#f87171",
    "mergemaster":   "#6ee7b7",
}

# ═══════════════════════════════════════════════════════════════════
#  CSS
# ═══════════════════════════════════════════════════════════════════
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,opsz,wght@0,8..60,300;0,8..60,400;0,8..60,600;0,8..60,700;1,8..60,400;1,8..60,600;1,8..60,700&family=Inter:wght@300;400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

html, body, .stApp {{
  background-color: {BG};
  color: {TEXT};
  font-family: 'Inter', sans-serif;
  font-size: 14px;
  -webkit-font-smoothing: antialiased;
}}

.block-container {{ padding-top: 0.9rem; padding-bottom: 2rem; max-width: 1440px; }}

/* ── Sidebar ── */
[data-testid="stSidebar"] {{
  background-color: {BG2};
  border-right: 1px solid #22222e;
}}
[data-testid="stSidebar"] .stMarkdown h3 {{
  color: {ACCENT};
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.62rem;
  text-transform: uppercase;
  letter-spacing: 0.2em;
  margin-top: 28px;
  margin-bottom: 10px;
  font-weight: 500;
}}

/* ── Radio nav ── */
div[data-testid="stSidebar"] [data-testid="stRadio"] label {{
  font-family: 'Inter', sans-serif !important;
  font-size: 0.82rem !important;
  color: {SEC} !important;
  font-weight: 400;
  letter-spacing: 0.01em;
  padding: 3px 0;
}}
div[data-testid="stSidebar"] [data-testid="stRadio"] [aria-checked="true"] + div label,
div[data-testid="stSidebar"] [data-testid="stRadio"] [aria-checked="true"] ~ div label {{
  color: {TEXT} !important;
  font-weight: 600 !important;
}}

/* ── Page header ── */
.page-header {{
  padding: 28px 0 20px;
  border-bottom: 2px solid {ACCENT};
  margin-bottom: 28px;
}}
.page-header-eyebrow {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.62rem;
  color: {ACCENT};
  text-transform: uppercase;
  letter-spacing: 0.22em;
  margin-bottom: 10px;
  font-weight: 500;
}}
.page-header-title {{
  font-family: 'Source Serif 4', Georgia, serif;
  font-size: 2.3rem;
  font-weight: 700;
  font-style: italic;
  color: {TEXT};
  line-height: 1.1;
  margin-bottom: 10px;
  letter-spacing: -0.01em;
}}
.page-header-sub {{
  font-family: 'Inter', sans-serif;
  font-size: 0.875rem;
  color: {SEC};
  font-weight: 300;
  line-height: 1.65;
  max-width: 680px;
}}
.page-header-rule {{
  width: 40px; height: 2px;
  background: {ACCENT};
  margin: 14px 0 0;
}}

/* ── Section title ── */
.section-title {{
  font-family: 'Source Serif 4', Georgia, serif;
  font-size: 1.2rem;
  font-weight: 600;
  font-style: italic;
  color: {TEXT};
  border-left: 3px solid {ACCENT};
  padding-left: 14px;
  margin: 32px 0 16px;
  line-height: 1.25;
  letter-spacing: -0.01em;
}}
.section-eyebrow {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.6rem;
  color: {ACCENT};
  text-transform: uppercase;
  letter-spacing: 0.2em;
  margin-bottom: 3px;
  padding-left: 17px;
  font-weight: 500;
}}

/* ── KPI cards ── */
.kpi-card {{
  background: {BG2};
  border-radius: 2px;
  padding: 20px 18px 18px;
  border: 1px solid #22222e;
  border-top: 3px solid {ACCENT};
  min-height: 118px;
}}
.kpi-value {{
  font-family: 'Source Serif 4', Georgia, serif;
  font-size: 2.2rem;
  font-weight: 700;
  color: {ACCENT};
  line-height: 1.0;
  letter-spacing: -0.02em;
}}
.kpi-label {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.62rem;
  color: {SEC};
  margin-top: 7px;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  font-weight: 400;
}}
.kpi-sub {{
  font-family: 'Inter', sans-serif;
  font-size: 0.73rem;
  margin-top: 5px;
  font-weight: 400;
}}

/* ── Chat feed ── */
.chat-wrap {{
  height: 460px;
  overflow-y: auto;
  background: {BG2};
  border: 1px solid #22222e;
  border-radius: 2px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}}
.chat-wrap::-webkit-scrollbar {{ width: 4px; }}
.chat-wrap::-webkit-scrollbar-thumb {{ background: #33334a; border-radius: 4px; }}
.chat-msg {{ display: flex; gap: 10px; align-items: flex-start; }}
.chat-avatar {{
  width: 30px; height: 30px; border-radius: 2px;
  display: flex; align-items: center; justify-content: center;
  font-size: 0.75rem; font-weight: 700; flex-shrink: 0;
  font-family: 'IBM Plex Mono', monospace;
}}
.chat-bubble {{
  flex: 1;
  background: {BG3};
  border: 1px solid #22222e;
  border-radius: 0 2px 2px 2px;
  padding: 7px 12px;
}}
.chat-sender {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.65rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 3px;
}}
.chat-text {{ font-size: 0.82rem; color: {SEC}; line-height: 1.55; font-weight: 300; }}
.chat-ts {{ font-size: 0.62rem; color: {MUTED}; margin-top: 4px; font-family: 'IBM Plex Mono', monospace; }}
.chat-empty {{
  text-align: center; color: {MUTED};
  font-size: 0.8rem; padding: 40px 0;
  font-family: 'Inter', sans-serif; font-weight: 300;
}}

/* ── Phase progress ── */
.phase-bar {{
  display: flex;
  border: 1px solid #22222e;
  border-radius: 2px;
  overflow: hidden;
}}
.phase-step {{
  flex: 1; padding: 10px 4px; text-align: center;
  font-size: 0.62rem; font-weight: 500; letter-spacing: 0.04em;
  text-transform: uppercase; color: {MUTED};
  border-right: 1px solid #22222e;
  font-family: 'IBM Plex Mono', monospace;
  line-height: 1.4;
}}
.phase-step:last-child {{ border-right: none; }}
.phase-step.done {{ background: rgba(34,197,94,0.08); color: {SUCCESS}; }}
.phase-step.active {{
  background: rgba(245,197,24,0.08);
  color: {ACCENT};
  font-weight: 600;
}}
.phase-step .ph-icon {{ display: block; font-size: 0.95rem; margin-bottom: 2px; }}

/* ── Agent grid ── */
.agent-grid {{
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-top: 4px;
}}
.agent-card {{
  background: {BG2};
  border: 1px solid #22222e;
  border-radius: 2px;
  padding: 16px 12px;
  text-align: center;
}}
.agent-card.active {{
  border-color: {ACCENT};
  background: rgba(245,197,24,0.06);
}}
.agent-card.done {{
  border-color: {SUCCESS};
  background: rgba(34,197,94,0.06);
}}
.agent-card.error {{
  border-color: {WARN};
  background: rgba(239,68,68,0.06);
}}
.agent-icon {{ font-size: 1.5rem; margin-bottom: 6px; }}
.agent-name {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.6rem;
  font-weight: 500;
  color: {SEC};
  text-transform: uppercase;
  letter-spacing: 0.06em;
}}
.agent-badge {{
  display: inline-block;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.58rem;
  padding: 2px 7px;
  border-radius: 2px;
  margin-top: 5px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: 500;
}}
.badge-active {{ background: rgba(245,197,24,0.15); color: {ACCENT}; }}
.badge-done   {{ background: rgba(34,197,94,0.12);  color: {SUCCESS}; }}
.badge-error  {{ background: rgba(239,68,68,0.12);  color: {WARN}; }}
.badge-wait   {{ background: rgba(255,255,255,0.04); color: {MUTED}; }}

/* ── Narrative / info block ── */
.narrative-block {{
  background: {BG2};
  border-radius: 2px;
  padding: 22px 28px;
  border-left: 4px solid {ACCENT};
  border-top: 1px solid #22222e;
  border-right: 1px solid #22222e;
  border-bottom: 1px solid #22222e;
  margin-bottom: 16px;
}}
.narrative-title {{
  font-family: 'Source Serif 4', Georgia, serif;
  font-size: 1.05rem;
  font-weight: 700;
  color: {TEXT};
  margin-bottom: 10px;
  line-height: 1.3;
}}
.narrative-body {{
  font-size: 0.85rem;
  color: {SEC};
  line-height: 1.85;
  font-weight: 300;
}}

/* ── Banners ── */
.banner {{
  border-radius: 2px; padding: 12px 16px;
  font-size: 0.83rem; margin-bottom: 12px;
  font-family: 'Inter', sans-serif;
  border-left: 4px solid;
}}
.banner-info    {{ background: rgba(96,165,250,0.08); border-color: {INFO};    color: {SEC}; }}
.banner-warn    {{ background: rgba(245,197,24,0.08); border-color: {ACCENT};  color: {SEC}; }}
.banner-success {{ background: rgba(34,197,94,0.08);  border-color: {SUCCESS}; color: {SEC}; }}
.banner-error   {{ background: rgba(239,68,68,0.08);  border-color: {WARN};    color: {SEC}; }}

/* ── Code viewer ── */
.code-header {{
  background: {BG3};
  border: 1px solid #22222e;
  border-bottom: none;
  border-radius: 2px 2px 0 0;
  padding: 8px 14px;
  display: flex; align-items: center; gap: 8px;
}}
.code-dot {{ width: 10px; height: 10px; border-radius: 50%; }}

/* ── Running pill ── */
.running-pill {{
  display: inline-flex; align-items: center; gap: 8px;
  background: rgba(245,197,24,0.1);
  border: 1px solid {ACCENT}44;
  border-radius: 2px;
  padding: 6px 14px;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.72rem;
  color: {ACCENT};
  font-weight: 500;
  letter-spacing: 0.04em;
}}
.spinner {{
  width: 14px; height: 14px;
  border: 2px solid {ACCENT}44;
  border-top-color: {ACCENT};
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  flex-shrink: 0;
}}
@keyframes spin {{ to {{ transform: rotate(360deg); }} }}

/* ── HITL gate ── */
.gate-block {{
  background: {BG2};
  border: 2px solid {ACCENT};
  border-radius: 2px;
  padding: 22px 26px;
  margin-bottom: 20px;
}}
.gate-title {{
  font-family: 'Source Serif 4', Georgia, serif;
  font-size: 1.1rem;
  font-weight: 700;
  font-style: italic;
  color: {TEXT};
  margin-bottom: 6px;
}}
.gate-sub {{ font-size: 0.82rem; color: {SEC}; font-weight: 300; margin-bottom: 16px; line-height: 1.6; }}

/* ── Buttons ── */
.stButton > button {{
  background: {ACCENT} !important;
  color: #0f0f12 !important;
  font-weight: 600 !important;
  border-radius: 2px !important;
  border: none !important;
  font-family: 'Inter', sans-serif !important;
  font-size: 0.82rem !important;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  transition: opacity 0.15s !important;
}}
.stButton > button:hover {{ opacity: 0.88 !important; }}
.stButton > button:disabled {{
  background: {BG3} !important;
  color: {MUTED} !important;
  border: 1px solid #22222e !important;
}}

/* ── Inputs ── */
.stTextArea textarea {{
  background: {BG3} !important;
  color: {TEXT} !important;
  border: 1px solid #33334a !important;
  border-radius: 2px !important;
  font-family: 'Inter', sans-serif !important;
  font-size: 0.875rem !important;
  resize: vertical;
}}
.stTextArea textarea:focus {{
  border-color: {ACCENT} !important;
  box-shadow: 0 0 0 1px {ACCENT}44 !important;
}}
.stSelectbox > div > div {{
  background: {BG3} !important;
  border: 1px solid #33334a !important;
  border-radius: 2px !important;
  color: {TEXT} !important;
}}

/* ── Misc ── */
hr {{ border-color: #22222e !important; margin: 24px 0 !important; }}
.stMarkdown p {{ color: {SEC} !important; font-weight: 300; line-height: 1.7; }}
h1,h2,h3 {{ color: {TEXT} !important; font-family: 'Source Serif 4', Georgia, serif !important; }}
code {{
  font-family: 'IBM Plex Mono', monospace !important;
  background: {BG3} !important;
  padding: 2px 7px !important;
  border-radius: 2px !important;
  font-size: 0.78em !important;
  color: {ACCENT} !important;
}}
[data-testid="stExpander"] {{
  background: {BG2} !important;
  border: 1px solid #22222e !important;
  border-radius: 2px !important;
}}
label {{
  color: {SEC} !important;
  font-size: 0.78rem !important;
  font-family: 'Inter', sans-serif !important;
  letter-spacing: 0.02em;
}}
::-webkit-scrollbar {{ width: 5px; height: 5px; }}
::-webkit-scrollbar-track {{ background: transparent; }}
::-webkit-scrollbar-thumb {{ background: #33334a; border-radius: 3px; }}
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════════════
AGENTS = [
    {"key": "conductor",     "label": "Conductor",     "icon": "🎯"},
    {"key": "planner",       "label": "Planner",       "icon": "📐"},
    {"key": "plan_reviewer", "label": "Plan Reviewer", "icon": "🔍"},
    {"key": "coder",         "label": "Coder",         "icon": "💻"},
    {"key": "code_reviewer", "label": "Code Reviewer", "icon": "🧐"},
    {"key": "test_engineer", "label": "Test Engineer", "icon": "🧪"},
    {"key": "debugger",      "label": "Debugger",      "icon": "🐛"},
    {"key": "mergemaster",   "label": "Mergemaster",   "icon": "🔀"},
]

PHASES = [
    {"key": "planning",      "label": "Plan",    "icon": "📐"},
    {"key": "plan_review",   "label": "Review",  "icon": "🔍"},
    {"key": "plan_approval", "label": "Gate",    "icon": "🔒"},
    {"key": "coding",        "label": "Code",    "icon": "💻"},
    {"key": "code_review",   "label": "Check",   "icon": "🧐"},
    {"key": "code_approval", "label": "Gate",    "icon": "🔒"},
    {"key": "debugging",     "label": "Debug",   "icon": "🐛"},
    {"key": "testing",       "label": "Test",    "icon": "🧪"},
    {"key": "merging",       "label": "Merge",   "icon": "🔀"},
    {"key": "completed",     "label": "Done",    "icon": "✓"},
]
PHASE_ORDER = [p["key"] for p in PHASES]

EXAMPLE_TASKS = [
    "Build a FastAPI REST service with CRUD, SQLite persistence, and Pydantic validation.",
    "Create a Python CLI tool that watches a folder and auto-generates CSV summary reports.",
    "Implement a Redis sliding-window rate limiter middleware for an async Python web app.",
    "Write a web scraper that collects job postings from 3 boards and deduplicates results.",
    "Build a Python package with pytest tests that parses and validates OpenAPI 3.x specs.",
]

NAV_ITEMS = [
    "Overview",
    "Live Agent Feed",
    "Pipeline & Agents",
    "Generated Code",
    "Report & Review",
]

# ═══════════════════════════════════════════════════════════════════
#  SESSION STATE
# ═══════════════════════════════════════════════════════════════════
def _init():
    defs = {
        "pipeline_id":    None,
        "running":        False,
        "current_phase":  "idle",
        "agent_statuses": {a["key"]: "waiting" for a in AGENTS},
        "chat_messages":  [],
        "code_changes":   [],
        "final_report":   None,
        "error":          None,
        "review_status":  "pending",
        "tasks_total":    0,
        "tasks_done":     0,
        "issues_found":   0,
        "start_time":     None,
        "end_time":       None,
        "msg_queue":      queue.Queue(),
        "thread_active":  False,
        "_prefill":       "",
    }
    for k, v in defs.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init()

# ═══════════════════════════════════════════════════════════════════
#  PIPELINE RUNNER
# ═══════════════════════════════════════════════════════════════════
def _run_thread(task: str, q: queue.Queue):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_run_async(task, q))
    except Exception as e:
        q.put({"type": "error", "text": str(e)})
    finally:
        loop.close()

async def _run_async(task: str, q: queue.Queue):
    try:
        from code_assistant.workflows.coding_pipeline import CodingPipeline
    except ImportError as e:
        q.put({"type": "error", "text": f"Import error: {e}"})
        return

    q.put({"type": "chat", "sender": "System", "color": INFO,
           "text": f"Pipeline started — {task[:80]}..."})

    pipeline = CodingPipeline()
    orig_notify = pipeline.state_manager._notify_listeners

    PHASE_AGENT = {
        "planning": "planner", "plan_review": "plan_reviewer",
        "plan_approval": "plan_reviewer", "coding": "coder",
        "code_review": "code_reviewer", "code_approval": "code_reviewer",
        "debugging": "debugger", "testing": "test_engineer",
        "merging": "mergemaster", "completed": "mergemaster",
    }

    def _notify(event, state, data=None):
        orig_notify(event, state, data)
        phase = state.current_phase
        q.put({"type": "phase", "phase": phase, "pid": state.pipeline_id})
        ag = PHASE_AGENT.get(phase)
        if ag:
            q.put({"type": "agent", "agent": ag, "status": "active"})

        if event == "code_change" and data:
            q.put({"type": "code", "data": data})
            q.put({"type": "chat", "sender": "Coder", "color": AGENT_COLORS["coder"],
                   "text": f"Wrote {data.get('file_path','?')} ({data.get('change_type','edit')})"})
        elif event == "review" and data:
            ok = "✓" if data.get("status") == "approved" else "✗"
            rv = data.get("reviewer", "reviewer").replace("_", " ").title()
            q.put({"type": "chat", "sender": rv, "color": AGENT_COLORS.get("plan_reviewer", SEC),
                   "text": f"{ok} {data.get('status','?')} — {str(data.get('comments',''))[:100]}"})
        elif event == "task_added" and data:
            q.put({"type": "chat", "sender": "Conductor", "color": AGENT_COLORS["conductor"],
                   "text": f"Task: {data.title}"})

    pipeline.state_manager._notify_listeners = _notify

    try:
        q.put({"type": "chat", "sender": "Conductor", "color": AGENT_COLORS["conductor"],
               "text": "Conductor online. Initialising LangGraph workflow…"})
        result = await pipeline.execute(task)
        q.put({"type": "pid", "id": result.pipeline_id})
        q.put({"type": "result", "result": result.to_dict()})

        ps = pipeline.state_manager.get_pipeline(result.pipeline_id)
        cp = ps.current_phase if ps else "completed"

        if cp in ("plan_approval", "code_approval"):
            q.put({"type": "needs_approval"})
            q.put({"type": "chat", "sender": "System", "color": ACCENT,
                   "text": f"Pipeline paused at {cp} — awaiting your decision."})
        else:
            q.put({"type": "done"})
            q.put({"type": "chat", "sender": "System", "color": SUCCESS,
                   "text": "Pipeline completed successfully."})
    except Exception as e:
        q.put({"type": "error", "text": str(e)})
        q.put({"type": "chat", "sender": "System", "color": WARN,
               "text": f"Error: {str(e)[:200]}"})
    finally:
        await pipeline.shutdown()

def _resume_thread(pid: str, decision: str, feedback: str, q: queue.Queue):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_resume_async(pid, decision, feedback, q))
    except Exception as e:
        q.put({"type": "error", "text": str(e)})
    finally:
        loop.close()

async def _resume_async(pid, decision, feedback, q):
    try:
        from code_assistant.workflows.coding_pipeline import CodingPipeline
    except ImportError as e:
        q.put({"type": "error", "text": str(e)}); return
    pipeline = CodingPipeline()
    try:
        q.put({"type": "chat", "sender": "System", "color": ACCENT,
               "text": f"Resuming with decision: {decision}"})
        result = await pipeline.resume(pid, decision, feedback or None)
        q.put({"type": "result", "result": result.to_dict()})
        q.put({"type": "done"})
        q.put({"type": "chat", "sender": "System", "color": SUCCESS,
               "text": "Pipeline completed after resume."})
    except Exception as e:
        q.put({"type": "error", "text": str(e)})
    finally:
        await pipeline.shutdown()

# ═══════════════════════════════════════════════════════════════════
#  QUEUE DRAIN
# ═══════════════════════════════════════════════════════════════════
def drain_queue():
    q: queue.Queue = st.session_state.msg_queue
    while not q.empty():
        try:
            m = q.get_nowait()
        except queue.Empty:
            break
        t = m.get("type")
        if t == "phase":
            st.session_state.current_phase = m["phase"]
            if "pid" in m:
                st.session_state.pipeline_id = m["pid"]
        elif t == "agent":
            st.session_state.agent_statuses[m["agent"]] = m["status"]
        elif t == "pid":
            st.session_state.pipeline_id = m["id"]
        elif t == "chat":
            st.session_state.chat_messages.append({
                "sender": m["sender"], "text": m["text"],
                "color": m.get("color", SEC),
                "ts": datetime.now().strftime("%H:%M:%S"),
            })
        elif t == "code":
            st.session_state.code_changes.append(m["data"])
        elif t == "result":
            r = m["result"]
            st.session_state.tasks_total  = r.get("total_tasks", 0)
            st.session_state.tasks_done   = r.get("completed_tasks", 0)
            st.session_state.issues_found = r.get("issues_found", 0)
            st.session_state.final_report = r
        elif t == "needs_approval":
            st.session_state.review_status = "needs_approval"
        elif t == "done":
            st.session_state.running       = False
            st.session_state.thread_active = False
            st.session_state.current_phase = "completed"
            st.session_state.end_time      = datetime.now().isoformat()
            for a in AGENTS:
                if st.session_state.agent_statuses[a["key"]] == "active":
                    st.session_state.agent_statuses[a["key"]] = "done"
        elif t == "error":
            st.session_state.error         = m["text"]
            st.session_state.running       = False
            st.session_state.thread_active = False

# ═══════════════════════════════════════════════════════════════════
#  GRAPHVIZ PIPELINE DIAGRAM
# ═══════════════════════════════════════════════════════════════════
def build_graph(phase: str):
    import graphviz
    PMAP = {
        "planning": "planning", "plan_review": "plan_review",
        "plan_approval": "plan_gate", "coding": "coding",
        "code_review": "code_review", "code_approval": "code_gate",
        "debugging": "debugging", "testing": "testing",
        "merging": "merging", "completed": "merging",
    }
    active = PMAP.get(phase, "")
    idx    = PHASE_ORDER.index(phase) if phase in PHASE_ORDER else -1
    done   = {PMAP[p] for p in PHASE_ORDER[:idx] if PMAP.get(p)}

    g = graphviz.Digraph("p", graph_attr={
        "rankdir": "LR", "bgcolor": BG2,
        "pad": "0.35", "splines": "ortho",
        "nodesep": "0.45", "ranksep": "0.6",
    }, node_attr={
        "fontname": "IBM Plex Mono, monospace",
        "fontsize": "10", "style": "filled,rounded",
        "shape": "box", "margin": "0.22,0.15", "penwidth": "1.4",
    }, edge_attr={
        "color": "#33334a", "penwidth": "1.3",
        "arrowsize": "0.65", "fontname": "IBM Plex Mono",
        "fontsize": "8", "fontcolor": MUTED,
    })

    nodes = [
        ("planning",    "Planning"),
        ("plan_review", "Plan Review"),
        ("plan_gate",   "Plan Gate\n[HITL]"),
        ("coding",      "Coding"),
        ("code_review", "Code Review"),
        ("code_gate",   "Code Gate\n[HITL]"),
        ("debugging",   "Debugging"),
        ("testing",     "Testing"),
        ("merging",     "Merging"),
    ]
    for nid, lbl in nodes:
        if nid == active:
            g.node(nid, label=lbl, fillcolor="#2a2200", fontcolor=ACCENT,
                   color=ACCENT, penwidth="2.2")
        elif nid in done:
            g.node(nid, label=lbl, fillcolor="#0f2a1a", fontcolor=SUCCESS,
                   color=SUCCESS)
        elif nid in ("plan_gate", "code_gate"):
            g.node(nid, label=lbl, fillcolor=BG3, fontcolor=MUTED,
                   color="#33334a", shape="diamond")
        else:
            g.node(nid, label=lbl, fillcolor=BG3, fontcolor=SEC,
                   color="#33334a")

    g.edge("planning",    "plan_review")
    g.edge("plan_review", "plan_gate")
    g.edge("plan_gate",   "coding",    label="approved")
    g.edge("plan_gate",   "planning",  label="rejected")
    g.edge("coding",      "code_review")
    g.edge("code_review", "code_gate")
    g.edge("code_gate",   "testing",   label="approved")
    g.edge("code_gate",   "debugging", label="needs fix")
    g.edge("debugging",   "coding")
    g.edge("testing",     "merging")
    return g

# ═══════════════════════════════════════════════════════════════════
#  SHARED HELPERS
# ═══════════════════════════════════════════════════════════════════
def page_header(eyebrow: str, title: str, sub: str):
    st.markdown(f"""
    <div class="page-header">
      <div class="page-header-eyebrow">{eyebrow}</div>
      <div class="page-header-title">{title}</div>
      <div class="page-header-sub">{sub}</div>
      <div class="page-header-rule"></div>
    </div>
    """, unsafe_allow_html=True)

def section_title(eyebrow: str, title: str):
    st.markdown(f"""
    <div class="section-eyebrow">{eyebrow}</div>
    <div class="section-title">{title}</div>
    """, unsafe_allow_html=True)

def kpi(col, value: str, label: str, sub: str, sub_color: str = SEC):
    col.markdown(f"""
    <div class="kpi-card">
      <div class="kpi-value">{value}</div>
      <div class="kpi-label">{label}</div>
      <div class="kpi-sub" style="color:{sub_color};">{sub}</div>
    </div>
    """, unsafe_allow_html=True)

def banner(msg: str, kind: str = "info"):
    icons = {"info": "ℹ", "warn": "⚠", "success": "✓", "error": "✗"}
    st.markdown(f'<div class="banner banner-{kind}">{icons.get(kind,"•")} {msg}</div>',
                unsafe_allow_html=True)

def elapsed() -> str:
    if not st.session_state.start_time:
        return "—"
    s = datetime.fromisoformat(st.session_state.start_time)
    e = datetime.fromisoformat(st.session_state.end_time) if st.session_state.end_time else datetime.now()
    sec = int((e - s).total_seconds())
    return f"{sec//60}m {sec%60}s"

def phase_bar():
    phase = st.session_state.current_phase
    cur   = PHASE_ORDER.index(phase) if phase in PHASE_ORDER else -1
    html  = '<div class="phase-bar">'
    for i, p in enumerate(PHASES):
        cls = "phase-step"
        if i < cur:   cls += " done"
        elif i == cur: cls += " active"
        html += f'<div class="{cls}"><span class="ph-icon">{p["icon"]}</span>{p["label"]}</div>'
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)

def agent_grid():
    html = '<div class="agent-grid">'
    for a in AGENTS:
        st_ = st.session_state.agent_statuses.get(a["key"], "waiting")
        cls   = f"agent-card {st_}"
        badge_cls = {"active": "badge-active", "done": "badge-done",
                     "error": "badge-error", "waiting": "badge-wait"}.get(st_, "badge-wait")
        badge_lbl = {"active": "Active", "done": "Done",
                     "error": "Error",   "waiting": "Idle"}.get(st_, "Idle")
        col = AGENT_COLORS.get(a["key"], SEC)
        html += f"""
        <div class="{cls}">
          <div class="agent-icon" style="color:{col};">{a["icon"]}</div>
          <div class="agent-name">{a["label"]}</div>
          <div class="agent-badge {badge_cls}">{badge_lbl}</div>
        </div>"""
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)

def chat_feed():
    msgs = st.session_state.chat_messages[-80:]
    if not msgs:
        st.markdown(f'<div class="chat-wrap"><div class="chat-empty">No messages yet.<br>Start a pipeline to see live agent communication.</div></div>',
                    unsafe_allow_html=True)
        return
    inner = ""
    for m in msgs:
        initials = "".join(w[0] for w in m["sender"].split()[:2]).upper()
        c = m.get("color", SEC)
        inner += f"""
        <div class="chat-msg">
          <div class="chat-avatar" style="background:{c}18; color:{c}; border:1px solid {c}33;">{initials}</div>
          <div class="chat-bubble">
            <div class="chat-sender" style="color:{c};">{m["sender"]}</div>
            <div class="chat-text">{m["text"]}</div>
            <div class="chat-ts">{m.get("ts","")}</div>
          </div>
        </div>"""
    st.markdown(f'<div class="chat-wrap" id="cf">{inner}</div>', unsafe_allow_html=True)
    st.markdown("<script>(function(){var e=document.getElementById('cf');if(e)e.scrollTop=e.scrollHeight;})();</script>",
                unsafe_allow_html=True)

def hitl_gate():
    phase = st.session_state.current_phase
    rs    = st.session_state.review_status
    if rs != "needs_approval" and phase not in ("plan_approval", "code_approval"):
        return
    gate_name = "Plan" if "plan" in str(phase) else "Code"
    st.markdown(f"""
    <div class="gate-block">
      <div class="gate-title">Human Review Required — {gate_name}</div>
      <div class="gate-sub">
        The pipeline has paused and is waiting for your decision.
        Review the {gate_name.lower()} output above, then approve or reject below.
      </div>
    </div>
    """, unsafe_allow_html=True)

    fb = st.text_area("Feedback (required if rejecting):", height=80, key="hitl_fb",
                      placeholder="e.g. The plan is missing error handling…")
    c1, c2, _ = st.columns([1, 1, 3])
    with c1:
        if st.button(f"✓  Approve {gate_name}", key="btn_approve", use_container_width=True):
            _do_resume("approved", fb)
    with c2:
        if st.button(f"✗  Reject {gate_name}", key="btn_reject", use_container_width=True):
            if not fb.strip():
                st.warning("Please add feedback before rejecting.")
            else:
                _do_resume("rejected", fb)

def _do_resume(decision, feedback):
    pid = st.session_state.pipeline_id
    if not pid:
        st.error("No active pipeline."); return
    st.session_state.update({"running": True, "review_status": "pending",
                             "msg_queue": queue.Queue()})
    t = threading.Thread(target=_resume_thread,
                         args=(pid, decision, feedback, st.session_state.msg_queue), daemon=True)
    t.start()
    st.session_state.thread_active = True
    st.rerun()

# ═══════════════════════════════════════════════════════════════════
#  SIDEBAR
# ═══════════════════════════════════════════════════════════════════
with st.sidebar:
    # Logo
    st.markdown(f"""
    <div style="padding:10px 0 24px; border-bottom:1px solid #22222e; margin-bottom:4px;">
      <div style="font-family:'Source Serif 4',Georgia,serif; font-size:1.35rem;
                  font-weight:700; font-style:italic; color:{TEXT}; line-height:1.15;">
        BAND<br>
        <span style="color:{ACCENT}; font-style:normal; font-weight:600;">Code Assistant</span>
      </div>
      <div style="font-family:'IBM Plex Mono',monospace; font-size:0.58rem; color:{SEC};
                  margin-top:8px; text-transform:uppercase; letter-spacing:0.2em; font-weight:400;">
        Multi-Agent Pipeline
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### Navigation")
    nav = st.radio("Go to", NAV_ITEMS, label_visibility="collapsed")

    st.markdown("### Quick Tasks")
    for ex in EXAMPLE_TASKS:
        if st.button(ex[:52] + "…", key=f"ex_{ex[:16]}", use_container_width=True):
            st.session_state._prefill = ex

    st.markdown("<hr style='border-color:#22222e; margin:20px 0;'>", unsafe_allow_html=True)

    # Env status
    api_key = (os.getenv("OVERALL_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
               or os.getenv("OPENAI_API_KEY") or "")
    ws_url  = os.getenv("THENVOI_WS_URL", "")

    env_ok  = bool(api_key) and "your" not in api_key.lower()
    ws_ok   = bool(ws_url)

    st.markdown(f"""
    <div style="font-family:'IBM Plex Mono',monospace; font-size:0.62rem;
                color:{SEC}; line-height:1.9; letter-spacing:0.04em;">
      LLM Key &nbsp;{'<span style="color:' + SUCCESS + ';">✓</span>' if env_ok else '<span style="color:' + WARN + ';">✗ missing</span>'}<br>
      BAND WS &nbsp;{'<span style="color:' + SUCCESS + ';">✓</span>' if ws_ok  else '<span style="color:' + ACCENT + ';">⚠ local mode</span>'}<br>
      Agents &nbsp;&nbsp;8 agents<br>
      Engine &nbsp;&nbsp;LangGraph + Claude
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<hr style='border-color:#22222e; margin:16px 0;'>", unsafe_allow_html=True)

    if st.session_state.running:
        st.markdown('<div class="running-pill"><div class="spinner"></div>Pipeline running…</div>',
                    unsafe_allow_html=True)
    elif st.button("Reset Session", use_container_width=True, key="btn_reset"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

# ═══════════════════════════════════════════════════════════════════
#  DRAIN + AUTO-REFRESH
# ═══════════════════════════════════════════════════════════════════
drain_queue()
if st.session_state.running or st.session_state.thread_active:
    import time; time.sleep(0.4)
    st.rerun()

# ═══════════════════════════════════════════════════════════════════
#  PAGE: OVERVIEW
# ═══════════════════════════════════════════════════════════════════
if nav == "Overview":
    page_header(
        "Multi-Agent Coding Platform",
        "BAND Code Assistant",
        "An eight-agent pipeline — Conductor, Planner, Coder, Reviewer, Tester, Debugger, "
        "Mergemaster — that plans, writes, reviews, tests, and merges your code automatically "
        "through the BAND coordination layer."
    )

    # Error
    if st.session_state.error:
        banner(st.session_state.error, "error")

    # ── Task form ─────────────────────────────────────────────────
    section_title("Step 1", "Describe your task")

    prefill = st.session_state.pop("_prefill", "") or ""
    task = st.text_area(
        "Task description",
        value=prefill,
        height=100,
        placeholder="e.g. Build a FastAPI REST service with CRUD operations, SQLite persistence, and full pytest coverage.",
        key="task_area",
        disabled=st.session_state.running,
        label_visibility="collapsed",
    )

    col_btn, col_info, col_id = st.columns([2, 3, 2])
    with col_btn:
        launch = st.button(
            "Launch Pipeline",
            key="btn_launch",
            use_container_width=True,
            disabled=st.session_state.running or not task.strip(),
        )
    with col_info:
        if st.session_state.running:
            st.markdown('<div class="running-pill" style="margin-top:4px;"><div class="spinner"></div>Agents are working…</div>',
                        unsafe_allow_html=True)
    with col_id:
        if st.session_state.pipeline_id:
            pid_short = st.session_state.pipeline_id[:8]
            st.markdown(f'<div style="font-family:\'IBM Plex Mono\',monospace; font-size:0.68rem; color:{MUTED}; margin-top:10px; text-align:right;">ID: <span style="color:{SEC};">{pid_short}…</span></div>',
                        unsafe_allow_html=True)

    if launch and task.strip():
        st.session_state.update({
            "pipeline_id": None, "running": True,
            "current_phase": "planning",
            "agent_statuses": {a["key"]: "waiting" for a in AGENTS},
            "chat_messages": [], "code_changes": [],
            "final_report": None, "error": None,
            "review_status": "pending", "tasks_total": 0,
            "tasks_done": 0, "issues_found": 0,
            "start_time": datetime.now().isoformat(), "end_time": None,
            "msg_queue": queue.Queue(), "thread_active": True,
        })
        t = threading.Thread(target=_run_thread,
                             args=(task.strip(), st.session_state.msg_queue), daemon=True)
        t.start()
        st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    # ── KPI row ───────────────────────────────────────────────────
    section_title("Status", "Pipeline at a glance")
    c1, c2, c3, c4, c5 = st.columns(5)
    phase_lbl = st.session_state.current_phase.replace("_", " ").title() if st.session_state.current_phase != "idle" else "—"
    kpi(c1, str(st.session_state.tasks_total or "—"), "Tasks",     "Created by planner", SEC)
    kpi(c2, str(st.session_state.tasks_done  or "—"), "Completed", "Finished tasks",     SUCCESS)
    kpi(c3, str(st.session_state.issues_found or "—"), "Issues",   "Found in review",    WARN if st.session_state.issues_found else SEC)
    kpi(c4, phase_lbl[:14],                            "Phase",    "Current stage",      ACCENT if st.session_state.running else SEC)
    kpi(c5, elapsed(),                                 "Elapsed",  "Wall-clock time",    SEC)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Phase progress ────────────────────────────────────────────
    section_title("Progress", "Pipeline stages")
    phase_bar()

    # ── HITL gate ─────────────────────────────────────────────────
    if st.session_state.review_status == "needs_approval":
        st.markdown("<br>", unsafe_allow_html=True)
        hitl_gate()

    # ── Pipeline graph ────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    section_title("Workflow", "Live pipeline graph")
    try:
        import graphviz as _gv
        st.graphviz_chart(build_graph(st.session_state.current_phase),
                          use_container_width=True)
    except ImportError:
        banner("graphviz not installed. Run: uv add graphviz", "warn")

# ═══════════════════════════════════════════════════════════════════
#  PAGE: LIVE AGENT FEED
# ═══════════════════════════════════════════════════════════════════
elif nav == "Live Agent Feed":
    page_header(
        "Real-Time Communication",
        "Live Agent Feed",
        "Every message exchanged between agents over the BAND coordination layer appears "
        "here in real-time — from the Conductor's initial kick-off through to the "
        "Mergemaster's final commit."
    )

    col_feed, col_stat = st.columns([3, 2], gap="large")

    with col_feed:
        section_title("Messages", "Agent communication log")
        chat_feed()
        if st.session_state.running:
            st.markdown('<div class="running-pill" style="margin-top:10px;"><div class="spinner"></div>Listening for agent messages…</div>',
                        unsafe_allow_html=True)
        if st.button("Clear feed", key="btn_clear_feed"):
            st.session_state.chat_messages = []
            st.rerun()

    with col_stat:
        section_title("Agents", "Status overview")
        agent_grid()

        st.markdown("<br>", unsafe_allow_html=True)
        section_title("Stages", "Phase progress")
        phase_bar()

# ═══════════════════════════════════════════════════════════════════
#  PAGE: PIPELINE & AGENTS
# ═══════════════════════════════════════════════════════════════════
elif nav == "Pipeline & Agents":
    page_header(
        "Orchestration View",
        "Pipeline & Agents",
        "The LangGraph workflow that coordinates eight specialised Claude-powered agents. "
        "Each node maps to an agent role; HITL gates pause execution for your review "
        "before committing code or merging."
    )

    section_title("Workflow", "LangGraph pipeline diagram")
    try:
        import graphviz as _gv
        st.graphviz_chart(build_graph(st.session_state.current_phase),
                          use_container_width=True)
    except ImportError:
        banner("graphviz not installed. Run: uv add graphviz", "warn")

    st.markdown("<br>", unsafe_allow_html=True)
    section_title("Agents", "Eight-agent roster")
    agent_grid()

    st.markdown("<br>", unsafe_allow_html=True)
    section_title("Stages", "Execution progress")
    phase_bar()

    # Agent reference cards
    st.markdown("<br>", unsafe_allow_html=True)
    section_title("Reference", "Agent roles")

    agent_meta = [
        ("conductor",     "🎯", "Conductor",
         "Orchestrates the full workflow. Receives the user task, routes it through agents in order, monitors progress, and produces the final summary."),
        ("planner",       "📐", "Planner",
         "Senior architect. Breaks the task into numbered subtasks, specifies exact filenames, acceptance criteria, and complexity estimates."),
        ("plan_reviewer", "🔍", "Plan Reviewer",
         "Critical engineer. Checks the plan for missing steps, file conflicts, and unclear criteria. Approves or rejects with specific reasons."),
        ("coder",         "💻", "Coder",
         "Expert implementer. Writes complete, runnable code for every subtask — with type hints, docstrings, and full error handling."),
        ("code_reviewer", "🧐", "Code Reviewer",
         "Meticulous QA. Checks for bugs, security issues, missing error handling, and style. Scores each file and provides exact fixes."),
        ("test_engineer", "🧪", "Test Engineer",
         "QA specialist. Writes comprehensive pytest tests covering happy paths, edge cases, and error scenarios to 80%+ coverage."),
        ("debugger",      "🐛", "Debugger",
         "Root-cause expert. Diagnoses failing tests or review rejections, fixes the code (not the tests), and explains each change."),
        ("mergemaster",   "🔀", "Mergemaster",
         "Integration engineer. Creates a git branch, commits all files with a proper message, and opens a pull request."),
    ]

    for i in range(0, len(agent_meta), 2):
        cols = st.columns(2, gap="medium")
        for j, col in enumerate(cols):
            if i + j >= len(agent_meta):
                break
            key, icon, name, desc = agent_meta[i + j]
            col.markdown(f"""
            <div class="narrative-block">
              <div class="narrative-title">{icon} {name}</div>
              <div class="narrative-body">{desc}</div>
            </div>
            """, unsafe_allow_html=True)

    # HITL section
    if st.session_state.review_status == "needs_approval":
        st.markdown("<br>", unsafe_allow_html=True)
        section_title("Action Required", "Human-in-the-Loop gate")
        hitl_gate()

# ═══════════════════════════════════════════════════════════════════
#  PAGE: GENERATED CODE
# ═══════════════════════════════════════════════════════════════════
elif nav == "Generated Code":
    page_header(
        "Coder Agent Output",
        "Generated Code",
        "All files created or modified by the Coder agent during this pipeline run. "
        "Select a file from the dropdown to inspect its contents."
    )

    changes = st.session_state.code_changes
    if not changes:
        st.markdown("<br>", unsafe_allow_html=True)
        banner("No code generated yet. Launch a pipeline from the Overview page.", "info")
        st.markdown(f"""
        <div class="narrative-block" style="margin-top:20px;">
          <div class="narrative-title">How code generation works</div>
          <div class="narrative-body">
            Once you submit a task, the Planner agent produces an implementation plan.
            After human approval, the Coder agent writes every file specified in the plan —
            complete with type hints, docstrings, and error handling. Files appear here
            in real-time as the Coder completes each one.
          </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        file_labels = [f"{c.get('file_path','?')}  [{c.get('change_type','edit')}]"
                       for c in changes]
        selected = st.selectbox("Select file", file_labels, key="code_sel",
                                label_visibility="visible")
        idx = file_labels.index(selected)
        ch  = changes[idx]
        fp  = ch.get("file_path", "unknown")
        content = ch.get("content", "# No content")
        ext = fp.rsplit(".", 1)[-1] if "." in fp else "python"
        lang = ext if ext in ["python","py","js","ts","go","yaml","json","toml","sh","md","sql"] else "python"
        if lang == "py": lang = "python"

        st.markdown(f"""
        <div class="code-header">
          <div class="code-dot" style="background:#ff5f57;"></div>
          <div class="code-dot" style="background:#febc2e;"></div>
          <div class="code-dot" style="background:#28c840;"></div>
          <span style="font-family:'IBM Plex Mono',monospace; font-size:0.72rem;
                       color:{SEC}; margin-left:10px;">{fp}</span>
          <span style="font-family:'IBM Plex Mono',monospace; font-size:0.62rem;
                       color:{MUTED}; margin-left:auto;">{ch.get('change_type','edit')}</span>
        </div>
        """, unsafe_allow_html=True)
        st.code(content, language=lang)

        # All files list
        st.markdown("<br>", unsafe_allow_html=True)
        section_title("All Files", f"{len(changes)} file(s) in this run")
        for c in changes:
            col_fp, col_tp, col_ag = st.columns([3, 1, 1])
            col_fp.markdown(f'<code>{c.get("file_path","?")}</code>', unsafe_allow_html=True)
            col_tp.markdown(f'<span style="color:{SEC}; font-size:0.78rem;">{c.get("change_type","edit")}</span>', unsafe_allow_html=True)
            col_ag.markdown(f'<span style="color:{MUTED}; font-size:0.72rem; font-family:\'IBM Plex Mono\',monospace;">{c.get("agent","coder")}</span>', unsafe_allow_html=True)
        st.markdown("<hr style='border-color:#22222e;'>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════
#  PAGE: REPORT & REVIEW
# ═══════════════════════════════════════════════════════════════════
elif nav == "Report & Review":
    page_header(
        "Pipeline Results",
        "Report & Review",
        "The final pipeline report — status, timing, task counts, and any issues found. "
        "If the pipeline has paused at a Human-in-the-Loop gate, you can approve or reject below."
    )

    # HITL gate at top if needed
    if st.session_state.review_status == "needs_approval":
        hitl_gate()
        st.markdown("<br>", unsafe_allow_html=True)

    report = st.session_state.final_report
    if not report:
        banner("No report yet. Run a pipeline from the Overview page to see results here.", "info")
    else:
        status   = report.get("status", "unknown")
        s_color  = {
            "completed": SUCCESS, "running": ACCENT, "error": WARN
        }.get(status, SEC)
        s_icon   = {"completed": "✓", "running": "…", "error": "✗"}.get(status, "•")

        section_title("Summary", "Pipeline report")
        st.markdown(f"""
        <div class="narrative-block">
          <div class="narrative-title">{s_icon} Status: <span style="color:{s_color};">{status.upper()}</span></div>
          <div class="narrative-body">
            <table style="width:100%; border-collapse:collapse; font-size:0.84rem; line-height:2;">
              <tr>
                <td style="color:{MUTED}; width:180px; font-family:'IBM Plex Mono',monospace; font-size:0.72rem; text-transform:uppercase; letter-spacing:0.08em;">Pipeline ID</td>
                <td style="color:{TEXT}; font-family:'IBM Plex Mono',monospace; font-size:0.75rem;">{report.get("pipeline_id","—")}</td>
              </tr>
              <tr>
                <td style="color:{MUTED}; font-family:'IBM Plex Mono',monospace; font-size:0.72rem; text-transform:uppercase; letter-spacing:0.08em;">Started</td>
                <td style="color:{TEXT};">{report.get("start_time","—")}</td>
              </tr>
              <tr>
                <td style="color:{MUTED}; font-family:'IBM Plex Mono',monospace; font-size:0.72rem; text-transform:uppercase; letter-spacing:0.08em;">Finished</td>
                <td style="color:{TEXT};">{report.get("end_time") or "In progress…"}</td>
              </tr>
              <tr>
                <td style="color:{MUTED}; font-family:'IBM Plex Mono',monospace; font-size:0.72rem; text-transform:uppercase; letter-spacing:0.08em;">Tasks Total</td>
                <td style="color:{TEXT};">{report.get("total_tasks",0)}</td>
              </tr>
              <tr>
                <td style="color:{MUTED}; font-family:'IBM Plex Mono',monospace; font-size:0.72rem; text-transform:uppercase; letter-spacing:0.08em;">Tasks Done</td>
                <td style="color:{SUCCESS};">{report.get("completed_tasks",0)}</td>
              </tr>
              <tr>
                <td style="color:{MUTED}; font-family:'IBM Plex Mono',monospace; font-size:0.72rem; text-transform:uppercase; letter-spacing:0.08em;">Issues Found</td>
                <td style="color:{WARN if report.get('issues_found',0) else TEXT};">{report.get("issues_found",0)}</td>
              </tr>
              <tr>
                <td style="color:{MUTED}; font-family:'IBM Plex Mono',monospace; font-size:0.72rem; text-transform:uppercase; letter-spacing:0.08em;">PR URL</td>
                <td><a href="{report.get('pr_url','#')}" style="color:{ACCENT};">{report.get('pr_url','—')}</a></td>
              </tr>
            </table>
          </div>
        </div>
        """, unsafe_allow_html=True)

        if report.get("error"):
            banner(f"Error: {report['error']}", "error")

        if report.get("phases_completed"):
            section_title("Phases", "Completed stages")
            st.code(", ".join(report["phases_completed"]))

    # Raw state inspector
    st.markdown("<br>", unsafe_allow_html=True)
    section_title("Debug", "Raw pipeline state")
    if st.session_state.pipeline_id:
        with st.expander("Inspect state JSON"):
            try:
                from code_assistant.band_integration.state_manager import StateManager
                sm  = StateManager()
                raw = sm.export_state(st.session_state.pipeline_id)
                if raw:
                    st.json(json.loads(raw))
                else:
                    banner("No state data found for this pipeline.", "info")
            except Exception as e:
                banner(f"Could not load state: {e}", "warn")
    else:
        banner("No active pipeline — start one from the Overview page.", "info")

# ═══════════════════════════════════════════════════════════════════
#  FOOTER
# ═══════════════════════════════════════════════════════════════════
st.markdown(f"""
<hr style="border-color:#22222e; margin:40px 0 16px;">
<div style="text-align:center; font-family:'IBM Plex Mono',monospace;
            font-size:0.6rem; color:{MUTED}; letter-spacing:0.12em; line-height:2;">
  BAND CODE ASSISTANT &nbsp;·&nbsp; 8 AGENTS &nbsp;·&nbsp; LANGGRAPH &nbsp;·&nbsp;
  CLAUDE &nbsp;·&nbsp; BAND OF AGENTS HACKATHON 2026
</div>
""", unsafe_allow_html=True)
