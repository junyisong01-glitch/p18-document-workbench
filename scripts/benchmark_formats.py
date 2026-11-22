"""Measure local parsing only, with each file in a fresh process. Never publishes data."""
import argparse
import json
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import tempfile
import time


def measure(path):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from app.parser import process
    started=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='p18-format-bench-') as directory:
        folder=Path(directory)
        shutil.copyfile(path,folder/('original'+path.suffix.lower()))
        result=process(folder,path.suffix.lower())
    peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    child_peak=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    if sys.platform!='darwin':peak*=1024;child_peak*=1024
    return dict(file=path.name,bytes=path.stat().st_size,seconds=round(time.monotonic()-started,3),
        parser_peak_mib=round(peak/1024/1024,1),child_peak_mib=round(child_peak/1024/1024,1),characters=result['characters'],
        issues=len(result['issues']),error=result.get('error'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files',type=Path,nargs='+')
    parser.add_argument('--child',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.child:
        print(json.dumps(measure(args.files[0]),ensure_ascii=False));return
    for path in args.files:
        child=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--child',str(path.resolve())],
            capture_output=True,text=True,timeout=130)
        if child.returncode:raise SystemExit(child.stderr)
        print(child.stdout.strip(),flush=True)


if __name__=='__main__':main()
