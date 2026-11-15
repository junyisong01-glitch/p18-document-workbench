from pathlib import Path
from app import main
from test_workbench import client, upload, wait


def test_frontend_assets_and_capability_metadata(client):
    html=client.get('/').text
    assert 'id="root"' in html and '/assets/' in html
    assert client.get('/search').text==html
    asset=client.get('/static/search.js')
    assert asset.status_code==200 and 'hitIsCurrent' in asset.text
    info=client.get('/api/config').json()
    assert info['workbench_version']=='semantic-ui-v1'
    assert Path(info['data_directory'])==main.DATA.resolve()
    setup=client.get('/api/semantic').json()['setup']
    assert isinstance(setup['ready'],bool) and setup['message']


def test_document_list_exposes_honest_index_state(client):
    doc=wait(client,upload(client)['id'])
    row=next(d for d in client.get('/api/documents').json() if d['id']==doc['id'])
    assert row['index']['searchable'] is False
    assert row['index']['status']=='disabled'
    assert 'result' not in row
