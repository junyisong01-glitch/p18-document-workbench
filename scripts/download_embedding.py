"""Explicit, download-only setup. Never called during indexing or retrieval."""
import os
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
from huggingface_hub import snapshot_download
from app.embedding import MODEL, REVISION

if __name__ == '__main__':
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    revision = os.environ.get('P18_EMBEDDING_REVISION', REVISION)
    print(snapshot_download(MODEL, revision=revision,
          allow_patterns=['*.json', '*.txt', '*.safetensors'], max_workers=2))
