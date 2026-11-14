"""Demo process boundary: no outside writes or non-loopback network."""
import sys,os,socket,threading
from contextlib import contextmanager
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
_active=threading.local()
@contextmanager
def official_deepseek_request():
    previous=getattr(_active,"ips",set())
    _active.ips={x[4][0] for x in socket.getaddrinfo("api.deepseek.com",443,type=socket.SOCK_STREAM)}
    try:yield
    finally:_active.ips=previous
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
        if isinstance(address,tuple) and address[0] not in {'127.0.0.1','::1','localhost'}:
            if not(address[0]in getattr(_active,'ips',set())and address[1]==443):raise PermissionError('Demo non-loopback connection blocked')
sys.addaudithook(guard)
