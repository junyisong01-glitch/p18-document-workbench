"""Reproduce offline real-model acceptance in independent pytest directories."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    target = args.output or Path(tempfile.mkdtemp(prefix='p18-semantic-evidence-')) / 'results.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env['P18_TEST_LOCAL_EMBEDDINGS'] = '1'
    env['P18_SEMANTIC_EVIDENCE'] = str(target.resolve())
    root = Path(__file__).resolve().parent.parent
    result = subprocess.run([sys.executable, '-m', 'pytest', '-q', 'tests/test_semantic.py'], cwd=root, env=env)
    if result.returncode == 0:
        print('真实检索与生命周期验证记录：' + str(target))
    sys.exit(result.returncode)
