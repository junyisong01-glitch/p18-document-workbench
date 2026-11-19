"""Document-library policy. Callers must obtain identity from a trusted session.

This module does not authenticate users or grant external-model permission.
Folder placement never grants document access.
"""
from dataclasses import dataclass


IDENTITIES = {
    '只读访客': '',
    '启辰研发岗位': '研发部',
    '启辰测试岗位': '研发部',
    '启辰运维岗位': '研发部',
    '启辰生产岗位': '生产制造部',
    '研发部员工': '研发部',
    '生产制造部员工': '生产制造部',
    '财务部普通员工': '财务部',
    '财务经理': '财务部',
    '财务总监': '财务部',
    '人力资源部普通员工': '人力资源部',
    '薪酬专员': '人力资源部',
    '人力资源总监': '人力资源部',
    '行政安全部员工': '行政安全部',
    '总经理': '管理层',
}


@dataclass(frozen=True)
class LibraryMetadata:
    code: str
    name: str
    folder: str
    department: str
    doc_type: str
    classification: str
    version: str
    lifecycle: str
    viewers: tuple[str, ...] = ()

    def __post_init__(self):
        if self.classification not in {'公开', '内部', '机密'}:
            raise ValueError('未知密级')
        if self.lifecycle not in {'现行有效', '已废止'}:
            raise ValueError('未知文档状态')
        if not all(isinstance(v, str) and v.strip() for v in
                   (self.code, self.name, self.folder, self.department, self.doc_type, self.version)):
            raise ValueError('文档管理字段不能为空')
        if self.classification == '机密' and any(v not in IDENTITIES for v in self.viewers):
            raise ValueError('机密文档查看范围包含未知身份')


def can_view(meta: LibraryMetadata, identity: str) -> bool:
    if identity not in IDENTITIES:
        return False
    if meta.classification == '公开':
        return True
    if meta.classification == '内部':
        return identity == '总经理' or IDENTITIES[identity] == meta.department
    return identity in meta.viewers


def can_use_as_evidence(meta: LibraryMetadata, identity: str) -> bool:
    return meta.lifecycle == '现行有效' and can_view(meta, identity)


def can_send_external(meta: LibraryMetadata, identity: str, *, existing_permission: bool) -> bool:
    return (meta.classification != '机密' and can_use_as_evidence(meta, identity)
            and existing_permission is True)
