"""
JobPilot — Autonomous Job Ingestion Pipeline (FINAL VERSION)

Pipeline:
1. Use ADK Google Search to discover job URLs
2. Fetch raw HTML for each URL
3. Extract structured job details using LLM
4. Insert into ChromaDB using SentenceTransformer embeddings
5. Print summary

This script matches main.py perfectly.
"""

import os
import hashlib
import requests
import chromadb
from sentence_transformers import SentenceTransformer
from chromadb.utils import embedding_functions


CHROMA_DB_PATH = "/kaggle/working/jobpilot_chroma_db"   

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"
}

JOB_DETAILS_SCHEMA = {
    "job_id": "",
    "title": "",
    "company": "",
    "location": "",
    "employment_type": "",
    "salary": "",
    "job_description": "",
    "requirements": [],
    "qualifications": [],
    "skills_mentioned": [],
    "apply_url": ""
}


class LocalEmbeddingFunction:
    def __init__(self):
        self.model = SentenceTransformer("all-MiniLM-L6-v2")

    def __call__(self, input):
        if isinstance(input, str):
            input = [input]
        return self.model.encode(input, convert_to_numpy=True).tolist()

    def name(self):
        return "local-mini-lm-l6-v2"

embedding_fn = LocalEmbeddingFunction()


def connect_to_chromadb():
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    jobs = client.get_or_create_collection(
        name="jobs",
        metadata={"hnsw:space": "cosine"},
        embedding_function=embedding_fn
    )
    return jobs


from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.google_search_tool import google_search

def job_link_search(tool_context, query: str, n_results: int = 15):
    """
    Uses ADK Google Search to retrieve job URLs.
    Returns only clean http/https URLs.
    """
    try:
        output = google_search(query=query, n_results=n_results)
        raw = output.get("search_results", [])

        urls = []
        for item in raw:
            link = item.get("link")
            if isinstance(link, str) and link.startswith("http"):
                urls.append(link)

        return {"query": query, "count": len(urls), "urls": urls}

    except Exception as e:
        return {"query": query, "count": 0, "urls": [], "error": str(e)}

job_link_search_tool_adk = FunctionTool(func=job_link_search)



def get_job_urls(query="machine learning engineer remote", n_results=15):
    """
    Uses ADK tool to discover real job posting URLs.
    """
    result = job_link_search_tool_adk.run({
        "query": query,
        "n_results": n_results
    })

    urls = result.get("urls", [])
    print(f"[INFO] ADK search discovered {len(urls)} job links.")
    return urls



def fetch_html(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=12)
        if resp.status_code == 200:
            return resp.text
        print(f"[WARN] Failed {url} — status {resp.status_code}")
    except Exception as e:
        print(f"[ERROR] Fetch error for {url}: {e}")
    return None



from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini

HTML_EXTRACTION_INSTRUCTION = """
You are the Job HTML Extraction Agent.

Given raw HTML and a job URL, extract job details into JOB_DETAILS_SCHEMA.

Output EXACTLY this JSON dict:

{
  "job_id": "<SHA256(url)[:16]>",
  "title": "",
  "company": "",
  "location": "",
  "employment_type": "",
  "salary": "",
  "job_description": "",
  "requirements": [],
  "qualifications": [],
  "skills_mentioned": [],
  "apply_url": "<same as input url>"
}

RULES:
- Extract ONLY what appears in the HTML.
- NEVER hallucinate information.
- Missing fields → leave empty.
- All lists MUST be lists of strings.
- No markdown, no commentary.
"""

gemini_flash = Gemini(model="gemini-2.5-flash")

html_extractor_agent = LlmAgent(
    model=gemini_flash,
    name="html_extractor_agent",
    description="Extracts structured job details from raw HTML.",
    instruction=HTML_EXTRACTION_INSTRUCTION
)

def parse_job_html(html: str, url: str) -> dict:
    job_id = hashlib.sha256(url.encode()).hexdigest()[:16]

    response = html_extractor_agent.run({
        "url": url,
        "html": html
    })

    # Enforce schema
    response["job_id"] = job_id
    response["apply_url"] = url

    # Ensure all keys exist
    for k, v in JOB_DETAILS_SCHEMA.items():
        response.setdefault(k, v)

    return response


def job_exists(collection, job_id: str) -> bool:
    try:
        out = collection.get(ids=[job_id])
        return len(out.get("ids", [])) > 0
    except:
        return False


def insert_job(collection, job_details: dict, raw_html: str):
    collection.add(
        ids=[job_details["job_id"]],
        documents=[raw_html],
        metadatas=[job_details]
    )



def ingest():
    jobs_collection = connect_to_chromadb()

    urls = get_job_urls(
        query="machine learning engineer remote",
        n_results=15
    )

    inserted = 0
    skipped = 0

    for url in urls:
        print(f"\n[INFO] Processing: {url}")

        html = fetch_html(url)
        if not html:
            print("[WARN] Skipping — no HTML")
            continue

        parsed = parse_job_html(html, url)
        job_id = parsed["job_id"]

        if job_exists(jobs_collection, job_id):
            print(f"[INFO] Skipped (already exists): {job_id}")
            skipped += 1
            continue

        insert_job(jobs_collection, parsed, html)
        print(f"[SUCCESS] Inserted: {job_id}")
        inserted += 1

    print("\n======== INGEST SUMMARY ========")
    print(f"Inserted: {inserted}")
    print(f"Skipped: {skipped}")
    print("================================\n")


if __name__ == "__main__":
    ingest()
