import {useCallback,useEffect,useState} from 'react';
import {api,fetchDocuments,fetchFolders,fetchDocTypes,insertDocument,deleteDocument,insertFolder,insertDocType,type NewDocumentInput,type NewFolderInput} from '@/lib/documentStore';
import type {DocumentRecord,FolderRecord,DocTypeRecord} from '@/types/document';
export function useDocumentLibrary(){
 const [documents,setDocuments]=useState<DocumentRecord[]>([]),[folders,setFolders]=useState<FolderRecord[]>([]),[docTypes,setDocTypes]=useState<DocTypeRecord[]>([]);
 const [user,setUser]=useState({identity:'',manager:false,demo:false});
 const [loadState,setLoadState]=useState<'loading'|'ready'|'error'>('loading'),[errorMessage,setErrorMessage]=useState('');
 const reload=useCallback(async()=>{try{const me=await api('/api/library/me');const [d,f,t]=await Promise.all([fetchDocuments(),fetchFolders(),fetchDocTypes()]);setUser(me);setDocuments(d);setFolders(f);setDocTypes(t);setErrorMessage('');setLoadState('ready');}catch(e){setDocuments([]);setErrorMessage(e instanceof Error?e.message:'加载失败');setLoadState('error');}},[]);
 useEffect(()=>{void reload();const timer=setInterval(()=>void reload(),5000);return()=>clearInterval(timer);},[reload]);
 const addDocument=async(input:NewDocumentInput)=>{await insertDocument(input);await reload();};
 const removeDocument=async(id:string)=>{await deleteDocument(id);await reload();};
 const addFolder=async(input:NewFolderInput)=>{await insertFolder(input);await reload();};
 const addDocType=async(name:string)=>{await insertDocType(name);await reload();};
 return {documents,folders,docTypes,user,loadState,errorMessage,reload,addDocument,removeDocument,addFolder,addDocType};
}
