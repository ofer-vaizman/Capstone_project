
JobPilot - Autonomous Job Application System

Overview
JobPilot is an autonomous job discovery and application system built using the Google Agent Development Kit (ADK) and the Gemini 2.5 model family. The system automatically performs the full job application workflow:

Discovers job postings through an ADK-powered search tool

Fetches and parses job posting HTML into structured fields

Stores job postings in a semantic vector database (ChromaDB)

Retrieves and ranks relevant jobs for the user

Summarizes the best matches

Generates tailored resumes and cover letters for selected jobs

This project was developed as the ADK Capstone and demonstrates agent orchestration, tool integration, session memory, structured schemas, and end-to-end automation.

Core Features

Autonomous Job Discovery
The system uses the ADK google_search_tool through a custom wrapper called job_link_search_tool, which returns clean job posting URLs. No manual links are required.

HTML Ingestion Pipeline
The ingestion pipeline:

fetches the raw HTML for each job posting

sends it to an LLM extraction agent

converts HTML to structured data using the JOB_DETAILS_SCHEMA

generates a deterministic job ID

stores the result in ChromaDB with local embeddings

Structured fields include:
title
company
location
employment type
salary
job description
requirements
qualifications
skills mentioned
apply URL

Vector Database (ChromaDB)
JobPilot stores job postings in a persistent ChromaDB collection. Embeddings are generated using the SentenceTransformer model "all-MiniLM-L6-v2", which is also used during job search in the main system so that retrieval is consistent.

Raw job HTML is stored as the document, while structured job metadata is stored as the metadata object.

Multi-Agent Architecture

JobPilot contains several coordinated agents, each with strict input/output schemas:

Orchestrator Agent
Controls the entire workflow. Calls sub-agents in the required order.

Profile Builder Agent
Converts raw user text into a structured PROFILE_SCHEMA.

Job Search Agent (Agent 1)
Retrieves jobs from ChromaDB.
Filters and scores them using job_filter_agent.
Ranks the top matches using rank_job_tool.

Job Summarizer Agent
Converts structured job objects into readable summaries for the user.

Application Builder Agent (Agent 2)
Coordinates resume and cover letter creation for selected jobs.

Resume Generator Agent
Creates tailored resumes using profile and job details.

Cover Letter Generator Agent
Creates a tailored 2 to 4 paragraph cover letter.

All agents follow strict JSON schemas to prevent hallucinations and ensure pipeline stability.

AI Models Used

Gemini 2.5 Flash
Used for:
profile parsing
HTML extraction
job summarization
resume writing
cover letter writing
orchestrator reasoning

SentenceTransformer (all-MiniLM-L6-v2)
Used for ChromaDB embeddings both at ingestion time and retrieval time.

Project File Structure

main.py
The full multi-agent system including orchestrator, tools, models, and ADK runner.

ingest_jobs.py
The autonomous ingestion pipeline.
Discovers job URLs, fetches HTML, extracts fields using the LLM, and stores them in ChromaDB.

instructions.py
Contains the instructions for every agent. These are the prompts that define system behavior.

schemas.py
Contains dictionary schemas for profiles, jobs, and filter outputs.

autoapply_sessions.db
SQLite database storing ADK session state and long-term memory.

jobpilot_chroma_db
Persistent ChromaDB vector store used for retrieval.

requirements.txt
List of dependencies.

README.md
This file.

How to Run

Run the ingestion pipeline
This populates ChromaDB with live job postings:

python ingest_jobs.py

Run the JobPilot multi-agent system

await main()

This triggers the orchestrator, which:

builds the user profile
runs job search
scores and ranks jobs
summarizes them
waits for the user's selections
builds tailored resumes and cover letters
returns a full application package for each selected job

Notes

ChromaDB persistence allows jobs to remain stored between runs.
All fields follow strict schemas to ensure stability.
The pipeline avoids hallucination by extracting only what appears in HTML.
The system is fully autonomous once started.
