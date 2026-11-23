import {Link} from 'react-router'
import {ArrowRight,BookOpen,FileText,MessageSquareText,Search} from 'lucide-react'

export function KnowledgeWelcome(){
 return <section className="lx-knowledge-welcome" aria-label="知识问答入口">
  <div className="lx-welcome-copy"><span className="lx-eyebrow"><BookOpen size={15}/>团队知识，随问随用</span><h2>从一个问题，找到工作所需的知识</h2><p>查找内部资料，获取有来源的回答，让每一份经验都能被用起来。</p><div className="lx-welcome-actions"><Link to="/qa" className="lx-ask-link"><MessageSquareText size={16}/>向知识库提问<ArrowRight size={16}/></Link><Link to="/documents" className="lx-browse-link">浏览资料<ArrowRight size={14}/></Link></div><small>仅使用你有权查看的已发布资料</small></div>
  <div className="lx-welcome-art" aria-hidden="true"><div className="lx-art-sheet lx-art-back"><FileText size={28}/><i/><i/><i/></div><div className="lx-art-sheet lx-art-front"><BookOpen size={30}/><i/><i/><i/></div><div className="lx-art-search"><Search size={27}/></div><span className="lx-art-caption">知识 · 连接 · 协作</span></div>
 </section>
}
