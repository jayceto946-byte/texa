"""Generic background job API."""
from __future__ import annotations

from fastapi import APIRouter

from backend.job_manager import get_job_manager

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
def list_jobs(type: str | None = None, limit: int = 100, book_name: str | None = None):
    jobs = get_job_manager().list_jobs(job_type=type, limit=limit, book_name=book_name)
    return {"success": True, "data": jobs}


@router.get("/{job_id}")
def get_job(job_id: str):
    job = get_job_manager().get_job(job_id)
    if not job:
        return {"success": False, "message": "Job not found"}
    return {"success": True, "data": job}


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str):
    try:
        job = get_job_manager().request_cancel(job_id)
    except KeyError:
        return {"success": False, "message": "Job not found"}
    return {"success": True, "data": job}