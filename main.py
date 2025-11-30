import os
import json
import hashlib
from typing import List, Dict, Any
from dotenv import load_dotenv
import asyncio
import requests
from pydantic import BaseModel, Field

from google.genai import types
from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.sessions import DatabaseSessionService
from google.adk.tools.agent_tool import AgentTool, ToolContext
from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.google_search_tool import google_search
from google.adk.runners import Runner
from google.adk.plugins.logging_plugin import LoggingPlugin

from schemas import (
    JOB_DETAILS_SCHEMA,
    PROFILE_SCHEMA,
    JOB_FILTER_OUTPUT_SCHEMA
)

from kaggle_secrets import UserSecretsClient

user_secrets = UserSecretsClient()
api_key = user_secrets.get_secret("GOOGLE_API_KEY")

os.environ["GOOGLE_API_KEY"] = api_key

retry_config = types.HttpRetryOptions(
    attempts=5,
    exp_base=7,
    initial_delay=1,
    http_status_codes=[429, 500, 503, 504],
)

gemini_flash = Gemini(model="gemini-2.5-flash", retry_options=retry_config)
gemini_lite = Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config)

session_service = DatabaseSessionService(
    db_url="sqlite:////kaggle/working/autoapply_sessions.db"
)

from sentence_transformers import SentenceTransformer

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


import chromadb
from chromadb.utils import embedding_functions

CHROMA_DB_PATH = "jobpilot_chroma_db"
client = chromadb.PersistentClient(path=CHROMA_DB_PATH)


jobs_collection = client.get_or_create_collection(
    name="jobs",
    metadata={"hnsw:space": "cosine"},
    embedding_function=embedding_fn
)

def chroma_query_tool(
    tool_context: ToolContext,
    query_text: str,
    top_k: int = 20
) -> Dict[str, Any]:
    """
    Performs a semantic search against the ChromaDB 'jobs' collection.

    Inputs:
        query_text (str): Dense semantic query created by job_search_agent.
        top_k (int): Number of results to return from vector search.

    Returns:
        {
            "results": [ job documents ],
            "query_text": "<query used>",
            "top_k": <int>,
            "num_returned": <int>,
            "error": None or <string>
        }
    """
    if not isinstance(query_text, str) or len(query_text.strip()) == 0:
        return {
            "results": [],
            "query_text": query_text,
            "top_k": top_k,
            "num_returned": 0,
            "error": "Invalid or empty query_text."
        }

    try:
        query_results = jobs_collection.query(
            query_texts=[query_text],
            n_results=top_k
        )

        documents = []
        if (
            query_results
            and "documents" in query_results
            and len(query_results["documents"]) > 0
        ):
            for idx, doc in enumerate(query_results["documents"][0]):
                metadata = query_results["metadatas"][0][idx]
                documents.append(metadata)

        return {
            "results": documents,
            "query_text": query_text,
            "top_k": top_k,
            "num_returned": len(documents),
            "error": None
        }

    except Exception as e:
        return {
            "results": [],
            "query_text": query_text,
            "top_k": top_k,
            "num_returned": 0,
            "error": f"CHROMA_EXCEPTION: {str(e)}"
        }

chroma_query_tool_adk = FunctionTool(func=chroma_query_tool)

def rank_job_tool(tool_context: ToolContext, jobs: List[Dict[str, Any]], top_k: int) -> Dict[str, Any]:
    if not isinstance(jobs, list):
        return {
            "ranked_jobs": [],
            "top_k": top_k,
            "total_jobs_in": 0,
            "total_jobs_ranked": 0,
            "error": "Invalid input: jobs must be a list."
        }

    valid_jobs = [j for j in jobs if isinstance(j.get("score"), (int, float))]
    ranked = sorted(valid_jobs, key=lambda j: j["score"], reverse=True)
    top_ranked = ranked[:top_k]

    return {
        "jobs": top_ranked,
        "top_k": top_k,
        "total_jobs_in": len(jobs),
        "total_jobs_ranked": len(top_ranked)
    }

rank_job_tool_adk = FunctionTool(func=rank_job_tool)

from instructions import instructions_json

orchestrator_agent = LlmAgent(
    model=gemini_flash,
    name="orchestrator_agent",
    description="Top-level controller for the JobPilot multi-agent system.",
    instruction=instructions_json['orchestrator_agent']
)

class ProfileBuilderInput(BaseModel):
    user_text: str
    existing_profile: Dict[str, Any] | None = None

profile_builder_agent = LlmAgent(
    model=gemini_flash,
    name="profile_builder_agent",
    description="Parses the user's free-form background into PROFILE_SCHEMA.",
    input_schema=ProfileBuilderInput,
    static_instruction=instructions_json['profile_builder_agent']
)

job_filter_agent = LlmAgent(
    model=gemini_lite,
    name="job_filter_agent",
    description="Evaluates user–job fit and produces a binary pass/fail and numeric score.",
    static_instruction=instructions_json['job_filter_agent']
)

class JobSearchAgentInput(BaseModel):
    profile: Dict[str, Any]
    rejection_memory: List[Any]

job_search_agent = LlmAgent(
    model=gemini_flash,
    name="job_search_agent",
    description="Searches for jobs in the existing database.",
    input_schema=JobSearchAgentInput,
    instruction=instructions_json['job_search_agent']
)

job_summarizer_agent = LlmAgent(
    model=gemini_lite,
    name="job_summarizer_agent",
    description="Generates clear, concise summaries of job postings.",
    static_instruction=instructions_json['job_summarizer_agent']
)

resume_generator_agent = LlmAgent(
    model=gemini_flash,
    name="resume_generator_agent",
    description="Generates a fully tailored resume for a specific job.",
    static_instruction=instructions_json['resume_generator_agent']
)

cover_letter_agent = LlmAgent(
    model=gemini_flash,
    name="cover_letter_generator_agent",
    description="Generates a tailored cover letter for a job.",
    instruction=instructions_json['cover_letter_generator_agent']
)

application_builder_agent = LlmAgent(
    model=gemini_flash,
    name="application_builder_agent",
    description="Agent 2 in JobPilot. Coordinates resume and cover letter generation.",
    instruction=instructions_json['application_builder_agent']
)

# === Attach Tools ===
profile_builder_agent_adk = AgentTool(agent=profile_builder_agent)
job_filter_agent_adk = AgentTool(agent=job_filter_agent)
resume_generator_agent_adk = AgentTool(agent=resume_generator_agent)
cover_letter_agent_adk = AgentTool(agent=cover_letter_agent)

orchestrator_agent.tools = [
    profile_builder_agent_adk,
    AgentTool(agent=job_search_agent),
    AgentTool(agent=job_summarizer_agent),
    AgentTool(agent=application_builder_agent),
]

job_search_agent.tools = [
    chroma_query_tool_adk,
    job_filter_agent_adk,
    rank_job_tool_adk,
]

job_filter_agent.tools = []
job_summarizer_agent.tools = []
resume_generator_agent.tools = []
cover_letter_agent.tools = []

application_builder_agent.tools = [
    resume_generator_agent_adk,
    cover_letter_agent_adk,
]

APP_NAME = "JobPilot_AgentSystem"

runner = Runner(
    agent=orchestrator_agent,
    app_name=APP_NAME,
    session_service=session_service,
    plugins=[LoggingPlugin()],
)

load_dotenv()
api_key = os.environ.get("GOOGLE_API_KEY")

async def main():
    test_input = """
Hi, my name is Ofer Harpaz Vaizman.

I'm currently based in Rockville, Maryland.
My phone number is 240-316-0830 and my email is oferharvai@gmail.com.
My LinkedIn is https://www.linkedin.com/in/ofer-v-data-analysis.

I have a BSc in Mathematics from the Open University of Israel (graduated with honors).
I also hold certifications in NASM CPT and CPR/AED.

Experience-wise, I’ve worked on several analytics and machine learning projects.
I’ve built agent-based systems (including multi-agent pipelines using Google’s ADK),
done data analysis in Python, and completed various machine learning projects ranging from
supervised models to RNNs, CNNs, and transformer-based architectures.

I also have experience tutoring students in math and assisting in coaching at a climbing gym.

My main skills include Python, data analysis, statistics, machine learning, agent systems,
and fitness coaching. I'm also familiar with TensorFlow, SQLAlchemy, and web scraping.

For job preferences:
I'm mainly looking for Data Analyst, Machine Learning Engineer, or AI Engineer roles.
I prefer remote or hybrid positions, ideally in the United States.
Industries I’m most interested in: AI, tech, startups, research organizations, or fitness tech.

I’d like to see 3 job options for now.
Let me know what roles you find.
"""

    response = await runner.run_debug(
        test_input,
        session_id="my_new_session_014"
    )

    print("\n============================")
    print("🟢 Test Run Complete")
    print("============================")
    print(response)
    print("ready")

print("Successful")
