import os, re, uuid
import httpx
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
try:
    from openai import OpenAI
except ImportError:
    OpenAI=None
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, String, Float, DateTime, Text, ForeignKey, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session

# Load backend-local settings without overriding explicitly supplied environment.
load_dotenv(Path(__file__).resolve().parent / '.env', override=False)
OPENAI_API_KEY=os.getenv('OPENAI_API_KEY')
OPENAI_BASE_URL=os.getenv('OPENAI_BASE_URL') or None
OPENAI_MODEL=os.getenv('OPENAI_MODEL','gpt-4o-mini')
openai_client=OpenAI(api_key=OPENAI_API_KEY,base_url=OPENAI_BASE_URL,timeout=15.0,max_retries=0) if OPENAI_API_KEY and OpenAI else None
SARVAM_API_KEY=os.getenv('SARVAM_API_KEY')
SARVAM_MODEL=os.getenv('SARVAM_MODEL','sarvam-105b')
AI_PROVIDER=os.getenv('AI_PROVIDER','openai').strip().lower()
SARVAM_CHAT_URL='https://api.sarvam.ai/v1/chat/completions'
SUPPORT_SYSTEM_PROMPT=(
    'You are ResolveMate, a concise and helpful customer-support assistant. '
    'The application can look up synthetic transaction records through backend-controlled tools, '
    'create support tickets, and prepare human-review escalations. These capabilities belong to '
    'the backend workflows; you do not directly perform them in an ordinary chat response. '
    'Only state transaction details or ticket IDs when verified results are explicitly provided '
    'in the current conversation. Never invent transaction details, statuses, amounts, or ticket IDs. '
    'You cannot execute actual refunds, payments, transfers, or other financial operations, and must '
    'never claim they were performed. Direct sensitive financial requests to human review. '
    'Do not request passwords, PINs, or one-time codes.'
)
provider_status='not_checked'
provider_error_category=None
provider_http_status=None
provider_error_stage=None
provider_exception_class=None
provider_response_content_type=None

def configured_provider():
    if AI_PROVIDER == 'sarvam':
        return ('Sarvam AI', bool(SARVAM_API_KEY), SARVAM_MODEL)
    if AI_PROVIDER == 'openai':
        return ('OpenAI', bool(openai_client), OPENAI_MODEL)
    return (AI_PROVIDER, False, None)

def generate_ai_reply(message):
    """Call the selected provider for ordinary support questions only."""
    if AI_PROVIDER == 'sarvam':
        if not SARVAM_API_KEY:
            raise RuntimeError('Sarvam is not configured')
        response=None
        stage='sending_request'
        try:
            response=httpx.post(
                SARVAM_CHAT_URL,
                headers={'api-subscription-key': SARVAM_API_KEY},
                json={'model':SARVAM_MODEL,'messages':[
                    {'role':'system','content':SUPPORT_SYSTEM_PROMPT},
                    {'role':'user','content':message[:2000]},
                ],'max_tokens':300},
                timeout=15.0,
            )
            stage='receiving_response'
            response.raise_for_status()
            content_type=getattr(response,'headers',{}).get('content-type')
            stage='decoding_json'
            payload=response.json()
            stage='extracting_message'
            content=payload['choices'][0]['message']['content']
            if not isinstance(content,str) or not content.strip():
                raise ValueError('empty generated message')
            return content
        except Exception as error:
            error.safe_stage=stage
            status_code=response.status_code if response is not None else getattr(getattr(error,'response',None),'status_code',None)
            error.safe_status_code=status_code if isinstance(status_code,int) and status_code >= 400 else None
            error.safe_content_type=content_type if 'content_type' in locals() else (getattr(response,'headers',{}).get('content-type') if response is not None else None)
            raise
    if AI_PROVIDER == 'openai':
        if openai_client is None:
            raise RuntimeError('OpenAI is not configured')
        completion=openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {'role':'system','content':SUPPORT_SYSTEM_PROMPT},
                {'role':'user','content':message[:2000]},
            ], max_tokens=300,
        )
        return completion.choices[0].message.content
    raise RuntimeError('Unknown AI provider')

def provider_error_details(error):
    """Return an allowlisted category, numeric status, and safe stage metadata."""
    if isinstance(error, httpx.TimeoutException):
        return 'timeout', None
    if isinstance(error, httpx.NetworkError):
        return 'network_error', None
    if isinstance(error, httpx.HTTPStatusError):
        code=error.response.status_code
        if code == 401: category='authentication'
        elif code == 403: category='permission'
        elif code == 404: category='not_found'
        elif code == 429: category='rate_limit_or_quota'
        elif code >= 500: category='server_error'
        else: category='response_error'
        return category, code
    if isinstance(error, httpx.HTTPError):
        return 'network_error', None
    return 'response_error', getattr(error,'safe_status_code',None)

DB_URL=os.getenv('DATABASE_URL','sqlite:///./resolvemate.db')
engine=create_engine(DB_URL, connect_args={'check_same_thread':False} if DB_URL.startswith('sqlite') else {})
SessionLocal=sessionmaker(bind=engine, autoflush=False)
class Base(DeclarativeBase): pass
def now(): return datetime.now(timezone.utc)
class Transaction(Base):
    __tablename__='transactions'
    id: Mapped[str]=mapped_column(String,primary_key=True); amount: Mapped[float]=mapped_column(Float); status: Mapped[str]=mapped_column(String); method: Mapped[str]=mapped_column(String); description: Mapped[str]=mapped_column(String); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class Ticket(Base):
    __tablename__='tickets'
    id: Mapped[str]=mapped_column(String,primary_key=True); issue: Mapped[str]=mapped_column(Text); category: Mapped[str]=mapped_column(String); transaction_id: Mapped[Optional[str]]=mapped_column(String,nullable=True); priority: Mapped[str]=mapped_column(String,default='NORMAL'); status: Mapped[str]=mapped_column(String,default='OPEN'); escalation_reason: Mapped[Optional[str]]=mapped_column(Text,nullable=True); handoff: Mapped[Optional[str]]=mapped_column(Text,nullable=True); resolution_note: Mapped[Optional[str]]=mapped_column(Text,nullable=True); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class Message(Base):
    __tablename__='messages'
    id: Mapped[int]=mapped_column(primary_key=True,autoincrement=True); conversation_id: Mapped[str]=mapped_column(String); role: Mapped[str]=mapped_column(String); content: Mapped[str]=mapped_column(Text); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class Log(Base):
    __tablename__='logs'
    id: Mapped[int]=mapped_column(primary_key=True,autoincrement=True); action: Mapped[str]=mapped_column(String); input_ref: Mapped[str]=mapped_column(String); success: Mapped[bool]=mapped_column(); summary: Mapped[str]=mapped_column(Text); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class Feedback(Base):
    __tablename__='feedback'
    id: Mapped[int]=mapped_column(primary_key=True,autoincrement=True); ticket_id: Mapped[str]=mapped_column(ForeignKey('tickets.id')); rating: Mapped[int]=mapped_column(); comment: Mapped[str]=mapped_column(Text,default='')
Base.metadata.create_all(engine)
def seed():
    with SessionLocal() as s:
        if not s.query(Transaction).count():
            for i,a,st,d in [('1001',500,'SUCCESS','Sample successful payment'),('1002',250,'PENDING','Sample pending payment'),('1003',150,'FAILED','Sample failed payment'),('1004',799,'SUCCESS','Sample successful payment'),('1005',1200,'UNKNOWN','Sample transaction requiring investigation')]: s.add(Transaction(id='TXN'+i,amount=a,status=st,method='UPI',description=d))
        s.commit()
seed()
def db():
    s=SessionLocal()
    try: yield s
    finally: s.close()
def log(s,action,ref,success,summary): s.add(Log(action=action,input_ref=ref,success=success,summary=summary)); s.commit()
def txdict(t): return {'id':t.id,'amount':t.amount,'status':t.status,'method':t.method,'description':t.description,'created_at':t.created_at}
def ticketdict(t): return {'id':t.id,'issue':t.issue,'category':t.category,'transaction_id':t.transaction_id,'priority':t.priority,'status':t.status,'escalation_reason':t.escalation_reason,'handoff':t.handoff,'resolution_note':t.resolution_note,'created_at':t.created_at}
app=FastAPI(title='ResolveMate AI API',version='1.0.0')
app.add_middleware(CORSMiddleware,allow_origins=os.getenv('CORS_ORIGINS','http://localhost:5173').split(','),allow_credentials=True,allow_methods=['*'],allow_headers=['*'])
class ChatIn(BaseModel): message: str=Field(min_length=1,max_length=2000); conversation_id: Optional[str]=None
class TicketIn(BaseModel): issue: str=Field(min_length=3,max_length=2000); transaction_id: Optional[str]=None; priority: str='NORMAL'
class ResolveIn(BaseModel): resolution_note: str=Field(min_length=3,max_length=2000)
class EscalateIn(BaseModel): reason: str=Field(min_length=3,max_length=1000)
class FeedbackIn(BaseModel): rating: int=Field(ge=1,le=5); comment: str=Field(default='',max_length=1000)
class AgentRequestIn(BaseModel): request: str=Field(min_length=1,max_length=2000); client_request_id: Optional[str]=Field(default=None,max_length=100)
def make_ticket(s,issue,txid,category,priority='NORMAL'):
    t=Ticket(id='RMA-'+uuid.uuid4().hex[:8].upper(),issue=issue,transaction_id=txid,category=category,priority=priority); s.add(t); s.commit(); s.refresh(t); log(s,'create_support_ticket',t.id,True,'Ticket created'); return t
def demo_reply(s,msg,ref):
    if not ref:return 'Please share the transaction reference (for example, TXN1002) so I can check the synthetic demo records.',None,None
    t=s.get(Transaction,ref);log(s,'lookup_transaction',ref,bool(t),'Verified record found' if t else 'No matching demo record')
    if not t:return f'I could not verify {ref} in the synthetic demo records. Please check the reference. I have not inferred a transaction status.',None,None
    verified=txdict(t);ticket=None
    if t.status=='PENDING':ticket=make_ticket(s,msg,ref,'pending_payment');reply=f'The synthetic demo record {ref} for {t.amount:.2f} is marked PENDING. I cannot guarantee when it will complete. Follow-up ticket {ticket.id} is open.'
    elif t.status=='FAILED':ticket=make_ticket(s,msg,ref,'failed_payment');reply=f'The synthetic demo record {ref} for {t.amount:.2f} is marked FAILED. This does not confirm a refund. Follow-up ticket {ticket.id} is open.'
    elif t.status=='SUCCESS':reply=f'The synthetic demo record {ref} for {t.amount:.2f} is marked SUCCESS.'
    else:ticket=make_ticket(s,msg,ref,'investigation','HIGH');reply=f'The synthetic demo record {ref} is marked UNKNOWN and needs investigation. Ticket {ticket.id} is open.'
    return reply,verified,ticket
@app.get('/api/health')
def health(): return {'status':'ok','mode':'Demo'}
@app.get('/api/settings/mode')
def mode():
    name,configured,model=configured_provider()
    status=provider_status if configured else 'missing_api_key'
    return {'mode':'AI' if configured else 'Demo','provider':name,'llm_configured':configured,'llm_connected':None,'model':model,'status':status,'error_category':provider_error_category,'error_status_code':provider_http_status,'error_stage':provider_error_stage,'exception_class':provider_exception_class,'response_content_type':provider_response_content_type}
@app.get('/api/transactions')
def transactions(search:str='',status:str='',s:Session=Depends(db)):
    q=s.query(Transaction)
    if search: q=q.filter(Transaction.id.ilike('%'+search[:50]+'%'))
    if status: q=q.filter(Transaction.status==status.upper())
    return [txdict(t) for t in q.order_by(Transaction.created_at.desc()).all()]
@app.get('/api/transactions/{transaction_id}')
def transaction(transaction_id:str,s:Session=Depends(db)):
    t=s.get(Transaction,transaction_id.upper())
    if not t: raise HTTPException(404,'Transaction not found')
    return txdict(t)
@app.post('/api/tickets')
def create_ticket(data:TicketIn,s:Session=Depends(db)):
    return ticketdict(make_ticket(s,data.issue,data.transaction_id,data.issue[:80],'HIGH' if data.priority.upper()=='HIGH' else 'NORMAL'))
@app.get('/api/tickets')
def tickets(status:str='',priority:str='',search:str='',s:Session=Depends(db)):
    q=s.query(Ticket)
    if status:q=q.filter(Ticket.status==status.upper())
    if priority:q=q.filter(Ticket.priority==priority.upper())
    if search:q=q.filter(Ticket.id.ilike('%'+search[:50]+'%')|Ticket.issue.ilike('%'+search[:100]+'%'))
    return [ticketdict(t) for t in q.order_by(Ticket.created_at.desc()).all()]
@app.get('/api/tickets/{ticket_id}')
def get_ticket(ticket_id:str,s:Session=Depends(db)):
    t=s.get(Ticket,ticket_id)
    if not t:raise HTTPException(404,'Ticket not found')
    history=[{'action':l.action,'summary':l.summary,'created_at':l.created_at} for l in s.query(Log).filter(Log.input_ref==ticket_id).all()]
    return {**ticketdict(t),'history':history}
@app.patch('/api/tickets/{ticket_id}')
def resolve(ticket_id:str,data:ResolveIn,s:Session=Depends(db)):
    t=s.get(Ticket,ticket_id)
    if not t:raise HTTPException(404,'Ticket not found')
    t.status='RESOLVED';t.resolution_note=data.resolution_note;s.commit();log(s,'resolve_ticket',ticket_id,True,'Ticket marked resolved');return ticketdict(t)
@app.post('/api/tickets/{ticket_id}/escalate')
def escalate(ticket_id:str,data:EscalateIn,s:Session=Depends(db)):
    t=s.get(Ticket,ticket_id)
    if not t:raise HTTPException(404,'Ticket not found')
    t.status='ESCALATED';t.escalation_reason=data.reason;t.handoff=f'Customer issue: {t.issue}\nCategory: {t.category}\nTransaction: {t.transaction_id or "Not provided"}\nReason: {data.reason}\nNext step: Human review required.';s.commit();log(s,'escalate_to_human',ticket_id,True,'Structured handoff prepared');return ticketdict(t)
@app.post('/api/tickets/{ticket_id}/feedback')
def feedback(ticket_id:str,data:FeedbackIn,s:Session=Depends(db)):
    if not s.get(Ticket,ticket_id):raise HTTPException(404,'Ticket not found')
    s.add(Feedback(ticket_id=ticket_id,rating=data.rating,comment=data.comment));s.commit();return {'saved':True}
@app.get('/api/activity-logs')
def logs(limit:int=Query(100,le=500),s:Session=Depends(db)):
    return [{'action':x.action,'input_ref':x.input_ref,'success':x.success,'summary':x.summary,'created_at':x.created_at} for x in s.query(Log).order_by(Log.created_at.desc()).limit(limit).all()]
@app.get('/api/analytics')
def analytics(s:Session=Depends(db)):
    return {'transactions_by_status':{k:v for k,v in s.query(Transaction.status,func.count()).group_by(Transaction.status).all()},'tickets_by_status':{k:v for k,v in s.query(Ticket.status,func.count()).group_by(Ticket.status).all()},'tickets_by_category':{k:v for k,v in s.query(Ticket.category,func.count()).group_by(Ticket.category).all()},'total_tickets':s.query(Ticket).count(),'escalations':s.query(Ticket).filter(Ticket.status=='ESCALATED').count(),'resolution_rate': round(s.query(Ticket).filter(Ticket.status=='RESOLVED').count()/max(s.query(Ticket).count(),1),3)}
@app.post('/api/agents/execute')
def execute_agents(data:AgentRequestIn,s:Session=Depends(db)):
    from agents.orchestrator import orchestrator, EXECUTIONS
    key=data.client_request_id.strip() if data.client_request_id else None
    if key:
        existing=next((x for x in EXECUTIONS.values() if x.get('client_request_id')==key),None)
        if existing:return existing
    result=orchestrator.run(data.request.strip(),s)
    result['client_request_id']=key
    return result
@app.get('/api/agents/executions/{execution_id}')
def agent_execution(execution_id:str):
    from agents.orchestrator import EXECUTIONS
    result=EXECUTIONS.get(execution_id)
    if not result: raise HTTPException(404,'Agent execution not found')
    return result
@app.get('/api/agents/executions')
def agent_executions():
    from agents.orchestrator import EXECUTIONS
    return list(reversed(list(EXECUTIONS.values())))
@app.post('/api/chat')
def chat(data:ChatIn,s:Session=Depends(db)):
    global provider_status, provider_error_category, provider_http_status
    global provider_error_stage, provider_exception_class, provider_response_content_type
    msg=data.message.strip(); cid=data.conversation_id or 'CONV-'+uuid.uuid4().hex[:10]
    provider_name,_,_=configured_provider()
    chat_provider_diagnostics={
        'provider':provider_name,
        'status':'not_attempted',
        'error_category':None,
        'error_stage':None,
        'exception_class':None,
        'error_status_code':None,
        'response_content_type':None,
    }
    s.add(Message(conversation_id=cid,role='customer',content=msg)); low=msg.lower()
    category='payment_status'; refmatch=re.search(r'TXN\d+',msg,re.I); ref=refmatch.group(0).upper() if refmatch else None
    stages=[]
    def stage(name,status):stages.append({'stage':name,'status':status})
    stage('Understand request','COMPLETED'); stage('Identify issue category','COMPLETED')
    risk=any(w in low for w in ['refund','transfer money','upi pin','otp','fraud','change bank'])
    human=any(w in low for w in ['human','agent','person'])
    if 'pending' in low and not ref: category='pending_payment'
    elif 'failed' in low: category='failed_payment'
    elif risk: category='sensitive_financial_action'
    elif human: category='human_assistance'
    stage('Gather required reference information','COMPLETED' if ref or risk or human else 'NEEDS_HUMAN_REVIEW')
    reply=''; ticket=None; verified=None
    response_mode='Demo'
    if risk or human:
        ticket=make_ticket(s,msg,ref,category,'HIGH' if risk else 'NORMAL'); reason='Sensitive financial request requires human review' if risk else 'Customer requested human assistance'
        ticket.status='ESCALATED';ticket.escalation_reason=reason;ticket.handoff=f'Customer question: {msg}\nCategory: {category}\nTransaction: {ref or "Not provided"}\nVerified information: None\nTools: Ticket creation\nReason: {reason}\nNext step: Human review required.';s.commit()
        log(s,'escalate_to_human',ticket.id,True,'Human review handoff prepared');reply=f'I can’t perform that action in this prototype. A human must review this case. Ticket {ticket.id} has been prepared for review; no support employee has been contacted.' if risk else f'I’ve prepared a human review case. Ticket {ticket.id}. This prototype has not contacted a support employee.'
    elif ref:
        stage('Call approved transaction lookup','IN_PROGRESS')
        reply,verified,ticket=demo_reply(s,msg,ref)
        stage('Inspect verified result','COMPLETED');stage('Decide next step','COMPLETED');stage('Execute permitted action','COMPLETED' if ticket else 'COMPLETED');stage('Verify action result','COMPLETED');stage('Respond to customer','COMPLETED');stage('Close or escalate case','COMPLETED' if ticket else 'WAITING')
    else:
        # Ordinary support questions may use the model. Never send database
        # records or stored conversation history; only this bounded message.
        chat_provider_diagnostics['status']='attempted'
        try:
            generated=generate_ai_reply(msg)
            if generated and generated.strip():
                reply=generated.strip()[:4000]
                response_mode='AI'
                chat_provider_diagnostics['status']='available'
                provider_status='available'
                provider_error_category=None
                provider_http_status=None
                provider_error_stage=None
                provider_exception_class=None
                provider_response_content_type=None
            else:
                raise RuntimeError('OpenAI returned an empty response')
        except Exception as error:
            # Do not log provider exception details: they may contain sensitive data.
            _,configured,_=configured_provider()
            provider_status='unavailable' if configured else 'missing_api_key'
            chat_provider_diagnostics['status']=provider_status
            if configured:
                provider_error_category,provider_http_status=provider_error_details(error)
                chat_provider_diagnostics['error_category']=provider_error_category
                chat_provider_diagnostics['error_status_code']=provider_http_status
                if AI_PROVIDER == 'sarvam':
                    provider_error_stage=getattr(error,'safe_stage','sending_request')
                    provider_exception_class=''.join(c for c in type(error).__name__ if c.isalnum())[:80]
                    raw_content_type=getattr(error,'safe_content_type',None)
                    mime=raw_content_type.split(';',1)[0].strip().lower() if isinstance(raw_content_type,str) else ''
                    provider_response_content_type=mime if re.fullmatch(r'[a-z0-9.+-]+/[a-z0-9.+-]+',mime) else None
                    chat_provider_diagnostics['error_stage']=provider_error_stage
                    chat_provider_diagnostics['exception_class']=provider_exception_class
                    chat_provider_diagnostics['response_content_type']=provider_response_content_type
            else:
                provider_error_category='missing_key'
                provider_http_status=None
                provider_error_stage=None
                provider_exception_class=None
                provider_response_content_type=None
                chat_provider_diagnostics['error_category']='missing_key'
            detail=f'Provider {provider_error_category}'
            if provider_http_status is not None:
                detail+=f' (HTTP {provider_http_status})'
            if provider_error_stage:
                detail+=f' at {provider_error_stage}; {provider_exception_class or "Exception"}'
                if provider_response_content_type:
                    detail+=f'; content-type {provider_response_content_type}'
            log(s,f'{AI_PROVIDER}_chat',cid,False,f'{detail}; deterministic fallback used')
            reply,verified,ticket=demo_reply(s,msg,ref)
    if len(stages)<10:
        for name in ['Call approved tool','Inspect tool result','Decide next step','Execute permitted action','Verify action result','Respond to customer','Close or escalate case']:
            if not any(x['stage']==name for x in stages):stage(name,'COMPLETED' if ticket else 'WAITING')
    s.add(Message(conversation_id=cid,role='assistant',content=reply));s.commit()
    return {'conversation_id':cid,'mode':response_mode,'category':category,'transaction':verified,'ticket':ticketdict(ticket) if ticket else None,'reply':reply,'stages':stages,'provider_diagnostics':chat_provider_diagnostics}
