"""Read-only dependency/cache checks; never downloads or loads model weights."""
import importlib.util
import os
from pathlib import Path

from app.embedding import MODEL, REVISION


def check_local_runtime():
    required = ['torch', 'transformers', 'qdrant_client', 'huggingface_hub', 'psutil']
    missing = [name for name in required if importlib.util.find_spec(name) is None]
    answer = {'ready': False, 'missing_dependencies': missing, 'model_cached': False,
              'message': '', 'model': MODEL, 'revision': os.environ.get('P18_EMBEDDING_REVISION', REVISION)}
    if missing:
        answer['message'] = '缺少本地检索依赖：' + '、'.join(missing) + '。请先安装 requirements-semantic.txt。'
        return answer
    try:
        from app.embedding import settings
        settings()
    except (ValueError, ImportError):
        answer['message'] = '本地模型配置无效，请检查版本SHA、维度和输入长度配置。'
        return answer
    try:
        from huggingface_hub import snapshot_download
        folder = Path(snapshot_download(MODEL, revision=answer['revision'], local_files_only=True))
        files = ['model.safetensors', 'config.json', 'tokenizer.json', 'tokenizer_config.json']
        answer['model_cached'] = all((folder / name).is_file() and (folder / name).stat().st_size > 0 for name in files)
    except Exception:
        pass
    answer['ready'] = answer['model_cached']
    answer['message'] = ('本地依赖与模型缓存已就绪；首次构建时加载模型。' if answer['ready'] else
                         '本地模型缓存缺失或不完整，请先手动运行模型下载步骤；系统不会自动下载。')
    return answer
