import type {DocumentRecord, FolderRecord, DocTypeRecord} from '@/types/document';
export async function api(path:string, init:RequestInit={}):Promise<any> {
  const response=await fetch(path,{...init,headers:{'X-P18-Client':'workbench',...init.headers}});
  if(response.status===401){location.replace('/login');throw new Error('登录已失效');}
  const value=await response.json();
  if(!response.ok)throw new Error(typeof value.detail==='string'?value.detail:(value.detail?.message||'操作失败，请刷新后重试'));
  return value;
}
export const fetchDocuments=():Promise<DocumentRecord[]>=>api('/api/library/documents');
export const fetchFolders=():Promise<FolderRecord[]>=>api('/api/library/catalog/folders');
export const fetchDocTypes=():Promise<DocTypeRecord[]>=>api('/api/library/catalog/types');
export const deleteDocument=(id:string)=>api(`/api/documents/${encodeURIComponent(id)}`,{method:'DELETE'});
export type NewFolderInput={name:string};
export const insertFolder=(body:NewFolderInput)=>api('/api/library/catalog/folders',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
export const insertDocType=(name:string)=>api('/api/library/catalog/types',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})});
export type NewDocumentInput={file:File; metadata:Record<string,unknown>};
export async function insertDocument(input:NewDocumentInput):Promise<DocumentRecord>{
 const body=new FormData();body.set('file',input.file);body.set('metadata_json',JSON.stringify({...input.metadata,expected_version:0}));
 return api('/api/library/upload',{method:'POST',body});
}
