import asyncio
from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException
from routes import history


def run_correction(closed=False, target='2026-10'):
    db = MagicMock()
    query = db.table.return_value
    query.select.return_value = query
    query.eq.return_value = query
    query.execute.return_value.data = [{'id': 42, 'facility_id': 7, 'uuid': 'test-uuid'}]
    db.rpc.return_value.execute.return_value.data = {'ok': True, 'already_in_target': True}
    with patch.object(history, '_auth', return_value=('admin', 'token')), \
         patch.object(history, '_deny_assistant_reports'), \
         patch.object(history, '_require_perfil', return_value=3), \
         patch.object(history, 'resolve_profile_scope', return_value={'data_user_id': 'owner'}), \
         patch.object(history, 'get_supabase_admin', return_value=db), \
         patch.object(history, 'get_closed_report', return_value={'status': 'closed'} if closed else None):
        result = asyncio.run(history.correct_receipt_period('2026-11', 42,
            history.ReceiptPeriodPayload(target_period=target), 'Bearer token', '3'))
    return result, db


def test_correction_uses_atomic_scoped_rpc():
    result, db = run_correction()
    assert result == {'ok': True, 'already_in_target': True}
    db.rpc.assert_called_once_with('gas_lp_correct_receipt_period', {
        'p_owner': 'owner', 'p_profile': 3, 'p_record': 42,
        'p_source': '2026-11', 'p_target': '2026-10', 'p_actor': 'admin'})
    db.table.return_value.delete.assert_not_called()


@pytest.mark.parametrize('closed,target', [(True, '2026-10'), (False, '2026-11'), (False, '2026-13')])
def test_correction_rejects_closed_or_invalid_period(closed, target):
    with pytest.raises(HTTPException):
        run_correction(closed=closed, target=target)
