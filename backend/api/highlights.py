"""Chapter highlight API: persistent OCR-based chapter notes."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from knowledge.chapter_highlights import ChapterHighlightError, ChapterHighlightService, HighlightJobStore

router = APIRouter(prefix="/books", tags=["chapter-highlights"])

_service = ChapterHighlightService()
_jobs = HighlightJobStore(_service)


@router.get("/{book_name}/chapter-highlights")
def list_chapter_highlights(book_name: str):
    _jobs.reconcile_book(book_name)
    chapters = _service.list_chapters(book_name)
    return {"success": True, "data": {"book_name": book_name, "chapters": chapters}}


@router.get("/{book_name}/chapter-highlights/{chapter_id}/html")
def view_chapter_highlight_html(book_name: str, chapter_id: str, section_id: str = "all"):
    item = _service.get_highlight(book_name, chapter_id, section_id=section_id)
    html_path = Path((item or {}).get("artifacts", {}).get("html_path", ""))
    if not item or not html_path.exists() or not html_path.is_file():
        raise HTTPException(status_code=404, detail="chapter highlight html not found; please regenerate")
    return FileResponse(str(html_path), media_type="text/html; charset=utf-8")


@router.get("/{book_name}/chapter-highlights/{chapter_id}")
def get_chapter_highlight(book_name: str, chapter_id: str, section_id: str = "all"):
    item = _service.get_highlight(book_name, chapter_id, section_id=section_id)
    if not item:
        return {"success": False, "message": "所选范围的重点尚未生成"}
    return {"success": True, "data": item}


@router.delete("/{book_name}/chapter-highlights/{chapter_id}")
def delete_chapter_highlight(book_name: str, chapter_id: str, section_id: str = "all"):
    try:
        result = _service.delete_highlight(book_name, chapter_id, section_id=section_id)
        if not result.get("removed"):
            return {"success": False, "message": "\u672a\u627e\u5230\u53ef\u5220\u9664\u7684\u91cd\u70b9\u4ea7\u7269", "data": result}
        return {"success": True, "message": "\u5df2\u5220\u9664\u65e7\u91cd\u70b9\u4ea7\u7269", "data": result}
    except Exception as exc:
        return {"success": False, "message": f"\u5220\u9664\u91cd\u70b9\u5931\u8d25\uff1a{exc}"}


@router.post("/{book_name}/chapter-highlights/{chapter_id}/jobs")
def create_chapter_highlight_job(book_name: str, chapter_id: str, section_id: str = "all", force: bool = False):
    try:
        # Keep job creation quick. Full OCR/package validation can scan large
        # MinerU outputs, so it runs inside the background job.
        scope = _service.validate_scope(book_name, chapter_id, section_id=section_id)
    except ChapterHighlightError as exc:
        return {"success": False, "message": str(exc)}
    except Exception as exc:
        return {"success": False, "message": f"无法确认章节范围：{exc}"}
    job = _jobs.create_job(book_name, scope["chapter_id"], section_id=scope["section_id"], force=force)
    return {"success": True, "message": "章节重点生成任务已启动", "job_id": job["id"], "data": job}


@router.get("/chapter-highlight-jobs/{job_id}")
def get_chapter_highlight_job(job_id: str):
    job = _jobs.read_job(job_id)
    if not job:
        return {"success": False, "message": "未找到章节重点生成任务"}
    return {"success": True, "data": job}


@router.get("/{book_name}/chapter-highlights/assets/{asset_path:path}")
def get_chapter_highlight_asset(book_name: str, asset_path: str):
    output_dir = _service._find_mineru_output_dir(book_name)
    if not output_dir:
        raise HTTPException(status_code=404, detail="MinerU output not found")
    root = output_dir.resolve()
    target = (output_dir / asset_path).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=403, detail="asset path forbidden")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="asset not found")
    return FileResponse(str(target))
