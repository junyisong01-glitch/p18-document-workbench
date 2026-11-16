"""Explicit Demo environment; never inherit credentials or old P18 paths."""
from pathlib import Path
import json,os
ROOT=Path(__file__).resolve().parents[1]
def environment(*,semantic=True):
    cfg=json.loads((ROOT/'config/demo-v1.json').read_text())
    paths={'HOME':ROOT/'.local-home','TMPDIR':ROOT/'runtime/demo-v1/tmp','XDG_CACHE_HOME':ROOT/'.cache','XDG_CONFIG_HOME':ROOT/'.local-config','XDG_DATA_HOME':ROOT/'.local-share','HF_HOME':ROOT/'.cache/huggingface','HF_HUB_CACHE':ROOT/cfg['model_cache'],'TORCH_HOME':ROOT/'.cache/torch','UV_CACHE_DIR':ROOT/'.cache/uv'}
    for path in paths.values():path.mkdir(parents=True,exist_ok=True)
    env={k:str(v) for k,v in paths.items()}
    env.update(PATH=str(ROOT/'.venv/bin')+':/usr/bin:/bin:/usr/sbin:/sbin',LANG='en_US.UTF-8',LC_ALL='en_US.UTF-8',PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',PYTHONPATH=str(ROOT/'config/runtime_guard')+os.pathsep+str(ROOT),P18_DATA_DIR=str(ROOT/cfg['data_dir']),P18_SEMANTIC_ENABLED='1' if semantic else '0',P18_SEARCH_MODE=cfg['search_mode'],P18_SEARCH_CANDIDATES=str(cfg['search_candidates']),P18_SEARCH_TOP_K=str(cfg['top_k']),P18_CHUNK_TARGET=str(cfg['chunk_target']),P18_CHUNK_OVERLAP=str(cfg['chunk_overlap']),P18_EMBEDDING_REVISION=cfg['embedding_revision'],P18_EMBEDDING_DIMENSION='1024',P18_EMBEDDING_MAX_TOKENS='4096',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',HF_HUB_DISABLE_IMPLICIT_TOKEN='1',DO_NOT_TRACK='1',TOKENIZERS_PARALLELISM='false',SOFFICE_PATH=os.environ.get('SOFFICE_PATH',cfg['converter']),OMP_NUM_THREADS='2',MKL_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
    env['P18_QUERY_VECTOR_CACHE']='1' if cfg.get('query_vector_cache',True) else '0'
    env['P18_PARSER']=cfg.get('parser_backend','legacy')
    if cfg.get('docling_python'):
        env['P18_DOCX_PYTHON']=str((ROOT/cfg['docling_python']).absolute())
    env['P18_DOCLING_FALLBACK']=cfg.get('docling_fallback','')
    env['P18_SQLITE_WAL']='1' if cfg.get('sqlite_wal',False) else '0'
    assert all('KEY' not in k and 'TOKEN' not in k or k in {'HF_HUB_DISABLE_IMPLICIT_TOKEN','TOKENIZERS_PARALLELISM','P18_EMBEDDING_MAX_TOKENS'} for k in env)
    return env
