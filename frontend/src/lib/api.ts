// 均易 JUNYI · 与 P18 后端通信的最小客户端
// 所有请求同源、带 Cookie；401 统一跳登录页。

export class ApiError extends Error {
  status: number
  code?: string
  constructor(message: string, status: number, code?: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: 'same-origin',
    headers: { 'X-P18-Client': 'workbench', ...(init.headers ?? {}) },
  })
  if (response.status === 401) {
    if (!location.pathname.endsWith('/login')) {
      location.replace('/login')
    }
    throw new ApiError('登录已失效', 401, 'unauthenticated')
  }
  const text = await response.text()
  const body = text ? JSON.parse(text) : null
  if (!response.ok) {
    const detail = body?.detail
    const message =
      typeof detail === 'string' ? detail : detail?.message || '请求未完成，请稍后重试'
    throw new ApiError(message, response.status, detail?.code)
  }
  return body as T
}

/** 上传：multipart，浏览器自动带 boundary，不能手动设 Content-Type */
export async function uploadDocument(file: File, metadata: Record<string, unknown>) {
  const form = new FormData()
  form.append('file', file)
  form.append('metadata_json', JSON.stringify(metadata))
  const response = await fetch('/api/library/upload', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'X-P18-Client': 'workbench' },
    body: form,
  })
  const text = await response.text()
  if (!response.ok) {
    let message = '上传失败'
    try {
      const detail = JSON.parse(text).detail
      message = typeof detail === 'string' ? detail : detail?.message || message
    } catch { /* 非 JSON 响应 */ }
    throw new ApiError(message, response.status)
  }
  return text ? JSON.parse(text) : null
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  del: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}

/** 服务端返回的库记录（字段与 app/library_api.library_record 对齐） */
export interface LibraryRecord {
  id: string
  name: string
  code: string
  folder: string
  department: string
  docType: string
  classification: string
  version: string
  lifecycle: string
  status: string
  reviewCompleted: boolean
  reviewSearchable: boolean
  format: string
  createdAt: string
  metadataVersion: number
  qcIssues: string[]
}

export interface Me {
  can_create_accounts?:boolean
  role?:'boss'|'supervisor'|'employee'|'guest'
  department?:string
  job?:string
  username?: string
  identity: string
  manager: boolean
  demo?: boolean
}
