"""User-facing backup and restart-safe restore endpoints."""
from __future__ import annotations

from fastapi import APIRouter

from backend.data_backup import create_backup, list_backups, restore_status, schedule_restore


router = APIRouter(prefix="/system/backups", tags=["backups"])


@router.get("")
def backups_list():
    try:
        return {"success": True, "data": {"items": list_backups(), **restore_status()}}
    except Exception as exc:
        return {"success": False, "message": f"读取备份失败：{exc}"}


@router.post("")
def backups_create(payload: dict | None = None):
    payload = payload or {}
    try:
        item = create_backup(include_derived=bool(payload.get("include_derived")), reason="manual")
        return {"success": True, "message": "备份已创建并通过压缩包校验", "data": item}
    except Exception as exc:
        return {"success": False, "message": f"备份失败：{exc}"}


@router.post("/{backup_name}/restore")
def backups_restore(backup_name: str):
    try:
        result = schedule_restore(backup_name)
        return {
            "success": True,
            "message": "合并恢复已登记，并已创建恢复前安全备份。重启后将覆盖备份内的数据，保留备份中未包含的其他核心数据。",
            "data": result,
        }
    except Exception as exc:
        return {"success": False, "message": f"无法安排恢复：{exc}"}
