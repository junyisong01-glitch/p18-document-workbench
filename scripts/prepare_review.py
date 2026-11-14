"""Prepare an EMPTY local review library; never imports a private corpus or credential."""
from pathlib import Path
import os,sys,getpass
ROOT=Path(__file__).resolve().parents[1]
os.environ['P18_DATA_DIR']=str(ROOT/'runtime/demo-v1-experience')
os.environ['P18_SEMANTIC_ENABLED']='0'
sys.path.insert(0,str(ROOT))
def main():
    from app import main as store,library_store
    username=input('新审查管理员账号：').strip()
    password=getpass.getpass('新密码（隐藏输入，至少12字符）：')
    if password!=getpass.getpass('再次输入：'):raise SystemExit('密码不一致，未创建账号')
    store.initialize()
    with store.connect()as conn:
        library_store.create_account(conn,username,password,'研发部员工',manager=True)
        library_store.enable(conn)
    print('空资料库和账号已创建；没有导入文档、授予许可或配置AI。')
if __name__=='__main__':main()
