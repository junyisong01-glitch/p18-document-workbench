import {useState} from 'react'
import * as Popover from '@radix-ui/react-popover'
import {CalendarDays,Clock3} from 'lucide-react'
import {DayPicker} from 'react-day-picker'
import {zhCN} from 'date-fns/locale'
import 'react-day-picker/style.css'

function calendarDate(value:string){return value?new Date(value+'T12:00:00'):undefined}
function dateKey(date:Date){return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`}
function beijingToday(){const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());return ['year','month','day'].map(key=>parts.find(p=>p.type===key)!.value).join('-')}
export function OperationTimePicker({label,value,onChange,withTime=false,end=false}:{label:string;value:string;onChange:(value:string)=>void;withTime?:boolean;end?:boolean}){
 const [open,setOpen]=useState(false)
 const [day,time]=value.split('T'),clock=time||(end?'23:59':'00:00'),[hour,minute]=clock.split(':')
 const today=calendarDate(beijingToday())!,selected=calendarDate(day)
 function choose(date?:Date){onChange((date?dateKey(date):'')+(withTime?'T'+clock:''));setOpen(false)}
 const dateLabel=withTime?(end?'结束日期':'开始日期'):label
 return <fieldset className="operation-time-picker"><legend>{label}</legend><div className="operation-time-control">
   <Popover.Root open={open} onOpenChange={setOpen}><Popover.Trigger asChild><button type="button" aria-label={dateLabel} className={'operation-date-trigger'+(!day?' is-empty':'')}><CalendarDays size={16}/><span>{day?day.replaceAll('-',' / '):'选择日期'}</span></button></Popover.Trigger>
     <Popover.Portal><Popover.Content sideOffset={8} align="start" className="operation-calendar" aria-label={dateLabel+'日历'}>
       <DayPicker mode="single" selected={selected} defaultMonth={selected||today} today={today} onSelect={choose} locale={zhCN} weekStartsOn={1} autoFocus showOutsideDays captionLayout="dropdown" startMonth={new Date(1970,0)} endMonth={new Date(today.getFullYear()+1,11)}/>
       <div className="operation-calendar-footer"><button type="button" onClick={()=>choose(today)}>今天</button><button type="button" onClick={()=>choose()}>清除日期</button></div>
     </Popover.Content></Popover.Portal>
   </Popover.Root>
   {withTime&&<div className="operation-clock"><Clock3 size={15}/><select aria-label={label+'小时'} value={hour} onChange={e=>onChange(day+'T'+e.target.value+':'+minute)}>{Array.from({length:24},(_,i)=>String(i).padStart(2,'0')).map(h=><option value={h} key={h}>{h}</option>)}</select><span>:</span><select aria-label={label+'分钟'} value={minute} onChange={e=>onChange(day+'T'+hour+':'+e.target.value)}>{Array.from({length:60},(_,i)=>String(i).padStart(2,'0')).map(m=><option value={m} key={m}>{m}</option>)}</select></div>}
 </div></fieldset>
}
