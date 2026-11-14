"""Offline acceptance fixture only. Not an AI response or production transport."""
import json
class OfflineResponse:
 def __enter__(self):return self
 def __exit__(self,*a):pass
 def read(self,n):
  global _fixture_count
  _fixture_count+=1
  content={'status':'answered','answer':'【验收模拟】晨间校准时长为18分钟。[S1]','citations':['S1']}if _fixture_count==1 else {'status':'insufficient_evidence','answer':'【验收模拟】现有资料不能确认保修期。','citations':[]}
  return json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(content,ensure_ascii=False)}}],'model':'offline-acceptance-not-DeepSeek','usage':{'total_tokens':0}},ensure_ascii=False).encode()
_fixture_count=0
