"""Compatibility import for the former duplicate Superadmin scope route.

Phase 0 consolidates ``PUT /admin-saas/user-sections`` in
``routes.admin_saas``.  Keeping this module importable avoids breaking tooling
or older imports, but it intentionally registers no HTTP route.
"""

from fastapi import APIRouter

from routes.admin_saas import _validate_user_section_scope


router = APIRouter()

__all__ = ["router", "_validate_user_section_scope"]
