import {Link} from 'react-router'
import {useSession} from '@/lib/session'
import {KnowledgeGapList} from '@/components/KnowledgeGaps'
export default function KnowledgeGapsPage(){
 const {user,kbId}=useSession()
 if(kbId!=='business'||!['employee','supervisor'].includes(user?.accessRole||''))return <p className="text-sm">此页供内部员工和部门主管使用。<Link to="/" className="ml-2 text-primary">返回首页</Link></p>
 return <div className="mx-auto max-w-4xl"><KnowledgeGapList/></div>
}
