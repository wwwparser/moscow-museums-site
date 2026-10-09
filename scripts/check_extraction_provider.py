"""Copy only the needed keys into the ignored local file and report availability without secrets."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import os
import requests
from src.services.llm_client import load_env,extract_json,ROOT

def main():
    source=Path.home()/'.claude/secrets/api-keys.env'
    load_env(source)
    target=ROOT/'.env'
    existing=target.read_text(encoding='utf8') if target.exists() else ''
    names=['DEEPSEEK_API_KEY','DAHL_API_KEY','IKHDEV_API_KEY']
    with target.open('a',encoding='utf8') as f:
        for name in names:
            if os.getenv(name) and name+'=' not in existing:f.write(name+'='+os.environ[name]+'\n')
    if os.getenv('DEEPSEEK_API_KEY'):
        r=requests.get('https://api.deepseek.com/user/balance',headers={'Authorization':'Bearer '+os.environ['DEEPSEEK_API_KEY']},timeout=20)
        if r.status_code==200:
            obj=r.json();print('DeepSeek available:',obj.get('is_available'),'balances:',obj.get('balance_infos',[]),flush=True)
            if obj.get('is_available'):return
        else:print('DeepSeek balance check HTTP',r.status_code,flush=True)
    for provider,key in [('dahl','DAHL_API_KEY'),('ikhdev','IKHDEV_API_KEY')]:
        if not os.getenv(key):continue
        try:
            obj=extract_json('Return JSON {"category":"adults","price_rub":500} from: Adult museum admission: 500 rubles.',provider,200)
            print(provider,'probe:',obj,flush=True)
            if obj.get('price_rub')==500:break
        except Exception as exc:print(provider,str(exc),flush=True)

if __name__=='__main__':main()
