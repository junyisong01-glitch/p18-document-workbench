import { isLocalAnswerEndpoint } from './confirmation-presentation'

const externalEndpoint = 'https://api.deepseek.com/chat/completions'

export type QaPreparedRoute = {
  request_endpoint?: string
  provider?: string
  messages?: unknown
}

export function externalQuestion(prepared: QaPreparedRoute): string | null {
  const messages = prepared.messages
  if (prepared.request_endpoint !== externalEndpoint || !Array.isArray(messages) || messages.length !== 1) return null
  const message = messages[0]
  return message?.role === 'user' && typeof message.content === 'string' ? message.content : null
}

export function answerRoute(prepared: QaPreparedRoute): 'local' | 'confirm_external' | 'unavailable' {
  if (isLocalAnswerEndpoint(prepared.request_endpoint) && /^Ollama(?:$|[ （(·])/.test(prepared.provider || '')) {
    return 'local'
  }
  return externalQuestion(prepared) !== null ? 'confirm_external' : 'unavailable'
}
