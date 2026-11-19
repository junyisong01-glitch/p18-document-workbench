"""Legacy urllib compatibility adapter; explicit LLM_PROVIDER uses app.llm providers."""
import os,json,threading
from urllib.request import Request
from urllib.error import HTTPError,URLError

class DeepSeekClient:
    label='DeepSeek'
    def credential(self):return os.environ.get('DEEPSEEK_API_KEY','').strip()
    @property
    def configured(self):return bool(self.credential())

    def complete(self, messages, cfg):
        from app.rag import RagError, request_endpoint, secure_urlopen
        key=self.credential()
        if not key:raise RagError('api_not_configured','尚未配置DeepSeek密钥，文档管理及知识检索仍可使用。')
        body={'model':cfg['model'],'messages':messages,'stream':False,'thinking':{'type':'disabled'},
              'response_format':{'type':'json_object'},'max_tokens':cfg['max_tokens']}
        req=Request(request_endpoint(cfg['base_url']),data=json.dumps(body).encode(),
                    headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
        # No automatic retries (a retry may be billed), no key/body/error-body logging.
        try:
            with secure_urlopen(req,timeout=cfg['timeout']) as response:
                raw=response.read(1_000_001)
            if len(raw)>1_000_000:raise ValueError()
            result=json.loads(raw);choice=result['choices'][0]
            if choice.get('finish_reason')!='stop':raise RagError('incomplete_answer','模型响应未完整结束，未发布回答，请检查输出限制后手动重试。')
            return choice['message']['content']
        except HTTPError as error:
            code={401:'api_auth',403:'api_auth',429:'api_rate_limit'}.get(error.code,'api_http_error')
            raise RagError(code, 'DeepSeek认证失败，请检查后端配置。' if code=='api_auth' else 'DeepSeek限流，请稍后手动重试。' if code=='api_rate_limit' else 'DeepSeek服务请求失败，未生成回答。') from None
        except (TimeoutError,):raise RagError('api_timeout','DeepSeek请求超时，未自动重试，可能已产生费用。') from None
        except URLError as error:
            if isinstance(error.reason,TimeoutError):raise RagError('api_timeout','DeepSeek请求超时，未自动重试，可能已产生费用。') from None
            raise RagError('api_network','无法连接DeepSeek，未自动重试。') from None
        except OSError:raise RagError('api_network','外部连接中断，未自动重试。') from None
        except (KeyError,ValueError,TypeError,IndexError):raise RagError('api_response','DeepSeek返回格式不符合要求，未发布回答。') from None




class SessionDeepSeekClient(DeepSeekClient):
    """Never inherits an operator's global key; no persistence or key echo."""
    def __init__(self):
        self._key = None
        self._credential_lock = threading.RLock()
    def credential(self):
        with self._credential_lock:
            return self._key or ''
    def complete(self, messages, cfg):
        from app.rag import RagError, request_endpoint, secure_urlopen
        if request_endpoint(cfg['base_url']) != 'https://api.deepseek.com/chat/completions':
            raise RagError('destination_not_allowed','个人密钥仅允许发送到官方DeepSeek接口。')
        return super().complete(messages, cfg)
    def set_key(self, value):
        with self._credential_lock:
            self._key = value
