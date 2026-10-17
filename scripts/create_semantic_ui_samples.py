"""Create fictional browser acceptance files in a new directory; never overwrites."""
import argparse
from pathlib import Path
import pymupdf as fitz
from docx import Document

SAMPLES = [
 ('支付排障.pdf','支付接口故障排查','付款请求长时间没有响应时，应检查网络连接和第三方接口地址，将请求超时阈值由3秒调整到10秒，并记录请求日志和失败重试记录。'),
 ('退款规则.pdf','订单退款处理','客户取消已支付订单时，先核对交易状态，通过原支付渠道退回款项，记录退款流水号。退款需要财务复核，不能重复发起。'),
 ('设备预约.pdf','实验设备预约','预约实验设备必须提供设备编号与使用时长，每次预约不得超过120分钟。预约冲突时需要更换时段。'),
 ('部署回滚.pdf','生产发布回滚','新版本上线后错误率升高，应停止继续发布并回退到上一稳定版本。回滚前保留日志和数据库备份，随后执行健康检查。'),
 ('账号权限.pdf','人员离职权限处理','员工离职时应立即停用账号，撤销代码仓库、服务器及内部文档访问权限，并交接负责的工作。'),
 ('数据库备份.pdf','数据库恢复流程','数据库每日执行全量备份并加密存储，误删业务记录时，应先恢复备份到隔离环境，验证完整性后再恢复生产数据。'),
]


def pdf(path,title,text,cover=False):
    doc=fitz.open()
    if cover:doc.new_page().insert_text((60,70),'FICTIONAL TEST DOCUMENT - Cover')
    doc.new_page().insert_textbox(fitz.Rect(40,40,550,780),title+'\n\n'+text,fontname='china-s',fontsize=12)
    doc.save(path);doc.close()


def create(directory, include_limit=False):
    directory.mkdir(parents=True,exist_ok=False)
    for i,(name,title,text) in enumerate(SAMPLES):pdf(directory/name,title,text,cover=i==0)
    doc=Document();doc.add_heading('软件安装操作与依赖配置',level=1)
    doc.add_paragraph('安装研发工具前先检查 Python 版本，创建独立虚拟环境，再安装项目所需依赖。安装完成后运行健康检查确认服务正常。')
    doc.save(directory/'07-安装说明.docx')
    doc=Document();doc.add_paragraph('须知')
    for _ in range(2):doc.add_paragraph('重复流程规范：每次上线都必须执行健康检查并记录发布版本。')
    doc.save(directory/'08-重复流程规范.docx')
    doc=Document();doc.add_heading('合并参数表复核样例',level=1);table=doc.add_table(rows=3,cols=2)
    table.cell(0,0).merge(table.cell(0,1)).text='接口调用配置参数'
    for row,values in zip(table.rows[1:],[('请求超时','10秒'),('重试次数','最多2次')]):
        for cell,value in zip(row.cells,values):cell.text=value
    doc.save(directory/'09-合并表格复核.docx')
    text='研发应用发布前的完整核验要求如下。'+''.join(f'第{i}项核验需要确认环境配置、依赖版本和访问权限，保存对应检查记录。' for i in range(1,10))+'发布完成后还应持续观察错误率、响应时间和用户反馈，发现异常应及时回滚。'
    pdf(directory/'10-长片段核验.pdf','完整发布核验清单',text)
    if include_limit:
        doc=Document();doc.add_heading('超长输入限制测试',level=1)
        doc.add_table(rows=1,cols=1).cell(0,0).text='validation '*5000
        doc.save(directory/'11-超长表格限制.docx')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path);parser.add_argument('--include-limit-case',action='store_true')
    args=parser.parse_args();create(args.directory,args.include_limit_case)
    print('已生成独立虚构验收样例：'+str(args.directory))
