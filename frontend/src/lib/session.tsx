// 原生会话、数据源与检索适配；权限和排序由服务端判定。

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { api, ApiError, type LibraryRecord, type Me } from './api'
import {
  KNOWLEDGE_BASES,
  ROLES,
  type Confidentiality,
  type Doc,
  type DocFormat,
  type KbId,
  type Role,
  type RoleId,
  type SearchResult,
} from './types'

export interface SessionUser {
  username: string
  name: string
  role: Role
  /** 现有文档管理员（阅读范围仍按岗位，仅在可写库开放管理入口） */
  admin: boolean
}

interface SessionState {
  availableKbs: KbId[]
  user: SessionUser | null
  kbId: KbId
  ready: boolean
  login: (username: string, password: string) => Promise<{ ok: boolean; error?: string }>
  logout: () => void
  setKb: (kb: KbId) => void
  /** 当前岗位在当前知识库中可见的文档（含归档） */
  visibleDocs: Doc[]
  /** 现行可检索文档（排除已废止） */
  searchableDocs: Doc[]
  archivedDocs: Doc[]
  kbStats: Record<KbId, { totalDocs: number; docx: number; xlsx: number; indexedDocs: number }>
  refresh: () => Promise<void>
  /** 兼容旧组件；不在客户端伪造复核结果。 */
  localReviewed: string[]
  markReviewed: (docId: string) => void
}

const SessionContext = createContext<SessionState | null>(null)

const SESSION_KEY = 'junyi.session'

const ROLE_RULES: Array<[RegExp, RoleId]> = [
  [/测试/, 'qa'],
  [/运维/, 'ops'],
  [/生产/, 'mfg'],
  [/研发|总经理|管理/, 'rd'],
]

function roleOf(identity: string): Role {
  for (const [pattern, id] of ROLE_RULES) if (pattern.test(identity)) return ROLES[id]
  return ROLES.rd
}

/** 服务端库记录 → 界面文档模型。字段缺失就留空，界面自行隐藏。 */
function toDoc(record: LibraryRecord): Doc {
  const extension = (record.format || '').toLowerCase()
  const format: DocFormat = extension === 'xlsx' ? 'xlsx' : extension === 'pdf' ? 'pdf' : 'docx'
  const indexed = record.status === '可检索' || !!record.reviewSearchable
  return {
    id: record.id,
    processingStatus:record.status,
    reviewRequired:record.status==='待复核'||record.reviewSearchable||!!record.qcIssues.length,
    code: record.code || '',
    title: record.name.replace(/\.[^.]+$/, ''),
    fileName: record.name,
    version: record.version || '',
    format,
    category: record.folder || '未分类',
    subcategory: record.docType || undefined,
    dept: record.department || '',
    confidentiality: (['公开', '内部', '机密'].includes(record.classification)
      ? record.classification
      : '内部') as Confidentiality,
    status: record.lifecycle === '已废止' ? 'archived' : 'active',
    indexStatus: indexed ? 'indexed' : 'review-pending',
    pipeline: { parsed: !['处理中','处理失败'].includes(record.status), chunked: indexed, reviewed: !!record.reviewCompleted, indexed },
    snippets: [],
  }
}

export const docInKb = (doc: Doc, kb: KbId) => doc.kbId === kb

const inKb = docInKb

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null)
  const [docs, setDocs] = useState<Doc[]>([])
  const [availableKbs,setAvailableKbs]=useState<KbId[]>(['demo'])
  const [kbId, setKbId] = useState<KbId>('demo')
  const [localReviewed, setLocalReviewed] = useState<string[]>([])
  const [ready, setReady] = useState(false)

  const markReviewed = useCallback((_docId: string) => { setLocalReviewed([]) }, [])

  const loadSession = useCallback(async (): Promise<boolean> => {
    try {
      const me = await api.get<Me>('/api/library/me')
      setUser({
        username: me.identity,
        name: me.identity,
        role: roleOf(me.identity),
        admin: !!me.manager,
      })
      const selection = await api.get<{selected:string,datasets:Array<{id:string}>}>('/api/library/datasets')
      const active:KbId=selection.selected==='qichen30'?'qichen':'demo'
      setKbId(active)
      setAvailableKbs(selection.datasets.map(d=>d.id==='qichen30'?'qichen':'demo'))
      const records = await api.get<LibraryRecord[]>('/api/library/documents')
      setDocs(records.map(r=>({...toDoc(r),kbId:active})))
      return true
    } catch {
      setUser(null)
      setDocs([])
      return false
    } finally {
      setReady(true)
    }
  }, [])

  useEffect(() => {
    void loadSession()
  }, [loadSession])

  const login = useCallback(
    async (username: string, password: string) => {
      try {
        await api.post('/api/library/login', { username: username.trim(), password })
      } catch (error) {
        const status = error instanceof ApiError ? error.status : 0
        return {
          ok: false,
          error: status === 401 ? '账号或密码无效，连续失败后请稍后重试。' : '登录失败，请稍后重试。',
        }
      }
      const ok = await loadSession()
      return ok ? { ok: true } : { ok: false, error: '登录成功但读取身份失败，请刷新重试。' }
    },
    [loadSession],
  )

  const logout = useCallback(() => {
    void api.post('/api/library/logout').catch(() => undefined)
    setUser(null)
    setDocs([])
    setKbId('qichen')
    try {
      sessionStorage.removeItem(SESSION_KEY)
    } catch {
      /* 忽略存储异常 */
    }
  }, [])

  const setKb = useCallback((kb: KbId) => {
    setReady(false)
    void api.post('/api/library/datasets',{dataset:kb==='qichen'?'qichen30':'demo'})
      .then(()=>location.assign('/documents'))
      .catch(()=>{setReady(true);window.alert('知识库切换失败，请重试')})
  }, [])

  const visibleDocs = useMemo(() => {
    if (!user) return []
    return docs.filter((doc) => inKb(doc, kbId))
  }, [docs, kbId, user])

  const searchableDocs = useMemo(
    () => visibleDocs.filter((doc) => doc.status === 'active' && doc.indexStatus==='indexed'),
    [visibleDocs],
  )

  const archivedDocs = useMemo(
    () => visibleDocs.filter((doc) => doc.status === 'archived'),
    [visibleDocs],
  )

  const kbStats = useMemo(() => {
    const build = (kb: KbId) => {
      if(kb!==kbId)return {totalDocs:-1,docx:-1,xlsx:-1,indexedDocs:-1}
      const list = docs.filter((doc) => inKb(doc, kb))
      return {
        totalDocs: list.length,
        docx: list.filter((doc) => doc.format === 'docx').length,
        xlsx: list.filter((doc) => doc.format === 'xlsx').length,
        indexedDocs: list.filter((doc) => doc.indexStatus === 'indexed').length,
      }
    }
    return { qichen: build('qichen'), demo: build('demo') }
  }, [docs,kbId])

  const refresh = useCallback(async () => {
    await loadSession()
  }, [loadSession])

  const value = useMemo(
    () => ({
      user,
      availableKbs,
      refresh,
      kbId,
      ready,
      login,
      logout,
      setKb,
      visibleDocs,
      searchableDocs,
      archivedDocs,
      kbStats,
      localReviewed,
      markReviewed,
    }),
    [user, availableKbs, kbId, ready, login, logout, setKb, visibleDocs, searchableDocs, archivedDocs, kbStats, refresh, localReviewed, markReviewed],
  )

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession(): SessionState {
  const ctx = useContext(SessionContext)
  if (!ctx) throw new Error('useSession must be used within SessionProvider')
  return ctx
}

export function useKnowledgeBase() {
  const { kbId } = useSession()
  return KNOWLEDGE_BASES[kbId]
}

export interface ApiHit {
  rank:number
  document_id: string
  document_name: string
  chunk_id: string
  text: string
  section?: string
  score: number
  revision: number
  index_token: string
}

export interface ApiSearchResponse {
  status: string
  results: ApiHit[]
  message?: string
  retrieval_mode?: string
}

export async function searchLibrary(query: string): Promise<{ body: ApiSearchResponse; elapsedMs: number }> {
  const started = performance.now()
  const body = await api.post<ApiSearchResponse>('/api/search', { query })
  return { body, elapsedMs: Math.round(performance.now() - started) }
}

export interface RagCandidate {
  candidate_id: string
  selectable: boolean
  default_reason?: string
  evidence: {
    document_id: string
    document_name: string
    chunk_id: string
    text: string
    section?: string
  }
}

export interface RagDraft {
  status: string
  session_id?: string
  draft_id?: string
  selection_version?: number
  candidates?: RagCandidate[]
  budget?: { groups: number; group_limit: number; message_chars: number; context_limit: number }
  message?: string
}

export const ragDraft = (question: string) => api.post<RagDraft>('/api/rag/drafts', { question })

export const ragSelection = (draftId: string, selectionVersion: number, candidateIds: string[]) =>
  api.post<{ ticket: string; budget?: RagDraft['budget']; expires_in?: number }>('/api/rag/selection', {
    draft_id: draftId,
    selection_version: selectionVersion,
    candidate_ids: candidateIds,
  })

export const ragAnswer = (ticket: string) =>
  api.post<{
    answer_status: string
    answer: string
    citations: Array<{ document_name: string; section?: string }>
  }>('/api/rag/answer', { ticket, consent: true })

export interface SearchOutput {
  results: SearchResult[]
  verifiedCase: boolean
  elapsedMs: number
}


export function downloadDemoFile(doc: Doc) {
  const a=document.createElement('a');a.href='/api/documents/'+encodeURIComponent(doc.id)+'/file/original';a.download=doc.fileName;a.click()
}
