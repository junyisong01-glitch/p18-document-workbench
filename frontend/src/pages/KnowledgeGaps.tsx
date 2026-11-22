import {Link} from 'react-router'
import {useSession} from '@/lib/session'
import {KnowledgeGapList} from '@/components/KnowledgeGaps'
import {FeedbackList} from '@/components/QuestionFeedback'
export default function KnowledgeGapsPage(){
 const {user,kbId}=useSession()
 if(kbId!=='business'||!['employee','supervisor','boss'].includes(user?.accessRole||''))return <p className="text-sm">此页供内部账号查看主动提交的反馈。<Link to="/" className="ml-2 text-primary">返回首页</Link></p>
 return <div className="mx-auto max-w-4xl space-y-8"><FeedbackList/>{user?.accessRole!=='boss'&&<KnowledgeGapList/>}</div>
}
