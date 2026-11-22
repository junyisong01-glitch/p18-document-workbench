from app.admission import sync_admission
from app.business_review import review_reasons, technical_ready


def test_release_reasons_check_real_values_and_report_only_location():
    assert review_reasons({'result':{'blocks':[{'text':'填写身份证号。客户名称：填写客户名称。报价按流程提交。'}]}},{})==[]
    doc={'result':{'blocks':[
        {'page':2,'text':'客户名称：示例设备有限公司。'},
        {'kind':'table','label':'私有值', 'tables':[{'rows':[['报价金额','备注'],['8000','测试']]}]},
    ]}}
    reasons=review_reasons(doc,{})
    assert reasons==['第 2 页含客户名称或姓名','表格含具体报价或合同金额']
    assert review_reasons(doc,{'restricted':True})[0]=='标为机密'


def test_only_preview_warning_can_pass_new_documents():
    doc={'id':'x','state':'review','revision':1,'characters':15,'publication_rules':1,
         'result':{'preview_warnings':['预览版式有差异'],'issues':[]}}
    sync_admission(doc)
    assert technical_ready(doc) and doc['admission']['eligible']
    doc['result']['issues']=[{'kind':'table'}]
    sync_admission(doc)
    assert not technical_ready(doc) and not doc['admission']['eligible']
