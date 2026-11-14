export const CLASSIFICATIONS = ['公开', '内部', '机密'] as const;
export type Classification = (typeof CLASSIFICATIONS)[number] | '未分类';

export interface DocTypeRecord {
  id: string;
  name: string;
}

export const DOC_STATUSES = ['可检索', '已停用检索', '处理中', '处理失败', '待复核', '待建索引', '待分类'] as const;
export type DocStatus = (typeof DOC_STATUSES)[number];

export const DEPARTMENTS = ['行政安全部', '生产制造部', '人力资源部', '财务部', '研发部'] as const;
export const ARCHIVE_FOLDER = '已废止版本';

export const IDENTITIES = [
  {key:'fin_staff',label:'财务部普通员工'}, {key:'fin_manager',label:'财务经理'}, {key:'hr_staff',label:'人力资源部普通员工'}, {key:'payroll',label:'薪酬专员'}, {key:'admin_staff',label:'行政安全部员工'},
  { key: 'gm', label: '总经理' },
  { key: 'rd', label: '研发部员工' },
  { key: 'mfg', label: '生产制造部员工' },
  { key: 'fin', label: '财务总监' },
  { key: 'hr', label: '人力资源总监' },
] as const;
export type IdentityKey = (typeof IDENTITIES)[number]['key'];

export interface DocumentRecord {
  id: string;
  name: string;
  code: string;
  format: string;
  department: string;
  docType: string;
  classification: Classification;
  version: string;
  effectiveDate: string;
  status: DocStatus;
  qcIssues: string[];
  viewers: string[];
  preview: string;
  createdAt: string;
  folder: string;
  metadataVersion: number;
  reviewSearchable?: boolean;
  reviewCompleted?: boolean;
  lifecycle: string;
}

export interface FolderRecord {
  id: string;
  name: string;
  defaultClassification: Classification;
  viewers: string[];
}

export type LibraryScope =
  | { kind: 'all' }
  | { kind: 'folder'; name: string }
  | { kind: 'docType'; value: string }
  | { kind: 'classification'; value: Classification };
