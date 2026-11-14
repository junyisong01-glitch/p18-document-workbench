"""Readonly response presentation; never changes review/admission/index decisions."""
from types import SimpleNamespace
import pytest
from app import library_api
@pytest.mark.parametrize('state,revision,decision,expected',[('ready',2,2,True),('ready',2,1,False),('review',2,2,False),('held',2,2,True),('ready',2,None,False)])
def test_review_display_requires_current_record(monkeypatch,state,revision,decision,expected):
 store=SimpleNamespace(index_status=lambda _: {'searchable':True},STATES={'parsing'})
 monkeypatch.setattr(library_api,'metadata',lambda *_:None)
 doc={'id':'fictional','name':'虚构','created_at':'now','state':state,'revision':revision,'review_decision':{'revision':decision},'result':{'issues':[{'message':'历史提示'}]}}
 r=library_api.library_record(store,doc)
 assert r['reviewCompleted'] is expected
 assert r['qcIssues']==['历史提示']
 assert doc['state']==state and doc['revision']==revision
