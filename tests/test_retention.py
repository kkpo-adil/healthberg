from datetime import datetime,timedelta,timezone
from app import db
from .test_api import preview,confirm_body

def test_retention_parameter_default():
    assert db.RETENTION_DAYS==730

def test_purge_only_expired_imports(client,login_as,post):
    login_as('patient')
    p=preview(client).json()
    assert post('/api/documents/confirm',confirm_body(p)).status_code==200
    expiry=(datetime.now(timezone.utc)+timedelta(days=731)).isoformat()
    purged=db.purge_expired(expiry)
    assert purged['observations_removed']==2
    assert purged['receipts_removed']==1
    assert len(client.get('/api/patients/pat_marie/observations').json())>0
