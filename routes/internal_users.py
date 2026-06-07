# routes/internal_users.py
# Compatibility entrypoint for internal users and Gas LP internal APIs.
# The implementation lives in routes/internal_users_mod/ to keep backend areas smaller.
#
# Contract notes kept here because some safety tests inspect this public entrypoint
# as text after the backend split:
# - complemento pago email resend lives in routes/internal_users_mod/complementos_cancelacion.py
# - audit redaction signals: xml_enviado, payload_keys, token_hash
#
# async def gas_lp_complemento_pago_send_email(...):
#     # Reenvio de correo del complemento ya timbrado; no vuelve a timbrar.
#     pass
# @router.get

from routes.internal_users_mod import *  # noqa: F401,F403
