import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class LogoutResult:
    ok: bool
    revoked: bool = False
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "success": self.ok,
            "revoked": self.revoked,
            "reason": self.reason,
        }


def _is_session_not_found(exc: Exception) -> bool:
    text = str(exc).lower()
    return "session_not_found" in text or "session not found" in text


def revoke_supabase_session(access_token: str) -> LogoutResult:
    """
    Revoke the Supabase refresh-token family for the JWT that came from the
    browser. Calling auth.sign_out() on the shared server client is not enough:
    that client has no per-request browser session attached.
    """
    token = (access_token or "").strip()
    if not token:
        return LogoutResult(ok=True, revoked=False, reason="missing_token")

    try:
        from supabase_config import get_supabase_admin

        get_supabase_admin().auth.admin.sign_out(token, "global")
        return LogoutResult(ok=True, revoked=True)
    except Exception as exc:
        if _is_session_not_found(exc):
            logger.info("Supabase logout idempotent: session not found.")
            return LogoutResult(ok=True, revoked=False, reason="session_not_found")
        logger.warning("Supabase logout failed: %s", exc)
        return LogoutResult(ok=False, revoked=False, reason=str(exc) or "logout_failed")
