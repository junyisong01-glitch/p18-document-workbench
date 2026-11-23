"""Small, read-only lifecycle summary; never return audit notes or grant targets."""
import json


def document_lifecycle(doc, workflow, events):
    submitted = None
    reviewed = None
    published = None
    for event in events:
        action = event['action']
        body = json.loads(event['body'])
        entry = {'actor': event['actor'], 'at': event['at']}
        if action in {'submitted', 'minor_correction_declared'} and submitted is None:
            submitted = entry
        elif action in {'return', 'withdraw', 'resubmit'}:
            reviewed = None
        elif action == 'approve':
            reviewed = entry
        elif action in {'publish', 'publish_version'}:
            published = {**entry, 'automatic': bool(body.get('automatic'))}
            if body.get('reviewed') and reviewed is None:
                reviewed = {'actor': body.get('approved_by') or event['actor'], 'at': event['at']}
        elif action == 'minor_correction_activated':
            published = {**entry, 'automatic': True}
    if submitted is None and not workflow.get('legacy'):
        submitted = {'actor': workflow.get('owner'), 'at': doc.get('created_at')}
    return {'submitted': submitted, 'reviewed': reviewed, 'published': published}
