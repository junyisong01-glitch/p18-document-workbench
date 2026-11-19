"""LLM transports and routing. No retrieval, credentials persistence or silent egress."""
from abc import ABC, abstractmethod
import json
import os
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

class BaseLLMProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str: ...

def fail(code, message):
    from app.rag import RagError
    raise RagError(code,message)

def load_env(path):
    """Small literal-only dotenv subset; never execute shell or expand variables."""
    path=Path(path)
    if not path.is_file():return
    for line in path.read_text().splitlines():
        line=line.strip()
        if not line or line.startswith('#'):continue
        key,sep,value=line.partition('=')
        if sep and key.strip() in {'LLM_PROVIDER','DEEPSEEK_API_KEY','OLLAMA_MODEL','OLLAMA_NUM_CTX'}:
            value=value.strip()
            if len(value)>=2 and value[0]==value[-1] and value[0] in "\"'":value=value[1:-1]
            os.environ.setdefault(key.strip(),value)

def provider_name():
    name=os.environ.get('LLM_PROVIDER','deepseek').strip().lower()
    if name not in {'deepseek','ollama'}:fail('llm_configuration','LLM_PROVIDER只支持ollama或deepseek。')
    return name

def guard(source_library, provider):
    if source_library in {'qichen','qichen30','business'} and provider!='ollama':
        fail('qichen_external_forbidden','启辰库禁止发送至DeepSeek或其他外部模型，不能降级外发。')

def messages(prompt):
    from app.rag import SYSTEM
    try:value=json.loads(prompt)
    except (ValueError,TypeError):value=None
    if isinstance(value,list) and value and all(isinstance(m,dict) and set(m)=={'role','content'} and isinstance(m['content'],str) for m in value):
        if value[0]!={'role':'system','content':SYSTEM}:fail('llm_prompt','缺少受控知识库系统指令。')
        return value
    return [{'role':'system','content':SYSTEM},{'role':'user','content':prompt}]

class DeepSeekProvider(BaseLLMProvider):
    name='deepseek'
    def __init__(self, *, key=None, timeout=60, max_tokens=1500):
        self.key=key;self.timeout=timeout;self.max_tokens=max_tokens
    def generate(self,prompt):
        key=self.key if self.key is not None else os.environ.get('DEEPSEEK_API_KEY','').strip()
        if not key:fail('api_not_configured','尚未配置DeepSeek API Key。')
        try:
            import httpx
            from openai import OpenAI
        except ImportError:fail('llm_dependency','未安装OpenAI SDK，请按requirements-llm.txt安装可选依赖。')
        try:
            # Fixed official origin; no redirects/proxies/retries, and no payload logging.
            with httpx.Client(follow_redirects=False,trust_env=False,timeout=self.timeout) as http:
                with OpenAI(api_key=key,base_url='https://api.deepseek.com',max_retries=0,http_client=http) as client:
                    response=client.chat.completions.create(model='deepseek-flash',messages=messages(prompt),stream=False,
                        response_format={'type':'json_object'},temperature=0,max_tokens=self.max_tokens,extra_body={'thinking':{'type':'disabled'}})
            choice=response.choices[0]
            if choice.finish_reason!='stop':fail('incomplete_answer','模型响应未完整结束，未发布回答。')
            content=choice.message.content
            if not isinstance(content,str)or not content or len(content)>1_000_000:fail('api_response','模型返回内容无效。')
            return content
        except Exception as e:
            from app.rag import RagError
            if isinstance(e,RagError):raise
            status=getattr(e,'status_code',None)
            fail({401:'api_auth',403:'api_auth',429:'api_rate_limit'}.get(status,'api_network'),'DeepSeek调用失败，未自动重试；请检查认证、限流或网络。')

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):fail('api_redirect','模型接口重定向已阻止。')

def local_json(path, body=None, timeout=2):
    req=Request('http://localhost:11434'+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    try:
        with build_opener(ProxyHandler({}),NoRedirect()).open(req,timeout=timeout) as response:raw=response.read(1_000_001)
        if len(raw)>1_000_000:raise ValueError()
        return json.loads(raw)
    except Exception as e:
        from app.rag import RagError
        if isinstance(e,RagError):raise
        fail('ollama_unavailable','本机Ollama不可用或返回无效。请启动服务并安装所选模型；未向DeepSeek发送任何内容。')

class OllamaProvider(BaseLLMProvider):
    name='ollama'
    def __init__(self, *, model=None, num_ctx=None, timeout=60, max_tokens=1500):
        self.model=model or os.environ.get('OLLAMA_MODEL','qwen2.5:7b');self.timeout=timeout;self.max_tokens=max_tokens
        try:self.num_ctx=int(num_ctx if num_ctx is not None else os.environ.get('OLLAMA_NUM_CTX','16384'))
        except ValueError:fail('llm_configuration','OLLAMA_NUM_CTX必须为整数。')
        if self.num_ctx<16384:fail('llm_configuration','OLLAMA_NUM_CTX不得低于16384。')
    def health(self):
        value=local_json('/api/tags')
        if not any(m.get('name')==self.model or m.get('model')==self.model for m in value.get('models',[])):
            fail('ollama_model_missing','Ollama已启动，但未安装配置的模型；不会自动下载。')
        return True
    def generate(self,prompt):
        # UTF-8 byte bound is deliberately conservative: never silently trim evidence.
        if len(json.dumps(messages(prompt),ensure_ascii=False).encode('utf-8'))>self.num_ctx-self.max_tokens-512:
            fail('llm_context_limit','所选资料超过本地模型保守容量，请减少证据；未自动截断或改用外部模型。')
        self.health()
        result=local_json('/api/chat',{'model':self.model,'messages':messages(prompt),'stream':False,'format':'json','think':False,'keep_alive':0,'truncate':False,
            'options':{'num_ctx':self.num_ctx,'num_predict':self.max_tokens,'temperature':0,'seed':42}},timeout=self.timeout)
        if result.get('done') is not True or result.get('done_reason')!='stop':fail('incomplete_answer','本地模型响应截断或未完整结束，未发布回答。')
        content=result.get('message',{}).get('content')
        if not isinstance(content,str)or not content:fail('api_response','Ollama未返回有效文本。')
        return content

class ClientAdapter(BaseLLMProvider):
    """Compatibility for existing injected test/legacy clients; RAG uses generate only."""
    def __init__(self,client,cfg):self.client=client;self.cfg=cfg
    def generate(self,prompt):return self.client.complete(messages(prompt),self.cfg)

class RoutedClient:
    def __init__(self,session=False,source_library='demo'):
        self.session=session;self.source_library=source_library;self._key=None;self.fallback=False;self.selected_provider=None
    @property
    def name(self):return self.selected_provider or ('deepseek' if self.fallback else provider_name())
    @property
    def label(self):return 'Ollama（本机）' if self.name=='ollama' else 'DeepSeek'
    def credential(self):return self._key if self._key is not None else (os.environ.get('DEEPSEEK_API_KEY','').strip() if not self.session or 'LLM_PROVIDER' in os.environ else '')
    def set_key(self,key):self._key=key or ''
    def configuration(self,cfg):
        cfg=dict(cfg,provider=self.name)
        if self.name=='ollama':
            p=OllamaProvider()
            cfg.update(base_url='http://localhost:11434',model=p.model,num_ctx=p.num_ctx)
        else:cfg.update(base_url='https://api.deepseek.com',model='deepseek-flash')
        return cfg
    def provider(self,cfg):
        guard(self.source_library,self.name)
        if self.name=='ollama':return OllamaProvider(model=cfg['model'],num_ctx=cfg['num_ctx'],timeout=cfg['timeout'],max_tokens=cfg['max_tokens'])
        return DeepSeekProvider(key=self.credential(),timeout=cfg['timeout'],max_tokens=cfg['max_tokens'])
    @property
    def configured(self):
        if self.name=='ollama':
            try:return OllamaProvider().health()
            except Exception:return False
        return bool(self.credential())
    def confirm_fallback(self):
        guard(self.source_library,'deepseek')
        if self.name!='ollama':fail('fallback_unavailable','当前不在Ollama路由。')
        if self.configured:fail('fallback_unavailable','本地服务正常，不触发故障降级。')
        self.fallback=True;self.selected_provider='deepseek'
    def select_provider(self,provider,confirm_external=False):
        if provider not in {'ollama','deepseek'}:fail('llm_configuration','不支持的模型服务。')
        guard(self.source_library,provider)
        if provider=='deepseek' and confirm_external is not True:fail('external_confirmation_required','必须明确确认选择外部DeepSeek；选定后仍须逐轮确认外发。')
        self.selected_provider=provider;self.fallback=False
    def complete(self,msg,cfg):return self.provider(cfg).generate(json.dumps(msg,ensure_ascii=False))

def startup_check():
    if provider_name()=='ollama':
        try:OllamaProvider().health();return {'available':True,'provider':'ollama'}
        except Exception:return {'available':False,'provider':'ollama','notice':'Ollama服务或模型不可用；保持本地路由，不自动外发。演示库可明确确认降级后重新选证据并确认发送。'}
    return {'available':None,'provider':'deepseek'}
