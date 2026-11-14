"""Demo process boundary: no outside writes or non-loopback network."""
import sys,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def safe_write(value):
    if isinstance(value,int) or value is None:return
    path=Path(os.fsdecode(value))
    if str(path) in {'/dev/null','/dev/tty'}:return
    if not path.resolve().is_relative_to(ROOT):raise PermissionError('Demo write outside isolated root blocked')
def guard(event,args):
    if event=='open':
        path,mode,flags=args
        if (mode and any(x in mode for x in 'wax+')) or (flags and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)):safe_write(path)
    elif event in {'os.mkdir','os.remove','os.rmdir','os.truncate','os.chmod','os.utime'}:safe_write(args[0])
    elif event in {'os.rename','os.link'}:
        safe_write(args[0]);safe_write(args[1])
    elif event=='os.symlink':safe_write(args[1])
    elif event=='socket.connect':
        address=args[1]
        if isinstance(address,tuple) and address[0] not in {'127.0.0.1','::1','localhost'}:raise PermissionError('Demo non-loopback connection blocked')
sys.addaudithook(guard)
