"""Question-only external reference for the single-library workbench."""
from contextlib import nullcontext
import json
import secrets
import time
from urllib.request import Request, ProxyHandler, build_opener

from fastapi import HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app import library_api, library_store
from app.datasets import LocalRag
from app.egress_gate import gate
from app.llm import NoRedirect, RoutedClient
from app import qa_facts
from app.rag import RagError

ENDPOINT = 'https://api.deepseek.com/chat/completions'
MODEL = 'deepseek-flash'
REASONS = {
    'disabled': '系统已关闭外部模型',
    'selection_required': '请重新确认本次登录使用外部模型',
    'credentials_missing': 'DeepSeek 密钥尚未配置',
    'no_evidence': '没有可核对的命中资料',
    'not_externally_public': '本轮命中资料未全部标记为对外公开',
    'stale': '本轮命中资料或权限已变化',
}


def settings(central):
    with central.connect() as conn:
        row = conn.execute('SELECT enabled, revision, public_ids FROM qa_external_settings WHERE id=1').fetchone()
    return dict(enabled=bool(row[0]), revision=row[1], grants=json.loads(row[2]))


def classified_public(store, identifier):
    workflow = store.business_read(identifier)
    row = library_api.metadata(store, identifier) if workflow else None
    return bool(row and row[1].classification == '公开' and row[1].lifecycle == '现行有效'
                and workflow and workflow['status'] == 'published' and workflow.get('company_public')
                and not any(workflow.get(key) for key in ('archived', 'deleted', 'restricted')))


def fingerprint(doc):
    return [doc['revision'], doc['sha256']]


def audit(central, event, question, ids, reason=None, *, sent=None):
    user = library_api.principal.get()
    with central.connect() as conn:
        conn.execute('INSERT INTO qa_external_audit(at,username,event,question,document_ids,blocked,reason,sent) VALUES (?,?,?,?,?,?,?,?)',
                     (time.time(), user['username'], event, question, json.dumps(ids), bool(reason), reason, sent))


class SettingsBody(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    enabled: bool
    revision: int = Field(ge=0)
    public_ids: list[str] = Field(max_length=1000)


def install_admin(store, central):
    with central.connect() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS qa_external_settings(id INTEGER PRIMARY KEY CHECK(id=1),enabled INTEGER,revision INTEGER,public_ids TEXT)')
        conn.execute("INSERT OR IGNORE INTO qa_external_settings VALUES(1,0,0,'{}')")
        conn.execute('CREATE TABLE IF NOT EXISTS qa_external_audit(id INTEGER PRIMARY KEY,at REAL,username TEXT,event TEXT,question TEXT,document_ids TEXT,blocked INTEGER,reason TEXT,sent TEXT)')

    def administrator():
        user = library_api.principal.get()
        with central.connect() as conn:
            current = library_store.session_by_digest(conn, user['session_digest']) if user else None
        if not current or current['role'] != 'boss':
            raise HTTPException(403, '仅系统管理员可管理外部模型与查看审计')

    def snapshot():
        cfg = settings(central)
        return dict(enabled=cfg['enabled'], revision=cfg['revision'],
                    public_ids=[identifier for identifier, original in cfg['grants'].items()
                                if classified_public(store, identifier) and fingerprint(store.get(identifier)) == original])

    @store.app.get('/api/rag/external-settings')
    def read_settings():
        administrator()
        with store.LOCK:
            return dict(snapshot(), documents=[
                dict(id=doc['id'], name=doc['name']) for doc in store.all_docs()
                if classified_public(store, doc['id'])
            ])

    @store.app.put('/api/rag/external-settings')
    def change_settings(body: SettingsBody):
        administrator()
        with gate().changing(), store.LOCK:
            current = settings(central)
            if current['revision'] != body.revision:
                raise HTTPException(409, '设置已变化，请重新读取')
            ids = sorted(set(body.public_ids))
            # Disabling must remain possible even if a previously marked document has changed.
            # Existing entries keep their original fingerprint. Saving the switch
            # cannot reauthorize bytes that changed after an earlier designation.
            retained = {key: value for key, value in current['grants'].items() if key in ids}
            newly_marked = set(ids) - set(retained)
            if any(not classified_public(store, identifier) for identifier in newly_marked):
                raise HTTPException(422, '只有已发布、非受限的公开资料可标记为对外公开')
            retained.update({identifier: fingerprint(store.get(identifier)) for identifier in newly_marked})
            with central.connect() as conn:
                conn.execute('UPDATE qa_external_settings SET enabled=?, revision=revision+1, public_ids=? WHERE id=1',
                             (body.enabled, json.dumps(retained)))
            return snapshot()

    @store.app.get('/api/rag/external-audit')
    def list_audit(username: str = Query('', max_length=100), start: float | None = None, end: float | None = None):
        administrator()
        with central.connect() as conn:
            rows = conn.execute(
                'SELECT at,username,event,question,document_ids,blocked,reason,sent FROM qa_external_audit '
                'WHERE (? = \'\' OR username=?) AND (? IS NULL OR at>=?) AND (? IS NULL OR at<=?) ORDER BY id DESC LIMIT 200',
                (username, username, start, start, end, end))
            return [dict(row, document_ids=json.loads(row['document_ids']), blocked=bool(row['blocked'])) for row in rows]


def question_transport(question, credential):
    # No system prompt, excerpts, metadata, history or other user-controlled URL.
    body = dict(model=MODEL, messages=[dict(role='user', content=question)], stream=False,
                max_tokens=1500, thinking={'type': 'disabled'})
    request = Request(ENDPOINT, data=json.dumps(body, ensure_ascii=False).encode(), method='POST',
                      headers={'Content-Type': 'application/json', 'Authorization': 'Bearer '+credential})
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=60) as response:
            raw = response.read(1_000_001)
        if len(raw) > 1_000_000:
            raise ValueError()
        choice = json.loads(raw)['choices'][0]
        answer = choice['message']['content']
        if choice['finish_reason'] != 'stop' or not isinstance(answer, str) or not 1 <= len(answer) <= 12_000:
            raise ValueError()
        return answer
    except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
        raise RagError('external_response', 'DeepSeek 未返回有效的完整回答，未自动重试。') from exc


class QuestionOnlyRag(LocalRag):
    question_only_external = True

    def __init__(self, store, central):
        super().__init__(store, lambda **_: None)
        self.central = central
        self.client = RoutedClient(session=True, source_library='qichen')
        self.client.selected_provider = 'ollama'
        self.external_revision = None

    def status(self):
        cfg = settings(self.central)
        return dict(super().status(), provider_switch_supported=True, question_only_external=True,
                    external_model_enabled=cfg['enabled'], external_selected=self.external_revision == cfg['revision'])

    def tune_query(self, question, query, session, turn_id):
        from app.qa_scope import GATEWAY, PLATFORM, parameter, products, resolve
        visible = set()
        if parameter(question) == 'quota' and not products(question):
            with self.store.LOCK:
                for doc in self.store.all_docs():
                    name = doc.get('name', '')
                    for product in (PLATFORM, GATEWAY):
                        if product.source_code in name and self.can_read(doc):
                            visible.add(product)
        rewritten, topic, clarification = resolve(question, session.get('qa_product') if turn_id is None else None, visible)
        if turn_id is None:
            session['qa_product'] = topic
        if rewritten != question or clarification:
            return rewritten, clarification
        return query, ''

    def draft_search(self, service, query, question):
        plan = qa_facts.parts(question)
        anchor = qa_facts.ticket_lookup(question) if not plan else None
        if anchor:
            return super().draft_search(service, query, question,
                                        chunk_filter=lambda chunk: qa_facts.contains_anchor(chunk['text'], anchor))
        authorized, local = super().draft_search(service, query, question)
        if not plan:
            return authorized, local
        extra = []
        for part in plan:
            result = service.search(part.query, top_k=20, document_filter=self.can_read)
            extra.extend(result['results'])
        return dict(authorized, results=[*authorized['results'], *extra]), local

    def document_anchor_check(self):
        service = self.store.require_semantic()
        snapshots = {}

        def contains(source, anchor):
            identifier = source['document_id']
            if identifier not in snapshots:
                snapshots[identifier] = service.snapshot(identifier)
            snap = snapshots[identifier]
            return bool(snap and snap['token'] == source['index_token'] and any(
                qa_facts.contains_anchor(chunk['text'], anchor) for chunk in snap['chunks']))

        return contains

    def prioritize_candidates(self, question, candidates):
        plan = qa_facts.parts(question)
        if not plan:
            return candidates
        contains = self.document_anchor_check()
        per_part = [[cid for cid, candidate in candidates.items()
                     if candidate['selectable'] and next(qa_facts.matches(part, candidate['evidence'], contains), None)]
                    for part in plan]
        preferred = [group[0] for group in per_part if group]
        preferred.extend(cid for group in per_part for cid in group)
        return {cid: candidates[cid] for cid in dict.fromkeys([*preferred, *candidates])}

    def local_evidence_result(self, ticket):
        plan = qa_facts.parts(ticket['question'])
        if plan and ticket['config'].get('provider') == 'ollama':
            return qa_facts.checked_answer(plan, ticket['evidence'], self.document_anchor_check())
        return None

    def select_model(self, provider, confirm_external):
        with self.lock:
            if any(session.get('busy') for session in self.sessions.values()):
                raise RagError('session_busy', '请等待当前回答结束。')
            cfg = settings(self.central)
            if provider == 'deepseek' and (confirm_external is not True or not cfg['enabled']):
                raise RagError('external_unavailable', '外部模型须已开启，且必须明确确认。')
            self.external_revision = cfg['revision'] if provider == 'deepseek' else None
            self.tickets.clear()
            self.drafts.clear()
            self.sessions.clear()
            return dict(provider=provider, scope='login_session', notice='请重新检索并核对本轮请求。')

    def _blocked(self, cfg, evidence):
        if not cfg['enabled']:
            return 'disabled'
        if self.external_revision != cfg['revision']:
            return 'selection_required'
        if not self.client.credential():
            return 'credentials_missing'
        if not evidence:
            return 'no_evidence'
        if not self.valid(evidence):
            return 'stale'
        if any(not classified_public(self.store, source['document_id'])
               or cfg['grants'].get(source['document_id']) != fingerprint(self.store.get(source['document_id']))
               for source in evidence):
            return 'not_externally_public'
        return None

    def _selection(self, draft_id, selection_version, candidate_ids, *, trace):
        with self.lock:
            result = super()._selection(draft_id, selection_version, candidate_ids, trace=trace)
            if qa_facts.parts(result['question']):
                result['configured'] = True
            if self.external_revision is None:
                return result
            # Consider every hit and every deduplicated member, even when unchecked.
            draft = self.drafts[draft_id]
            evidence = self.provenance([candidate['evidence'] for candidate in draft['candidates'].values()])
            ids = sorted({source['document_id'] for source in evidence})
            with self.store.LOCK:
                cfg = settings(self.central)
                reason = self._blocked(cfg, evidence)
            question = draft['question']
            if reason:
                audit(self.central, 'blocked', question, ids, reason)
                return dict(result, notice=f"{REASONS[reason]}，本轮使用本地 Ollama。")
            ticket = self.tickets[result['ticket']]
            ticket['external'] = dict(revision=cfg['revision'], evidence=evidence, ids=ids)
            messages = [dict(role='user', content=question)]
            return dict(result, provider='DeepSeek · 外部参考', destination='https://api.deepseek.com',
                        request_endpoint=ENDPOINT, model=MODEL, configured=True, messages=messages,
                        budget=dict(result['budget'], message_chars=len(json.dumps(messages, ensure_ascii=False)),
                                    message_bytes=len(json.dumps(messages, ensure_ascii=False).encode())),
                        notice='DeepSeek 只接收用户问题。命中资料仅用于外发资格检查。')

    def _answer(self, ticket_id, consent, context):
        with self.lock:
            self.prune()
            ticket = self.tickets.get(ticket_id)
            if ticket and 'external' in ticket:
                if consent is not True:
                    audit(self.central, 'blocked', ticket['question'], ticket['external']['ids'], 'confirmation_required')
                    raise RagError('consent_required', '请确认本轮仅发送用户问题。')
                self.tickets.pop(ticket_id)
                session = self.sessions.get(ticket['sid'])
                draft = self.drafts.get(ticket['draft_id'])
                if (not session or session.get('busy') or session['version'] != ticket['version'] or
                    session.get('active_draft') != ticket['draft_id'] or not draft or
                    draft['selection_version'] != ticket['selection_version']):
                    raise RagError('selection_changed', '原确认已失效，请重新检索。')
                session['busy'] = True
            else:
                session = None
        if session is None:
            return super()._answer(ticket_id, consent, context)
        question = ticket['question']
        external = ticket['external']
        ids = external['ids']
        try:
            with gate().sending(), self.store.LOCK:
                cfg = settings(self.central)
                reason = self._blocked(cfg, external['evidence'])
                if not reason and external['revision'] != cfg['revision']:
                    reason = 'selection_required'
                if reason:
                    audit(self.central, 'blocked', question, ids, reason)
                    raise RagError('external_blocked', f"{REASONS[reason]}，原外部确认已失效。请重新核对本地回答。")
                audit(self.central, 'dispatch', question, ids, sent=question)
                transport = getattr(self.central, 'QUESTION_ONLY_TRANSPORT', question_transport)
                network = getattr(self.central, 'QUESTION_ONLY_NETWORK', nullcontext)
                try:
                    with network():
                        answer = transport(question, self.client.credential())
                except Exception:
                    audit(self.central, 'error', question, ids)
                    raise
            with self.lock:
                session['version'] += 1
            return dict(status='answered', answer_status='answered', answer=answer, citations=[], evidence=[],
                        session_id=ticket['sid'], turn_id=secrets.token_urlsafe(24), provider='DeepSeek · 外部参考',
                        notice='外部参考回答，仅基于用户问题。')
        finally:
            with self.lock:
                session['busy'] = False
                session['at'] = time.monotonic()
