"""One offline Qwen process. No remote inference or automatic model fallback."""
import importlib.metadata
import multiprocessing
import os
from pathlib import Path
import re
import threading
import time
from typing import Protocol

MODEL = 'Qwen/Qwen3-Embedding-0.6B'
REVISION = '97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3'
INSTRUCTION = 'Given a question, retrieve relevant passages that answer the question'


class EmbeddingError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class EmbeddingProvider(Protocol):
    config: dict
    def encode(self, texts: list[str], *, query: bool = False) -> list[list[float]]: ...
    def close(self): ...


def settings():
    revision = os.environ.get('P18_EMBEDDING_REVISION', REVISION)
    dimension = int(os.environ.get('P18_EMBEDDING_DIMENSION', '1024'))
    max_tokens = int(os.environ.get('P18_EMBEDDING_MAX_TOKENS', '4096'))
    if not re.fullmatch('[0-9a-f]{40}', revision) or not 32 <= dimension <= 1024 or not 128 <= max_tokens <= 32768:
        raise ValueError('模型版本须为完整 SHA；维度须为32–1024，最大输入须为128–32768 tokens。')
    return {'provider': 'local-qwen', 'model': MODEL, 'revision': revision,
            'dimension': dimension, 'max_tokens': max_tokens, 'query_instruction': INSTRUCTION,
            'pooling': 'last-token-left-padding', 'normalize': True, 'device': 'cpu', 'dtype': 'float32',
            'torch': importlib.metadata.version('torch'), 'transformers': importlib.metadata.version('transformers')}


def _worker(pipe, config):
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    os.environ['TOKENIZERS_PARALLELISM'] = 'false'
    try:
        import psutil
        import torch
        from transformers import AutoModel, AutoTokenizer
        from huggingface_hub import snapshot_download
        started = time.perf_counter()
        path = snapshot_download(config['model'], revision=config['revision'], local_files_only=True)
        # Pin both the immutable snapshot and the installed implementation. No remote code.
        tokenizer = AutoTokenizer.from_pretrained(path, padding_side='left', local_files_only=True, trust_remote_code=False)
        model = AutoModel.from_pretrained(path, local_files_only=True, trust_remote_code=False,
                                         dtype=torch.float32, attn_implementation='sdpa').to('cpu').eval()
        pipe.send(('ready', {'load_seconds': time.perf_counter()-started, 'rss_bytes': psutil.Process().memory_info().rss,
                             'snapshot': Path(path).name, 'native_dimension': model.config.hidden_size, 'output_dimension': config['dimension']}))
    except Exception:
        pipe.send(('error', 'model_unavailable', '本地模型未下载完整、版本不存在或加载失败；不会切换外部服务。'))
        return
    while True:
        try:
            request = pipe.recv()
            if request is None:
                break
            text, query = request
            if query:
                text = f"Instruct: {config['query_instruction']}\nQuery:{text}"
            batch = tokenizer(text, return_tensors='pt', truncation=False)
            if batch['input_ids'].shape[1] > config['max_tokens']:
                pipe.send(('error', 'input_too_long', '输入超过当前模型 token 限制，未截断或生成部分向量。'))
                continue
            started = time.perf_counter()
            with torch.inference_mode():
                output = model(**batch).last_hidden_state[:, -1].float()[:, :config['dimension']]
                vector = torch.nn.functional.normalize(output, p=2, dim=1)[0]
            if not torch.isfinite(vector).all() or vector.norm().item() < .99:
                raise ValueError('invalid vector')
            pipe.send(('vector', vector.tolist(), {'seconds': time.perf_counter()-started,
                       'rss_bytes': psutil.Process().memory_info().rss, 'tokens': batch['input_ids'].shape[1]}))
        except EOFError:
            break
        except Exception:
            pipe.send(('error', 'embedding_failed', '本地向量生成失败；未返回替代向量。'))
    pipe.close()


class LocalQwen:
    def __init__(self):
        self.config = settings()
        self.timeout = float(os.environ.get('P18_EMBEDDING_TIMEOUT', '180'))
        if self.timeout <= 0 or self.timeout > 600:
            raise ValueError('向量任务超时须为0–600秒之间。')
        self.lock = threading.Lock()
        self.process = self.pipe = None
        self.metrics = {}
        self.last_error = None

    def _receive(self):
        if not self.pipe.poll(self.timeout):
            self.last_error = {'code': 'embedding_timeout', 'message': '本地模型任务超时。'}
            self._stop()
            raise EmbeddingError('embedding_timeout', '本地模型加载或向量化超时，可重试；不会调用外部 API。')
        try:
            response = self.pipe.recv()
        except (EOFError, OSError) as exc:
            self._stop()
            raise EmbeddingError('model_unavailable', '本地模型进程中断，请重试。') from exc
        if response[0] == 'error':
            self.last_error = {'code': response[1], 'message': response[2]}
            raise EmbeddingError(response[1], response[2])
        return response

    def _start(self):
        if self.process is not None and self.process.is_alive():
            return
        self._stop()
        context = multiprocessing.get_context('spawn')
        self.pipe, child = context.Pipe()
        self.process = context.Process(target=_worker, args=(child, self.config), daemon=True)
        self.process.start()
        child.close()
        try:
            response = self._receive()
            self.metrics.update(response[1])
        except Exception:
            self._stop()
            raise

    def encode(self, texts, *, query=False):
        if not self.lock.acquire(timeout=self.timeout):
            raise EmbeddingError('embedding_timeout', '本地模型繁忙，请稍后重试。')
        try:
            self._start()
            vectors = []
            for text in texts:  # One item at a time: bounded activation memory.
                self.pipe.send((text, query))
                response = self._receive()
                if response[0] != 'vector':
                    raise EmbeddingError('embedding_failed', '本地模型返回异常。')
                self.last_error = None
                vectors.append(response[1])
                self.metrics.update(response[2])
            return vectors
        finally:
            self.lock.release()

    def _stop(self):
        if self.process is not None:
            if self.process.is_alive():
                self.process.terminate()
            self.process.join(timeout=5)
            self.process = None
        if self.pipe is not None:
            self.pipe.close()
            self.pipe = None

    def close(self):
        with self.lock:
            self._stop()
