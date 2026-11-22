from datetime import datetime,timedelta,timezone
from app import db

def test_retention_parameter_default():
    assert db.RETENTION_DAYS==730

def test_purge_only_expired_imports(client):
    from .test_api import preview, confirm_body
    p=preview(client).json();r=client.post('/api/documents/confirm',json=confirm_body(p));assert r.status_code==200
    expiry=(datetime.now(timezone.utc)+timedelta(days=731)).isoformat()
    purged=db.purge_expired(expiry)
    assert purged['observations_removed']==2
    assert purged['receipts_removed']==1
    assert len(client.get('/api/patients/pat_marie/observations').json())>0
