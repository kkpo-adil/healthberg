import pytest
from scripts.check_ci import successful_run

SHA='a'*40


def run(**changes):
    return dict(id=1,head_sha=SHA,path='.github/workflows/ci.yml',name='Ajour checks',event='push',
                status='completed',conclusion='success',html_url='https://github.com/example',**changes)


def test_exact_revision_and_complete_workflow_required():
    good=run()
    assert successful_run({'workflow_runs':[good]},SHA)==good
    with pytest.raises(ValueError):successful_run({'workflow_runs':[good]},'b'*40)
    for changed in ({'path':'.github/workflows/unrelated.yml'},{'status':'in_progress'},
                    {'conclusion':'failure'},{'event':'pull_request'}):
        with pytest.raises(ValueError):successful_run({'workflow_runs':[{**good,**changed}]},SHA)


def test_newer_failed_run_overrides_older_green_run():
    older=run()
    latest={**older,'id':2,'conclusion':'failure'}
    with pytest.raises(ValueError):successful_run({'workflow_runs':[older,latest]},SHA)
