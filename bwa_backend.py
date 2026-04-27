from __future__ import annotations
import operator, os, re, json, time
from pathlib import Path
from typing import TypedDict, List, Optional, Annotated
from db import save_blog
from pydantic import BaseModel, ConfigDict
from langgraph.graph import StateGraph, START, END
from langchain_groq import ChatGroq
from langchain_tavily import TavilySearch

from langchain_core.messages import HumanMessage
from dotenv import load_dotenv

load_dotenv()

# =========================
# 🔧 UTILS
# =========================
def extract_json_safe(text: str):
    text = re.sub(r"```(?:json)?", "", text).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except:
        return None

def safe_llm(llm, messages, retries=3):
    for _ in range(retries):
        try:
            return llm.invoke(messages)
        except:
            time.sleep(1)
    return None

def add_toc(md: str):
    headers = re.findall(r"^## (.+)$", md, re.MULTILINE)
    toc = "\n".join(f"- [{h}](#{h.lower().replace(' ', '-')})" for h in headers)
    return f"## Table of Contents\n{toc}\n\n{md}" if headers else md

# =========================
# 📦 SCHEMA
# =========================
class Task(BaseModel):
    id: int
    title: str
    bullets: List[str]

    target_words: int = 150
    requires_research: bool = False
    requires_citations: bool = False
    requires_code: bool = False
    tags: List[str] = []

    model_config = ConfigDict(extra="ignore")

class Plan(BaseModel):
    blog_title: str
    audience: str
    tone: str
    blog_kind: str
    tasks: List[Task]
    model_config = ConfigDict(extra="ignore")

class EvidenceItem(BaseModel):
    title: str
    url: str
    snippet: Optional[str] = None

class State(TypedDict):
    topic: str
    mode: str
    needs_research: bool
    queries: List[str]
    evidence: List[EvidenceItem]
    plan: Optional[Plan]
    sections: Annotated[List[tuple[int, str]], operator.add]
    merged_md: str
    final: str
    user_id: str

# =========================
# 🤖 LLM
# =========================
llm = ChatGroq(
    model="llama-3.1-8b-instant",
    temperature=0.2,
    max_tokens=800
)

# =========================
# 🚦 ROUTER (FIXED)
# =========================
def router_node(state: State):
    prompt = f"""
Return ONLY JSON:
{{
 "needs_research": true/false,
 "mode": "closed_book",
 "queries": []
}}

Topic: {state['topic']}
"""

    res = safe_llm(llm, [HumanMessage(content=prompt)])
    data = extract_json_safe(res.content) if res else {}

    queries = data.get("queries", [])
    needs_research = data.get("needs_research", False)

    # ✅ CLEAN QUERIES
    clean_queries = []
    for q in queries:
        if isinstance(q, dict) and "question" in q:
            clean_queries.append(q["question"])
        elif isinstance(q, str):
            clean_queries.append(q)
    queries = clean_queries

    topic = state["topic"].lower()

    # 🔥 SMART RULES (IMPORTANT)
    tech_keywords = [
        "ai", "ml", "algorithm", "data", "system",
        "architecture", "pipeline", "model", "learning"
    ]

    complex_keywords = [
        "latest", "trend", "2024", "2025", "comparison",
        "vs", "difference", "advanced"
    ]

    # ✅ RULE 1: If complex topic → force research
    if any(k in topic for k in complex_keywords):
        needs_research = True

    # ✅ RULE 2: If technical topic → usually research
    if any(k in topic for k in tech_keywords):
        needs_research = True

    # ✅ RULE 3: If no queries but research needed → generate
    if needs_research and not queries:
        topic_clean = topic.replace("write", "").replace("create", "").strip()

        queries = [
            f"What is {topic_clean}?",
            f"How does {topic_clean} work?",
            f"Applications of {topic_clean}"
        ]

    # ✅ MODE FIX
    mode = "hybrid" if needs_research else "closed_book"

    return {
        "needs_research": needs_research,
        "queries": queries,
        "mode": mode
    }
def route_next(state: State):
    return "research" if state["needs_research"] else "orchestrator"

# 🔥 FILTER + SMART RANKING
def is_weak_source(item):
    url = item.get("url", "")
    snippet = item.get("snippet", "")

    bad_domains = ["pinterest", "facebook", "instagram", "quora", "youtube"]

    if any(b in url for b in bad_domains):
        return True

    if len(snippet.strip()) < 60:
        return True

    return False


def rank_sources(sources, query):
    query_words = query.lower().split()
    query_full = query.lower()

    def score(item):
        url = item.get("url", "")
        snippet = (item.get("snippet") or "").lower()

        score = 0

        # 🔥 1. Trusted domains boost
        trusted = ["wikipedia", "openai", "ibm", "aws", "microsoft"]
        if any(t in url for t in trusted):
            score += 60

        # 🔥 2. Priority boost
        if item.get("priority") == 0:
            score += 40

        # 🔥 3. Exact phrase match (VERY IMPORTANT)
        if query_full in snippet:
            score += 25

        # 🔥 4. Keyword density
        score += sum(1 for w in query_words if w in snippet) * 8

        # 🔥 5. Content richness
        score += min(len(snippet) // 70, 10)

        # 🔥 6. Penalize low-quality patterns
        if "click here" in snippet or "buy now" in snippet:
            score -= 20

        return -score

    return sorted(sources, key=score)
# =========================
# 🔎 RESEARCH
# =========================
from langchain_tavily import TavilySearch
import os

def _tavily_search(query):
    try:
        tool = TavilySearch(
            max_results=5,
            api_key=os.getenv("TAVILY_API_KEY")
        )

        results = tool.invoke(query)

        # 🔥 HANDLE BOTH CASES
        if isinstance(results, dict):
            return results.get("results", [])

        elif isinstance(results, list):
            return results

        else:
            return []

    except Exception:
        return []

def research_node(state: State):
    raw = []

    # 🔥 STEP 1: SEARCH
    for q in state.get("queries", [])[:5]:
        try:
            raw.extend(_tavily_search(q))
        except Exception as e:
            pass

    # 🔥 STEP 2: FALLBACK IF NO RAW
    if not raw:
        topic = state.get("topic", "").replace(" ", "+")

        raw = [{
            "title": f"{state.get('topic')} (Google Search)",
            "url": f"https://www.google.com/search?q={topic}",
            "snippet": f"Search results for {state.get('topic','')}"
        }]

    TRUSTED_DOMAINS = [
    "wikipedia.org",
    "ibm.com",
    "openai.com",
    "pinecone.io",
    "arxiv.org",
    "medium.com",
    "towardsdatascience.com",
    "aws.amazon.com",
    "learn.microsoft.com",
    "cloud.google.com",
    "developer.mozilla.org",
    "kaggle.com",
    "github.com"
]

    clean = []
    seen_urls = set()

    for r in raw:
        if not isinstance(r, dict):
            continue

        url = r.get("url", "")
        title = r.get("title", "")
        content = r.get("content") or r.get("snippet") or ""

        if not url or not url.startswith("http"):
            continue

        # 🔥 avoid duplicates
        if url in seen_urls:
            continue
        seen_urls.add(url)

        is_trusted = any(domain in url for domain in TRUSTED_DOMAINS)

        clean.append({
            "title": (title.split("|")[0].strip() if title else "Source"),
            "url": url,
            "snippet": (content[:300].rsplit(".", 1)[0] + ".") if content else "",
            "priority": 0 if is_trusted else 1
        })

    # 🔥 fallback if nothing trusted
    if not clean:
        topic = state.get("topic", "").replace(" ", "+")
        clean = [{
            "title": f"{state.get('topic')} - Google Search",
            "url": f"https://www.google.com/search?q={topic}",
            "snippet": "General search results",
            "priority": 1
        }]

    

    # 🔥 REMOVE BAD SOURCES
    clean = [c for c in clean if not is_weak_source(c)]

    # 🔥 SMART RANKING
    query = " ".join(state.get("queries", [])) or state.get("topic", "")
    clean = rank_sources(clean, query)[:5]

    evidence = []

    for e in clean:
        evidence.append(EvidenceItem(
            title=e.get("title", "No Title"),
            url=e.get("url", ""),
            snippet=e.get("snippet", "")
        ))

    # 🔥 STEP 6: FINAL GUARANTEE (NEVER EMPTY)
    if not evidence:
        topic_clean = state.get("topic", "").replace(" ", "+")

        evidence.append(EvidenceItem(
            title=state.get("topic", "General Topic"),
            url=f"https://www.google.com/search?q={topic_clean}",
            snippet=f"Search results for {state.get('topic','')}"
        ))

    return {"evidence": evidence}
# =========================
# 🧠 PLANNER (FIXED)
# =========================
def orchestrator_node(state: State) -> dict:
    prompt = f"""
Return ONLY JSON.

STRICT RULES:
- EXACTLY 3 tasks
- Each task must have 3 bullets

Schema:
{{
  "blog_title": "",
  "audience": "beginner",
  "tone": "simple",
  "blog_kind": "explainer",
  "tasks": [
    {{
      "id": 1,
      "title": "",
      "bullets": ["", "", ""],
      "target_words": 150,
      "requires_research": false,
      "requires_citations": true,
      "requires_code": false,
      "tags": ["basic"]
    }},
    {{
      "id": 2,
      "title": "",
      "bullets": ["", "", ""],
      "target_words": 200,
      "requires_research": true,
      "requires_citations": false,
      "requires_code": true,
      "tags": ["technical"]
    }},
    {{
      "id": 3,
      "title": "",
      "bullets": ["", "", ""],
      "target_words": 120,
      "requires_research": false,
      "requires_citations": false,
      "requires_code": false,
      "tags": ["summary"]
    }}
  ]
}}

Topic: {state['topic']}
"""

    fallback_plan = Plan(
        blog_title=state["topic"],
        audience="beginner",
        tone="simple",
        blog_kind="explainer",
        tasks=[
            Task(id=1, title="Introduction", bullets=["What","Why","Use"]),
            Task(id=2, title="How it works", bullets=["Steps","Example","Flow"], requires_code=True),
            Task(id=3, title="Summary", bullets=["Key points","Mistakes","Next steps"])
        ]
    )

    res = safe_llm(llm, [HumanMessage(content=prompt)])

    if not res:
        return {"plan": fallback_plan}

    data = extract_json_safe(res.content)

    # 🔥 FORCE EXACTLY 3 TASKS
    if not data or "tasks" not in data:
        return {"plan": fallback_plan}

    tasks = data["tasks"]

    if not isinstance(tasks, list) or len(tasks) < 3:
        return {"plan": fallback_plan}

    # ✅ TRIM EXTRA TASKS
    tasks = tasks[:3]

    try:
        # normalize structure
        clean_tasks = []

        for i, t in enumerate(tasks):
            title = t.get("title", "").lower()

            # 🔥 AUTO INTELLIGENCE
            requires_code = "code" in title or "implement" in title
            requires_research = "how" in title or "working" in title
            requires_citations = "what" in title or "definition" in title

            if "intro" in title:
                tags = ["basic"]
            elif "how" in title or "working" in title:
                tags = ["technical"]
            else:
                tags = ["summary"]

            clean_tasks.append({
                "id": i + 1,
                "title": t.get("title", f"Section {i+1}"),
                "bullets": t.get("bullets", ["A","B","C"])[:3],
                "target_words": t.get("target_words", 150),
                "requires_research": t.get("requires_research", requires_research),
                "requires_citations": t.get("requires_citations", requires_citations),
                "requires_code": t.get("requires_code", requires_code),
                "tags": t.get("tags", tags)
            })

        data["tasks"] = clean_tasks

        plan = Plan.model_validate(data)
        return {"plan": plan}

    except:
        return {"plan": fallback_plan}
# =========================

def fix_citations_safe(text, evidence):
    import re

    parts = re.split(r"(```.*?```)", text, flags=re.DOTALL)

    for i in range(len(parts)):
        if not parts[i].startswith("```"):

            for idx, e in enumerate(evidence):
                url = ""

                if hasattr(e, "model_dump"):
                    e = e.model_dump()

                url = e.get("url", "")

                if not url:
                    continue

                # 🔥 MAKE CLICKABLE
                title = e.get("title", "Source")[:60].rsplit(" ", 1)[0]

                parts[i] = re.sub(
                    rf'(?<!\d)\[{idx+1}\](?!\d)',
                    f' ([🔗 Source {idx+1}]({url}))',
                    parts[i]
                )

    return "".join(parts)

# 👷 WORKER
# =========================
def worker_node(state: State):
    plan = state["plan"]
    evidence = state.get("evidence", [])
    if not evidence:
        evidence = [EvidenceItem(
            title="Fallback Source",
            url="https://www.google.com",
            snippet="General information"
        )]
    sections = []

    # prepare citations
    citations_text = ""
    source_hint = ""
    for i, e in enumerate(evidence):
        if hasattr(e, "model_dump"):
            e = e.model_dump()

    source_hint += f"[{i+1}] → {e.get('title')}\n"
    if evidence:
        for i, e in enumerate(evidence):

            # convert object → dict
            if hasattr(e, "model_dump"):
                e = e.model_dump()

            url = e.get("url", "")

            if not url:
                continue

            title = (e.get("title") or "Source")[:60]
            citations_text += f"{i+1}. {title} ({url})\n"

    for task in plan.tasks:

        prompt = f"""
Write a HIGH-QUALITY professional blog section.

Title: {task.title}
Bullets: {task.bullets}

STYLE RULES:
- Write like an expert teacher
- Use simple but powerful explanations
- Add real-world examples
- Use short paragraphs
- Avoid repetition

CITATION RULES:
- Use ALL sources [1] to [5] at least once
- Do NOT repeat the same source multiple times
- Distribute citations across different paragraphs
- Place citations at end of sentence
- Max 1 citation per sentence

QUALITY RULES:
- Make content engaging
- Avoid generic lines
- Explain clearly
- Add value in every paragraph

Available Sources:
{citations_text}

Source Mapping:
{source_hint}
"""       

        # ✅ ADD CODE INSTRUCTION INSIDE LOOP
        if task.requires_code:
            prompt += """
- Add a simple Python code example
- Explain before code
- Use ```python format
"""

        # ✅ CALL LLM INSIDE LOOP
        try:
            res = safe_llm(llm, [HumanMessage(content=prompt)])
            content = res.content if res else "Content failed"

            content = fix_citations_safe(content, evidence)
            content = content.strip()[:2000]

        except:
            content = "Content failed"

        sections.append((task.id, content))

    return {"sections": sections}

# =========================
# 🔗 MERGE
# =========================
def merge_node(state: State):
    ordered = [s for _, s in sorted(state["sections"])]
    md = "# " + state["plan"].blog_title + "\n\n" + "\n\n".join(ordered)
    md = re.sub(
        r"# .*?\n",
        f"# {state['plan'].blog_title}\n\n*This article explains the topic in a clear and practical way.*\n\n",
        md,
        count=1)
    md = add_toc(md)
    topic = state.get("topic", "")
    google_link = f"https://www.google.com/search?q={topic.replace(' ','+')}"

    md += f"\n\n🔎 More info: [Search on Google]({google_link})"
    md += "\n\n---\n\n### 🔗 Sources Used\n"
    for e in state.get("evidence", []):
        if hasattr(e, "model_dump"):
            e = e.model_dump()

        title = e.get("title") or "Source"
        url = e.get("url") or "#"

        md += f"- [{title}]({url})\n"
    filename = state["topic"].replace(" ", "_") + ".md"
    Path(filename).write_text(md)

    # ✅ SAVE TO DATABASE
    try:
        user_id = state.get("user_id")

        if user_id:
            save_blog(
                state["plan"].blog_title,
                md,
                user_id
            )
        else:
            pass
    except Exception as e:
        pass

    return {"final": md}

# =========================
# 🔁 GRAPH
# =========================
g = StateGraph(State)

g.add_node("router", router_node)
g.add_node("research", research_node)
g.add_node("orchestrator", orchestrator_node)
g.add_node("worker", worker_node)
g.add_node("merge", merge_node)

g.add_edge(START, "router")
g.add_conditional_edges("router", route_next, {
    "research": "research",
    "orchestrator": "orchestrator"
})
g.add_edge("research", "orchestrator")
g.add_edge("orchestrator", "worker")
g.add_edge("worker", "merge")
g.add_edge("merge", END)

app = g.compile()