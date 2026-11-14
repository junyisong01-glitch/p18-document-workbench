import {useState} from 'react';
import Modal from '@/components/ui/Modal';
import {INPUT_CLASS} from '@/components/ui/formStyles';
import type {NewFolderInput} from '@/lib/documentStore';
export default function NewFolderDialog({onSubmit,onClose}:{existingNames:string[];onSubmit:(v:NewFolderInput)=>Promise<void>;onClose:()=>void}){
 const [name,setName]=useState(''),[error,setError]=useState(''),[pending,setPending]=useState(false);
 return <Modal title="新建文件夹" description="文件夹用于归档；所属部门与查看权限在每份文档上设置。" onClose={onClose} footer={<button disabled={pending||!name.trim()} className="rounded-xl bg-blue-600 text-white px-5 py-2" onClick={async()=>{setPending(true);try{await onSubmit({name:name.trim()});onClose();}catch(e){setError((e as Error).message);}finally{setPending(false);}}}>创建文件夹</button>}><label>文件夹名称<input className={INPUT_CLASS} value={name} maxLength={100} onChange={e=>setName(e.target.value)}/></label><p role="alert">{error}</p></Modal>;
}
