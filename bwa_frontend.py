from __future__ import annotations
from urllib.parse import urlparse
import json
import os
import re
import zipfile
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional, List, Iterator, Tuple

import pandas as pd
import streamlit as st
from auth import sign_in, sign_up
# -----------------------------
# Import your compiled LangGraph app
# -----------------------------



# -----------------------------
# Helpers
# -----------------------------
import re

def link_references(md, evidence):
    import re

    # ✅ Fix wrong formats → convert to [1]
    md = re.sub(r"(🔗\s*)?Source\s*(\d+)", r"[\2]", md)

    # split code blocks safely
    parts = re.split(r"(```[\s\S]*?```)", md)

    for i in range(len(parts)):

        # skip code blocks completely
        if parts[i].startswith("```"):
            continue

        for idx, e in enumerate(evidence):

            if hasattr(e, "model_dump"):
                e = e.model_dump()

            url = e.get("url", "")
            if not url:
                continue

            # replace [1] → clickable link
            parts[i] = re.sub(
                rf'(?<!\w)\[{idx+1}\](?!\w)',
                f"[🔗 Source {idx+1}]({url})",
                parts[i]
            )

    return "".join(parts)

def safe_slug(title: str) -> str:
    s = title.strip().lower()
    s = re.sub(r"[^a-z0-9 _-]+", "", s)
    s = re.sub(r"\s+", "_", s).strip("_")
    return s or "blog"


def bundle_zip(md_text: str, md_filename: str, images_dir: Path) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr(md_filename, md_text.encode("utf-8"))

        if images_dir.exists() and images_dir.is_dir():
            for p in images_dir.rglob("*"):
                if p.is_file():
                    z.write(p, arcname=str(p))
    return buf.getvalue()


def images_zip(images_dir: Path) -> Optional[bytes]:
    if not images_dir.exists() or not images_dir.is_dir():
        return None
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in images_dir.rglob("*"):
            if p.is_file():
                z.write(p, arcname=str(p))
    return buf.getvalue()


def try_stream(graph_app, inputs: Dict[str, Any]) -> Iterator[Tuple[str, Any]]:
    """
    Stream graph progress if available; else invoke.
    Yields ("updates"/"values"/"final", payload).
    """
    try:
        for step in graph_app.stream(inputs, stream_mode="updates"):
            yield ("updates", step)
        out = graph_app.invoke(inputs)
        yield ("final", out)
        return
    except Exception:
        pass

    try:
        for step in graph_app.stream(inputs, stream_mode="values"):
            yield ("values", step)
        out = graph_app.invoke(inputs)
        yield ("final", out)
        return
    except Exception:
        pass

    out = graph_app.invoke(inputs)
    yield ("final", out)


def extract_latest_state(current_state: Dict[str, Any], step_payload: Any) -> Dict[str, Any]:
    if isinstance(step_payload, dict):
        if len(step_payload) == 1 and isinstance(next(iter(step_payload.values())), dict):
            inner = next(iter(step_payload.values()))
            current_state.update(inner)
        else:
            current_state.update(step_payload)
    return current_state


# -----------------------------
# Markdown renderer that supports local images
# -----------------------------
_MD_IMG_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<src>[^)]+)\)")
_CAPTION_LINE_RE = re.compile(r"^\*(?P<cap>.+)\*$")


def _resolve_image_path(src: str) -> Path:
    src = src.strip().lstrip("./")
    return Path(src).resolve()


def render_markdown_with_local_images(md: str):
    matches = list(_MD_IMG_RE.finditer(md))
    if not matches:
        st.markdown(md, unsafe_allow_html=False)
        return

    parts: List[Tuple[str, str]] = []
    last = 0
    for m in matches:
        before = md[last : m.start()]
        if before:
            parts.append(("md", before))

        alt = (m.group("alt") or "").strip()
        src = (m.group("src") or "").strip()
        parts.append(("img", f"{alt}|||{src}"))
        last = m.end()

    tail = md[last:]
    if tail:
        parts.append(("md", tail))

    i = 0
    while i < len(parts):
        kind, payload = parts[i]

        if kind == "md":
            st.markdown(payload, unsafe_allow_html=False)
            i += 1
            continue

        alt, src = payload.split("|||", 1)

        caption = None
        if i + 1 < len(parts) and parts[i + 1][0] == "md":
            nxt = parts[i + 1][1].lstrip()
            if nxt.strip():
                first_line = nxt.splitlines()[0].strip()
                mcap = _CAPTION_LINE_RE.match(first_line)
                if mcap:
                    caption = mcap.group("cap").strip()
                    rest = "\n".join(nxt.splitlines()[1:])
                    parts[i + 1] = ("md", rest)

        if src.startswith("http://") or src.startswith("https://"):
            st.image(src, caption=caption or (alt or None), use_container_width=True)
        else:
            img_path = _resolve_image_path(src)
            if img_path.exists():
                st.image(str(img_path), caption=caption or (alt or None), use_container_width=True)
            else:
                st.warning(f"Image not found: `{src}` (looked for `{img_path}`)")

        i += 1


# -----------------------------
# ✅ NEW: Past blogs helpers
# -----------------------------
def list_past_blogs() -> List[Path]:
    """
    Returns .md files in current working directory, newest first.
    Filters out obvious non-blog markdown files if needed.
    """
    cwd = Path(".")
    files = [p for p in cwd.glob("*.md") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def read_md_file(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def extract_title_from_md(md: str, fallback: str) -> str:
    """
    Use first '# ' heading as title if present.
    """
    for line in md.splitlines():
        if line.startswith("# "):
            t = line[2:].strip()
            return t or fallback
    return fallback


# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="LangGraph Blog Writer", layout="wide")

st.title("Blog Writing Agent")

# -----------------------------
# 🔥 CLEAN SIDEBAR
# -----------------------------
with st.sidebar:

    st.title("⚙️ Dashboard")

    # 🔐 AUTH
    st.subheader("🔐 Account")

    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Login"):
            if not email or not password:
                st.warning("Enter email & password")
            else:
                try:
                    res = sign_in(email, password)
                    if res.user:
                        st.session_state["user_id"] = res.user.id
                        st.session_state["token"] = res.session.access_token 
                        st.session_state["email"] = email
                        st.success("✅ Logged in")
                    else:
                        st.error("Login failed")
                except Exception:
                    st.error("Invalid credentials")

    with col2:
        if st.button("Signup"):
            if not email or not password:
                st.warning("Enter email & password")
            else:
                try:
                    sign_up(email, password)
                    st.success("Signup done")
                except Exception:
                    st.error("Signup failed")

    if "user_id" in st.session_state:
        st.success("🟢 Logged in")
        st.caption(f"👤 {st.session_state.get('email', 'User')}")
        if st.button("Logout"):
            st.session_state.clear()
            st.rerun()

    st.divider()   

    # ✍️ BLOG GENERATION
    st.subheader("✍️ Generate Blog")

    topic = st.text_area("Topic", height=100)
    as_of = st.date_input("Date", value=date.today())

    run_btn = st.button("🚀 Generate", type="primary")

    st.divider()

    # 📚 DATABASE BLOGS
    st.subheader("📚 Your Blogs")

    user_id = st.session_state.get("user_id")
    if not user_id:
        st.info("🔒 Login to view your blogs")
        blogs = []
    else:
        import requests

        token = st.session_state.get("token")

        if not token:
            blogs = []
        else:
            try:
                res = requests.get(
                    "http://127.0.0.1:8000/get-blogs",
                    headers={
                        "Authorization": f"Bearer {token}"
                    },
                    timeout=10
                )

                if res.status_code == 200:
                    blogs = res.json().get("data", [])
                else:
                    blogs = []

            except Exception as e:
                st.error("Failed to fetch blogs")
                blogs = []

    if not blogs:
        st.caption("No blogs found")
    else:
        for i, b in enumerate(blogs):
            title = b.get("title", "Untitled")[:30]
            date_str = (b.get("created_at") or "")[:10]

            if st.button(f"{b['title']} ({b['created_at'][:10]})", key=f"blog_{i}"):

                st.session_state["last_out"] = {
                    "merge": {
                        "final": b.get("content", "")
                    },
                    "orchestrator": {
                        "plan": {
                            "blog_title": b.get("title", "Blog"),
                            "tasks": []
                        }
                    },
                    "research": {
                        "evidence": []
                    }
                }

                st.success("Blog loaded ✅")
                



# Storage for latest run
if "last_out" not in st.session_state:
    st.session_state["last_out"] = None

# Layout
tab_plan, tab_evidence, tab_preview, tab_images, tab_logs = st.tabs(
    ["🧩 Plan", "🔎 Evidence", "📝 Markdown Preview", "🖼️ Images", "🧾 Logs"]
)

logs: List[str] = []


def log(msg: str):
    logs.append(msg)


if run_btn:

    # ✅ ADD THIS (FIRST)
    if "user_id" not in st.session_state:
        st.warning("⚠️ Please login first")
        st.stop()

    # Existing code
    if not topic.strip():
        st.warning("Please enter a topic.")
        st.stop()

    inputs: Dict[str, Any] = {
        "topic": topic.strip(),
        "mode": "",
        "needs_research": False,
        "queries": [],
        "evidence": [],
        "plan": None,
        "as_of": as_of.isoformat(),
        "recency_days": 7,
        "sections": [],
        "merged_md": "",
        "md_with_placeholders": "",
        "image_specs": [],
        "final": "",
        "user_id": st.session_state.get("user_id"),
    }

  

    import requests

    try:
        with st.spinner("⚙️ Generating blog... please wait"):

            res = requests.post(
                "http://127.0.0.1:8000/generate-blog",
                json={
                    "topic": topic,
                    "as_of": as_of.isoformat()
                },
                headers={
                    "Authorization": f"Bearer {st.session_state.get('token')}"
                },
                timeout=120
            )

            if res.status_code != 200:
                st.error("❌ API Error")
                st.stop()

            out = res.json()

            if "error" in out:
                st.error(out["error"])
                st.stop()

    except Exception as e:
        st.error("❌ Server not responding")
        st.stop()

    if "out" not in locals() or not out:
        st.error("❌ No response from backend")
        st.stop()

    st.session_state["last_out"] = out
    
    log("[final] received final state")

    # ✅ SAVE BLOG
    user_id = st.session_state.get("user_id")

    plan_obj = out.get("orchestrator", {}).get("plan")

    title = "Generated Blog"
    if isinstance(plan_obj, dict):
        title = plan_obj.get("blog_title", "Generated Blog")

    content = out.get("merge", {}).get("final")

    if not content or len(content.strip()) == 0:
        st.error("❌ Blog content not generated")
        st.stop()
    else:
        st.success("✅ Blog generated successfully")

    # if user_id:
    #     save_blog(title, content, user_id)

# Render last result (if any)
out = st.session_state.get("last_out")
if out:
    # --- Plan tab ---
    with tab_plan:
        st.subheader("Plan")
        plan_obj = out.get("orchestrator", {}).get("plan")
        if not plan_obj:
            st.info("No plan found in output.")
        else:
            if hasattr(plan_obj, "model_dump"):
                plan_dict = plan_obj.model_dump()
            elif isinstance(plan_obj, dict):
                plan_dict = plan_obj
            else:
                plan_dict = json.loads(json.dumps(plan_obj, default=str))

            st.write("**Title:**", plan_dict.get("blog_title"))
            cols = st.columns(3)
            cols[0].write("**Audience:** " + str(plan_dict.get("audience")))
            cols[1].write("**Tone:** " + str(plan_dict.get("tone")))
            cols[2].write("**Blog kind:** " + str(plan_dict.get("blog_kind", "")))

            tasks = plan_dict.get("tasks", [])
            if tasks:
                df = pd.DataFrame(
                    [
                        {
                            "id": t.get("id"),
                            "title": t.get("title"),
                            "target_words": t.get("target_words"),
                            "requires_research": t.get("requires_research"),
                            "requires_citations": t.get("requires_citations"),
                            "requires_code": t.get("requires_code"),
                            "tags": ", ".join(t.get("tags") or []),
                        }
                        for t in tasks
                    ]
                ).sort_values("id")
                st.dataframe(df, width="stretch", hide_index=True)

                with st.expander("Task details", expanded=False):

                    import json

                    router = out.get("router", {})
                    research = out.get("research", {})
                    orchestrator = out.get("orchestrator", {})
                    worker = out.get("worker", {})

                    plan_obj = orchestrator.get("plan", {})

                    # ✅ DONE BOX
                    st.success("✅ Done")

                    # =========================
                    # 🔥 1. SUMMARY JSON (TOP)
                    # =========================

                    queries = out.get("queries") or router.get("queries") or []

                    clean_json = {
                        "mode": router.get("mode"),
                        "needs_research": router.get("needs_research"),
                        "queries": queries,
                        "evidence_count": len(research.get("evidence", [])),
                        "tasks": len(plan_obj.get("tasks", [])),
                        "images": 0,
                        "sections_done": len(worker.get("sections", []))
                    }

                    st.json(clean_json)

                    st.markdown("---")

                    # =========================
                    # 🔥 2. FULL TASK DETAILS (OLD UI)
                    # =========================

                    tasks = plan_obj.get("tasks", [])

                    if tasks:
                        for task in tasks:

                            # Title
                            st.markdown(f"### 🔹 Task {task['id']}: {task['title']}")

                            # Bullets
                            for bullet in task.get("bullets", []):
                                st.markdown(f"- {bullet}")

                            # Info line
                            st.markdown(
                                f"Words: {task.get('target_words')} | "
                                f"Research: {task.get('requires_research')} | "
                                f"Citations: {task.get('requires_citations')} | "
                                f"Code: {task.get('requires_code')}"
                            )

                            st.markdown("---")
                    
    # --- Evidence tab ---
    with tab_evidence:
        st.subheader("🔎 Evidence Sources")

        # ✅ correct path
        research_data = out.get("research", {})
        evidence = research_data.get("evidence", [])

        if not evidence:
            st.warning("No evidence found")
        else:
            for ev in evidence:

                # ✅ VERY IMPORTANT FIX
                if hasattr(ev, "model_dump"):
                    ev = ev.model_dump()

                url = ev.get("url") or ev.get("link") or ev.get("source") or ""

                if not url or not url.startswith("http"):
                    continue

                title = ev.get("title") or "Open Source"
                snippet = (ev.get("snippet") or ev.get("content") or "")[:200]

                domain = urlparse(url).netloc.replace("www.", "")

                st.markdown(f"""
                    <div style="
                        border:1px solid #e5e7eb;
                        padding:18px;
                        border-radius:14px;
                        margin-bottom:14px;
                        background-color:white;
                        box-shadow:0 2px 6px rgba(0,0,0,0.05);
                    ">
                        <h4 style="margin-bottom:5px;">
                            <a href="{url}" target="_blank" style="color:#2563eb;">
                                {title}
                            </a>
                        </h4>

                        <p style="color:#555; font-size:14px;">
                            {snippet}...
                        </p>

                        <p style="font-size:12px; color:#999;">
                            🌐 {domain}
                        </p>
                    </div>
                    """, unsafe_allow_html=True)
            

    # --- Preview tab ---
    with tab_preview:
        st.subheader("Markdown Preview")

        

        final_md = out.get("merge", {}).get("final") or ""
        final_md = link_references(
            final_md,
            out.get("research", {}).get("evidence", [])
        )

        if not final_md:
            st.warning("No final markdown found.")
        else:
            render_markdown_with_local_images(final_md)

            plan_obj = out.get("orchestrator", {}).get("plan")
            if hasattr(plan_obj, "blog_title"):
                blog_title = plan_obj.blog_title
            elif isinstance(plan_obj, dict):
                blog_title = plan_obj.get("blog_title", "blog")
            else:
                blog_title = extract_title_from_md(final_md, "blog")

            md_filename = f"{safe_slug(blog_title)}.md"

            st.download_button(
                "⬇️ Download Markdown",
                data=final_md.encode("utf-8"),
                file_name=md_filename,
                mime="text/markdown",
            )

            bundle = bundle_zip(final_md, md_filename, Path("images"))

            st.download_button(
                "📦 Download Bundle (MD + images)",
                data=bundle,
                file_name=f"{safe_slug(blog_title)}_bundle.zip",
                mime="application/zip",
            )

    # --- Images tab ---
    with tab_images:
        st.subheader("Images")
        specs = out.get("image_specs") or []
        images_dir = Path("images")

        if not specs and not images_dir.exists():
            st.info("No images generated for this blog.")
        else:
            if specs:
                st.write("**Image plan:**")
                st.json(specs)

            if images_dir.exists():
                files = [p for p in images_dir.iterdir() if p.is_file()]
                if not files:
                    st.warning("images/ exists but is empty.")
                else:
                    for p in sorted(files):
                        st.image(str(p), caption=p.name, use_container_width=True)

                z = images_zip(images_dir)
                if z:
                    st.download_button(
                        "⬇️ Download Images (zip)",
                        data=z,
                        file_name="images.zip",
                        mime="application/zip",
                    )

    # --- Logs tab ---
    with tab_logs:
        st.subheader("Logs")
        if "logs" not in st.session_state:
            st.session_state["logs"] = []
        if logs:
            st.session_state["logs"].extend(logs)

        st.text_area("Event log", value="\n\n".join(st.session_state["logs"][-80:]), height=520)
else:
    st.info(" Login and enter a topic to generate your blog")