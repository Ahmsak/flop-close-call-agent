"""One exact existing outbox notice through the installed Hermes adapter; no LLM."""
import argparse
import json
from pathlib import Path
import subprocess

from durable import Durable,Policy
from ops import Store

ROOT=Path(__file__).resolve().parent


class HermesTelegram:
    environment='telegram'
    def __init__(self,python,home,database,grant):
        self.python,self.home,self.database=python,home,database
        self.chat_id,self.username=grant['chat_id'],grant['username']

    def send(self,nid,destination,payload):
        command=[str(self.python),str(ROOT/'telegram_bridge.py'),'--home',str(self.home),
                 '--expected-username',self.username,'--outbox-send']
        result=subprocess.run(command,input=json.dumps({'database':str(self.database),'grant':payload['delivery_grant']}),
                              capture_output=True,text=True,encoding='utf-8',timeout=90)
        # Never forward child stderr: it may contain third-party diagnostics.
        if result.returncode:return None
        try:return json.loads(result.stdout)
        except ValueError:return None


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--grant',type=Path,required=True)
    parser.add_argument('--hermes-python',type=Path,required=True);parser.add_argument('--hermes-home',type=Path,required=True)
    args=parser.parse_args();grant=json.loads(args.grant.read_text(encoding='utf-8'))
    store=Store(ROOT/'runtime/state.sqlite')
    try:
        adapter=HermesTelegram(args.hermes_python,args.hermes_home,ROOT/'runtime/state.sqlite',grant)
        result=Durable(store).deliver(grant['notification_id'],adapter,Policy(ROOT/'config.json'),grant=grant)
        print(json.dumps({k:result[k] for k in ('id','task_id','state','attempts','receipt','reason')}))
    finally:
        args.grant.write_text(json.dumps({**grant,'status':'CLOSED'},indent=2),encoding='utf-8')
        store.close()


if __name__=='__main__':main()
