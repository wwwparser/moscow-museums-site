'use strict';
fetch('data/update-report.json',{cache:'no-cache'}).then(r=>{if(!r.ok)throw Error('No report');return r.json();}).then(report=>{
  const root=document.querySelector('#update-health');
  const date=new Date(report.finished_at).toLocaleString('ru-RU',{timeZone:'Europe/Moscow'});
  const intro=document.createElement('p');intro.textContent='Завершено '+date+' мск. '+(report.status==='partial'?'Часть источников недоступна или требует проверки.':'Проверки завершены.');root.replaceChildren(intro);
  const list=document.createElement('ul');
  for(const [key,title] of [['sites','Сайты и контакты'],['events','Афиши'],['admission','Тарифы и льготы'],['telegram','Telegram']]){
    const row=report[key];const item=document.createElement('li');item.textContent=title+': проверено сегодня '+row.checked_today+' из '+row.checked+'; с ошибками '+row.with_errors+'; сохранены прежние данные у '+row.stale+'.';list.append(item);
  }
  root.append(list);
  if(report.pending_luna){const pending=document.createElement('p');pending.textContent='Ожидают разбора внутренней Luna: '+report.pending_luna+' источников. Непроверенные сведения не выдаются за обновлённые.';root.append(pending);}
  const link=document.createElement('a');link.href='data/update-report.json';link.textContent='Скачать подробный отчёт JSON ↗';link.download='update-report.json';root.append(link);
}).catch(()=>{const root=document.querySelector('#update-health');if(root)root.textContent='Отчёт появится после следующего полного запуска обновления.';});
