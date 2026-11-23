import json
from app.business_document_details import document_lifecycle


def event(action, at, actor='head', **body):
    return dict(action=action, at=at, actor=actor, body=json.dumps(body))


def test_summary_uses_actual_events_and_does_not_leak_audit_notes():
    result=document_lifecycle({}, {}, [event('submitted',1,'rd'),event('approve',2,note='private reason'),event('publish',3,reviewed=True,approved_by='head'),event('share',4,username='private grantee')])
    assert result=={'submitted':{'actor':'rd','at':1},'reviewed':{'actor':'head','at':2},'published':{'actor':'head','at':3,'automatic':False}}


def test_combined_approval_auto_publication_and_correction_are_distinct():
    reviewed=document_lifecycle({}, {}, [event('publish_version',3,reviewed=True,approved_by='boss')])
    assert reviewed['reviewed']=={'actor':'boss','at':3}
    auto=document_lifecycle({}, {}, [event('publish',3,'rd',automatic=True)])
    assert auto['reviewed'] is None and auto['published']['automatic']
    correction=document_lifecycle({}, {'approved_by':'old reviewer'}, [event('minor_correction_declared',4,'rd'),event('minor_correction_activated',5,'rd')])
    assert correction['submitted']=={'actor':'rd','at':4}
    assert correction['reviewed'] is None and correction['published']['automatic']


def test_missing_legacy_records_are_not_invented_and_return_resets_review():
    assert document_lifecycle({'created_at':'import time'}, {'legacy':True,'owner':'legacy_import','published_by':'boss'}, [])=={'submitted':None,'reviewed':None,'published':None}
    result=document_lifecycle({'created_at':'2026-11-23T01:00:00Z'}, {'owner':'rd'}, [event('approve',1),event('return',2)])
    assert result['submitted']['at']=='2026-11-23T01:00:00Z'
    assert result['reviewed'] is None
