"""Existing Hermes Telegram adapter, gated by the durable outbox at the HTTP boundary."""
import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
import sys
import hashlib
import sqlite3
import time


def claim_wire(database,grant,*,clock=time.time):
    """One durable wire attempt, including across child-process restarts."""
    c=sqlite3.connect('file:'+Path(database).resolve().as_posix()+'?mode=rw',uri=True)
    try:
        c.execute('BEGIN IMMEDIATE')
        if type(grant.get('expires')) not in (int,float) or not clock()<grant['expires']:
            raise PermissionError('DELIVERY_GRANT_EXPIRED')
        nid=grant['notification_id']
        row=c.execute('SELECT state,attempts,task_id FROM automation_outbox WHERE id=?',(nid,)).fetchone()
        permission=c.execute('SELECT value FROM metadata WHERE key=?',('delivery_permission:'+nid,)).fetchone()
        if row!=('SENDING',grant.get('outbox_attempt',1),grant['task_id']) or not permission or json.loads(permission[0])!={**grant,'status':'CLOSED'}:
            raise PermissionError('OUTBOX_INTENT_REQUIRED')
        c.execute('INSERT INTO metadata VALUES(?,?)',('telegram_wire:'+nid,json.dumps({'requests':1})))
        c.commit()
    finally:c.close()


def response_excerpt(status,body):
    """Allowlist API evidence; never retain raw responses, URLs or headers."""
    excerpt={}
    if type(status) is int:excerpt['http_status']=status
    if not isinstance(body,dict):return excerpt
    if type(body.get('ok')) is bool:excerpt['ok']=body['ok']
    result=body.get('result')
    if not isinstance(result,dict):return excerpt
    safe={}
    for key in ('message_id','date'):
        if type(result.get(key)) is int:safe[key]=result[key]
    for group,fields in (('from',('id','username')),('chat',('id','type')),('document',('file_name','file_size'))):
        value=result.get(group)
        if not isinstance(value,dict):continue
        selected={}
        for key in fields:
            item=value.get(key)
            if key in ('id','file_size'):
                if type(item) is int:selected[key]=item
            elif isinstance(item,str) and len(item)<=255:
                if key=='username' and (not item.isascii() or not item.replace('_','').isalnum()):continue
                if key=='type' and item not in ('private','group','supergroup','channel'):continue
                if key=='file_name' and any(c in item for c in ('/', '\\', ':','\n','\r')):continue
                selected[key]=item
        if selected:safe[group]=selected
    if safe:excerpt['result']=safe
    return excerpt


def delivery_result(status,body,chat,requests,artifact_hash):
    excerpt=response_excerpt(status,body)
    result={'status':'UNKNOWN' if requests else 'NOT_SENT','requests':requests,'response_excerpt':excerpt}
    message=excerpt.get('result',{})
    if excerpt.get('ok') is True and message.get('message_id') and str(message.get('chat',{}).get('id'))==chat:
        result.update(accepted=True,service_id=str(message['message_id']),chat_id=chat,artifact_sha256=artifact_hash)
        result.pop('status')
    elif excerpt.get('ok') is False:
        result.update(rejected=True);result.pop('status')
    return result


def check_owner(home_chat, allowed_users, chat, expected_username):
    allowed=[x.strip() for x in allowed_users.split(',')]
    if not home_chat.isdigit() or home_chat not in allowed:
        return {'status':'NOT_SENT','reason':'OWNER_BINDING_MISSING','requests':0}
    if (chat.get('type')!='private' or str(chat.get('id'))!=home_chat or
            (chat.get('username') or '').casefold()!=expected_username.casefold()):
        return {'status':'NOT_SENT','reason':'OWNER_CHAT_NOT_CONFIRMED','requests':0}
    return {'status':'VERIFIED','requests':0}


async def probe(home, expected_username,send_spec=None):
    requests=0
    sys.path.insert(0,str(home/'hermes-agent'))
    os.environ['HERMES_HOME']=str(home)  # this subprocess only
    logging.disable(logging.CRITICAL)
    from hermes_cli.config import load_env
    from agent.secret_scope import get_secret
    config=load_env()
    for name in ('TELEGRAM_BOT_TOKEN','TELEGRAM_HOME_CHANNEL','TELEGRAM_ALLOWED_USERS'):
        if name in config: os.environ[name]=config[name]
    token=get_secret('TELEGRAM_BOT_TOKEN')
    chat=os.environ.get('TELEGRAM_HOME_CHANNEL','')
    allowed=os.environ.get('TELEGRAM_ALLOWED_USERS','')
    if not token or not chat.isdigit() or chat not in [x.strip() for x in allowed.split(',')]:
        return {'status':'NOT_SENT','reason':'OWNER_BINDING_MISSING','requests':0}
    try:
        from telegram import Bot
        async with Bot(token=token) as bot:
            target=await bot.get_chat(chat)
        result=check_owner(chat,allowed,{'id':target.id,'type':target.type,'username':target.username},expected_username)
        if send_spec and result['status']=='VERIFIED':
            grant=send_spec['grant']
            if grant['chat_id']!=chat or grant['username']!=expected_username:
                return {'status':'NOT_SENT','reason':'GRANT_OWNER_MISMATCH','requests':0}
            artifact=Path(grant['artifact'])
            if hashlib.sha256(artifact.read_bytes()).hexdigest()!=grant['sha256']:
                return {'status':'NOT_SENT','reason':'ARTIFACT_CHANGED','requests':0}
            from telegram.request import HTTPXRequest
            import httpx
            original=HTTPXRequest.do_request
            original_init=HTTPXRequest.__init__
            def no_retries(self,*args,**kwargs):
                options=dict(kwargs.get('httpx_kwargs') or {})
                options.update(transport=httpx.AsyncHTTPTransport(retries=0,proxy=kwargs.get('proxy')),follow_redirects=False)
                kwargs['httpx_kwargs']=options
                original_init(self,*args,**kwargs)
            response=None; http_status=None
            async def guarded(self,url,method,*args,**kwargs):
                nonlocal requests,response,http_status
                endpoint=url.rsplit('/',1)[-1]
                if endpoint=='getMe':return await original(self,url,method,*args,**kwargs)
                if endpoint!='sendDocument' or requests:raise PermissionError('SEND_NOT_ALLOWED')
                data=kwargs['request_data']
                if str(data.parameters.get('chat_id'))!=chat:raise PermissionError('RECIPIENT_CHANGED')
                files=list(data.multipart_data.values())
                if len(files)!=1 or not isinstance(files[0][1],bytes) or hashlib.sha256(files[0][1]).hexdigest()!=grant['sha256']:
                    raise PermissionError('UPLOAD_CHANGED')
                claim_wire(send_spec['database'],grant)
                requests=1
                reply=await original(self,url,method,*args,**kwargs)
                http_status=reply[0]
                try:response=json.loads(reply[1])
                except Exception:pass
                return reply
            HTTPXRequest.do_request=guarded
            HTTPXRequest.__init__=no_retries
            try:
                from tools import send_message_tool as sender
                caption=('Сохранённая памятка по FLOP Testnet по материалам предыдущего запуска. '
                         'Сейчас выполнена только доставка, не новая проверка FLOP. '
                         'Участие в testnet и награда этим не подтверждаются.')
                # Installed Hermes omits .html from captionable documents. Scope this
                # compatibility adjustment to this isolated child, never gateway files.
                extensions=sender._CAPTIONABLE_EXTS
                sender._CAPTIONABLE_EXTS=extensions|{'.html'}
                try:await sender._send_telegram(token,chat,caption,media_files=[(str(artifact),False)],force_document=True)
                finally:sender._CAPTIONABLE_EXTS=extensions
            except Exception:pass
            finally:
                HTTPXRequest.do_request=original
                HTTPXRequest.__init__=original_init
            return delivery_result(http_status,response,chat,requests,grant['sha256'])
        return {**result,'chat_id':str(target.id),'type':target.type,'username':target.username}
    except Exception:
        return {'status':'UNKNOWN' if requests else 'NOT_SENT','reason':'CONNECTION_CHECK_FAILED','requests':requests}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--home',type=Path,required=True)
    parser.add_argument('--expected-username',required=True)
    parser.add_argument('--outbox-send',action='store_true',help='Internal child: requires durable outbox intent and one-shot wire claim')
    args=parser.parse_args()
    spec=json.load(sys.stdin) if args.outbox_send else None
    print(json.dumps(asyncio.run(probe(args.home,args.expected_username,spec))))
