// 使用原生会话凭据接口；不写入浏览器存储，不从浏览器直连模型服务。
import { api } from './api'

export interface ModelConfigStatus {
  configured: boolean
  provider: string
  baseUrl: string
  endpoint: string
  model: string
}

export async function loadModelConfig(): Promise<ModelConfigStatus> {
  const [credentials, health] = await Promise.all([
    api.get<{configured:boolean;provider:string;endpoint:string}>('/api/rag/credentials'),
    api.get<{configured:boolean;provider:string;destination:string;model:string;error?:string}>('/api/rag'),
  ])
  if (health.error || !health.model || !health.destination || !credentials.endpoint) {
    throw new Error('当前后端模型配置不可用，请先检查部署配置。本地检索仍可使用。')
  }
  return {
    configured: credentials.configured && health.configured,
    provider: credentials.provider,
    baseUrl: health.destination,
    endpoint: credentials.endpoint,
    model: health.model,
  }
}

export async function saveModelKey(apiKey: string): Promise<void> {
  await api.put('/api/rag/credentials', {api_key:apiKey.trim()})
}

export async function clearModelKey(): Promise<void> {
  await api.del('/api/rag/credentials')
}
