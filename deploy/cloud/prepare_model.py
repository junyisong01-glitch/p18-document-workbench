"""Download only public, pinned embedding weights; no document is sent."""
from huggingface_hub import snapshot_download

if __name__ == '__main__':
    snapshot_download('Qwen/Qwen3-Embedding-0.6B', revision='97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3', allow_patterns=['*.json', '*.safetensors', '*.txt', '*.model', 'merges.txt'])
    print('Pinned original retrieval model cached; no alternative model selected.')
