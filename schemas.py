"""
Unified schema definitions for JobPilot.

These schemas mirror EXACTLY the structures defined inside instructions.py.
They are simple Python dictionaries representing the expected fields and default
values for all structured objects shared across the JobPilot system.

"""


PROFILE_SCHEMA = {
    "name": "",
    "location": "",
    "contact": {
        "email": "",
        "phone": "",
        "linkedin": ""
    },
    "education": [
        {
            "degree": "",
            "field": "",
            "institution": "",
            "year": ""
        }
    ],
    "experience": [
        {
            "title": "",
            "company": "",
            "start_date": "",
            "end_date": "",
            "description": ""
        }
    ],
    "skills": [],
    "job_preferences": {
        "role_types": [],
        "industries": [],
        "locations": [],
        "remote": False,
        "number_of_jobs_wanted": 3
    },
    "additional_notes": "",
    "update_required": False,
    "last_update": 0
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




JOB_FILTER_OUTPUT_SCHEMA = {
    "pass": False,
    "score": 0,
    "rationale": ""
}



schemas = {
    "PROFILE_SCHEMA": PROFILE_SCHEMA,
    "JOB_DETAILS_SCHEMA": JOB_DETAILS_SCHEMA,
    "JOB_FILTER_OUTPUT_SCHEMA": JOB_FILTER_OUTPUT_SCHEMA,
}
