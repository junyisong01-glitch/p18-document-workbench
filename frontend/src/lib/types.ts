// 均易 JUNYI · 原生接口视图类型
// 注意：本文件为前端演示数据结构，字段映射 P18 真实接口。
// 若某字段现有 API 不提供，界面直接隐藏，不编造占位事实。

export type RoleId = 'rd' | 'qa' | 'ops' | 'mfg' | 'finance' | 'hr' | 'adm' | 'management' | 'guest'

export interface Role {
  id: RoleId
  name: string // 研发 / 测试 / 运维 / 生产
  dept: string // 所属部门（服务端岗位信息）
}

export interface Account {
  username: string
  password: string
  name: string
  role: RoleId
  /** 现有文档管理员：仅授予可写知识库中的上传/复核/索引管理入口，阅读范围仍按岗位 */
  admin?: boolean
}

export type KbId = 'qichen' | 'demo' | 'business'

export interface KnowledgeBase {
  id: KbId
  name: string
  shortName: string
  modeLabel: string // 知识库模式说明
  readonly: boolean // 是否只读
  externalAiAllowed: boolean // 是否允许外部 AI 问答
  managed: boolean // 是否具备上传/复核/索引管理能力（管理员）
  stats: {
    totalDocs: number
    docx: number
    xlsx: number
    indexedChunks: number
    archived: number
    reviewNotes: number
  } | null
}

export type DocFormat = 'doc' | 'docx' | 'xlsx' | 'xls' | 'pdf' | 'txt' | 'md' | 'csv' | 'jpg' | 'jpeg' | 'png'
export type DocStatus = 'active' | 'archived' // archived = 已废止归档
export type Confidentiality = '公开' | '内部' | '机密' // 现有密级分类

export interface Snippet {
  id: string
  section: string // 片段所在结构（章节/表），真实切分结构信息
  text: string
}

export interface TablePreview {
  columns: string[]
  rows: string[][]
}

export interface Doc {
  reviewRequired?: boolean
  processingStatus?: string
  kbId?: KbId
  id: string
  code: string // 文档编号
  title: string // 文档主题（不含编号与版本）
  fileName: string // 完整文件名
  version: string
  format: DocFormat
  category: string // 所属目录分类
  subcategory?: string // 研发部内部分类（二级目录）
  dept: string // 所属部门
  confidentiality: Confidentiality // 密级
  status: DocStatus
  indexStatus: 'indexed' | 'review-pending' // 索引状态
  pipeline: {
    parsed: boolean
    chunked: boolean
    reviewed: boolean
    indexed: boolean
  }
  snippets: Snippet[]
  tablePreview?: TablePreview // Excel 结构化内容预览（演示）
}

export const ROLES: Record<RoleId, Role> = {
  finance:{id:'finance',name:'财务',dept:'财务部'},
  hr:{id:'hr',name:'人事',dept:'人力资源部'},
  adm:{id:'adm',name:'行政安全',dept:'行政安全部'},
  management:{id:'management',name:'管理层负责人',dept:'管理层'},
  guest:{id:'guest',name:'访客',dept:'无部门读权'},
  rd: { id: 'rd', name: '研发', dept: '研发部' },
  qa: { id: 'qa', name: '测试', dept: '研发部' },
  ops: { id: 'ops', name: '运维', dept: '研发部' },
  mfg: { id: 'mfg', name: '生产', dept: '生产制造部' },
}

export const KNOWLEDGE_BASES: Record<KbId, KnowledgeBase> = {
  business:{id:'business',name:'启辰智造知识库',shortName:'启辰智造',modeLabel:'提交 · 审核 · 发布 · 权限内检索（禁止外发）',readonly:false,externalAiAllowed:false,managed:false,stats:null},
  qichen: {
    id: 'qichen',
    name: '历史启辰验收库',
    shortName: '启辰智造',
    modeLabel: '只读检索 · 禁止外部 AI 问答',
    readonly: true,
    externalAiAllowed: false,
    managed: false,
    stats: null,
  },
  demo: {
    id: 'demo',
    name: '演示资料库',
    shortName: '演示资料',
    modeLabel: '检索 · 人工确认证据后的条件性问答',
    readonly: false,
    externalAiAllowed: true,
    managed: true,
    stats: null,
  },
}

export const QICHEN_CATEGORIES = [
  '01_公司公共制度',
  '02_行政安全部',
  '03_生产制造部',
  '04_人力资源部',
  '05_财务部',
  '06_研发部',
  '99_已废止版本',
] as const

export const DEMO_CATEGORIES = ['平台资料'] as const
