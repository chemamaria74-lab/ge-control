from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from routes.admin_saas import (
    _clean_http_error,
    _delete_test_user_local,
    _is_demo_env,
    _require_superadmin,
    _resolve_user_identifier,
)


router = APIRouter()


@router.delete("/admin-saas/users/{target_user_id}/test")
async def delete_saas_test_user_serialized(target_user_id: str, authorization: str = Header(default="")):
    uid, _, _ = _require_superadmin(authorization)
    resolved = _resolve_user_identifier(target_user_id)
    if resolved == uid and not _is_demo_env():
        raise HTTPException(400, "No puedes eliminar tu propio usuario fuera de ambiente demo/staging.")
    try:
        result = _delete_test_user_local(resolved, uid)
    except HTTPException:
        raise
    except Exception as exc:
        raise _clean_http_error(500, exc, "No se pudo eliminar el usuario de prueba.")
    return JSONResponse(jsonable_encoder({"ok": True, "result": result}))
