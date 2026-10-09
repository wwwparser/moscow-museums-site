'use strict';
window.TelegramFeed = (() => {
  const q = selector => document.querySelector(selector);
  const html = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const url = value => { try {const u=new URL(value);return ['https:','http:'].includes(u.protocol)?u.href:'';}catch{return '';} };
  const handle = channel => '@'+channel.split('/').pop();
  const date = value => new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'long',year:'numeric',timeZone:'Europe/Moscow'}).format(new Date(value));
  const day = value => new Intl.DateTimeFormat('en-CA',{year:'numeric',month:'2-digit',day:'2-digit',timeZone:'Europe/Moscow'}).format(new Date(value));
  const time = value => new Intl.DateTimeFormat('ru-RU',{hour:'2-digit',minute:'2-digit',timeZone:'Europe/Moscow'}).format(new Date(value));
  const storageKey='museum-route:saved-posts';
  let saved=new Set();
  try {const stored=JSON.parse(localStorage.getItem(storageKey)||'[]');if(Array.isArray(stored))saved=new Set(stored.filter(s=>typeof s==='string'));}catch{}
  let bundle, museums=[], limit=12, ready=false, onlySaved=false;
  const expanded=new Set();
  const channelName = c => {
    const names=[...new Set(c.museum_ids.map(id=>bundle.museums.find(m=>m.id===id)?.name).filter(Boolean))];
    return names[0]||handle(c.url);
  };
  function channels() {const ids=new Set(museums.map(m=>m.id));return bundle.channels.filter(c=>c.museum_ids.some(id=>ids.has(id)));}
  function init(data) {
    bundle=data;if(ready)return;ready=true;
    q('#feed-updated').textContent='Копия от '+date(data.meta.built_at);
    const refresh=()=>{limit=12;render();};
    q('#post-search').addEventListener('input',refresh);
    ['post-period','post-sort','channel'].forEach(id=>q('#'+id).addEventListener('change',refresh));
    q('#channel-search').addEventListener('input',renderChannels);
    q('#saved-posts').onclick=()=>{onlySaved=!onlySaved;refresh();};
    q('#reset-feed').onclick=()=>{q('#post-search').value='';q('#channel-search').value='';q('#channel').value='';q('#post-period').value='all';q('#post-sort').value='new';onlySaved=false;refresh();};
    q('#more-posts').onclick=()=>{const previous=limit;limit+=12;render();q('#post-list').querySelectorAll('.post')[previous]?.focus({preventScroll:true});};
    q('#feed-top').onclick=()=>q('#telegram').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});
    q('#feed-channels').onclick=e=>{const button=e.target.closest('[data-feed-channel]');if(button){q('#channel').value=button.dataset.feedChannel;refresh();}};
    q('#post-list').onclick=e=>{
      const expand=e.target.closest('[data-expand-post]');
      if(expand){const id=expand.dataset.expandPost,body=document.getElementById(expand.getAttribute('aria-controls'));const open=!expanded.has(id);open?expanded.add(id):expanded.delete(id);body.classList.toggle('is-collapsed',!open);expand.setAttribute('aria-expanded',String(open));expand.textContent=open?'Свернуть текст ↑':'Читать целиком ↓';}
      const save=e.target.closest('[data-save-post]');
      if(save){const id=save.dataset.savePost;saved.has(id)?saved.delete(id):saved.add(id);try{localStorage.setItem(storageKey,JSON.stringify([...saved]));}catch{}if(onlySaved)render();else{save.setAttribute('aria-pressed',String(saved.has(id)));save.textContent=saved.has(id)?'Сохранено ✓':'Сохранить';renderSavedCount();}}
    };
  }
  function renderSavedCount(){q('#saved-count').textContent=saved.size;q('#saved-posts').setAttribute('aria-pressed',String(onlySaved));}
  function renderChannels(){
    const available=channels().filter(c=>c.posts.length).sort((a,b)=>channelName(a).localeCompare(channelName(b),'ru'));
    const selected=q('#channel').value,search=q('#channel-search').value.trim().toLocaleLowerCase('ru');
    const matches=available.filter(c=>(channelName(c)+' '+handle(c.url)).toLocaleLowerCase('ru').includes(search));
    const count=available.reduce((sum,c)=>sum+c.posts.length,0);
    q('#feed-channels').innerHTML=`<button data-feed-channel="" class="feed-channel ${!selected?'active':''}" aria-pressed="${!selected}"><span>Все каналы<small>${available.length} с публикациями</small></span><b>${count}</b></button>`+matches.map(c=>`<button data-feed-channel="${html(c.url)}" class="feed-channel ${selected===c.url?'active':''}" aria-pressed="${selected===c.url}"><span>${html(channelName(c))}<small>${html(handle(c.url))}</small></span><b>${c.posts.length}</b></button>`).join('')+(!matches.length?'<p class="muted">Каналы не найдены.</p>':'');
    const unavailable=channels().filter(c=>!c.posts.length);
    q('#channel-errors-summary').textContent='Без доступных постов · '+unavailable.length;
    q('#channel-errors').innerHTML=unavailable.map(c=>`<a href="${html(url(c.url))}" target="_blank" rel="noopener noreferrer">${html(handle(c.url))} ↗</a>`).join('');
  }
  function render(data,visible) {
    if(data){init(data);museums=visible;}
    if(!bundle)return;
    const available=channels().filter(c=>c.posts.length),selected=q('#channel').value;
    q('#channel').innerHTML='<option value="">Все каналы</option>'+available.sort((a,b)=>channelName(a).localeCompare(channelName(b),'ru')).map(c=>`<option value="${html(c.url)}">${html(channelName(c))} · ${html(handle(c.url))}</option>`).join('');
    q('#channel').value=available.some(c=>c.url===selected)?selected:'';
    renderChannels();renderSavedCount();
    const search=q('#post-search').value.trim().toLocaleLowerCase('ru'),period=q('#post-period').value;
    const cutoff=Date.now()-(period==='week'?7:30)*86400000;
    const byChannel=new Map(available.map(c=>[c.url,c]));
    const posts=[...new Map(available.flatMap(c=>c.posts).map(p=>[p.id,p])).values()].filter(p=>(!q('#channel').value||p.channel===q('#channel').value)&&(!onlySaved||saved.has(p.id))&&(!search||(p.text+' '+handle(p.channel)+' '+channelName(byChannel.get(p.channel))).toLocaleLowerCase('ru').includes(search))&&(period==='all'||new Date(p.date).getTime()>=cutoff));
    posts.sort((a,b)=>(q('#post-sort').value==='old'?1:-1)*(new Date(a.date)-new Date(b.date))||a.id.localeCompare(b.id));
    const shown=posts.slice(0,limit);let lastDay='';
    q('#post-list').innerHTML=shown.map((p,index)=>{
      const c=byChannel.get(p.channel),name=channelName(c),key=day(p.date),bodyId='post-body-'+index;
      const divider=key!==lastDay?`<h3 class="feed-day"><time datetime="${html(p.date)}">${html(date(p.date))}</time></h3>`:'';lastDay=key;
      const long=p.text.length>650||p.text.split('\n').length>9,open=expanded.has(p.id);
      return divider+`<article class="post" tabindex="-1"><header class="post-header"><span class="channel-avatar" aria-hidden="true">${html(name.replace(/[^\p{L}\p{N}]/gu,'').slice(0,1)||'М')}</span><div class="post-author"><h3><a href="${html(url(p.channel))}" target="_blank" rel="noopener noreferrer">${html(name)}</a></h3><span>${html(handle(p.channel))}</span></div><time datetime="${html(p.date)}" title="${html(date(p.date))} · ${html(time(p.date))} мск">${html(time(p.date))}<small>мск</small></time></header><div id="${bodyId}" class="post-text ${long&&!open?'is-collapsed':''}">${html(p.text)}</div>${long?`<button class="post-expand quiet" data-expand-post="${html(p.id)}" aria-expanded="${open}" aria-controls="${bodyId}">${open?'Свернуть текст ↑':'Читать целиком ↓'}</button>`:''}<div class="post-footer"><a href="${html(url(p.url))}" target="_blank" rel="noopener noreferrer">Открыть в Telegram ↗</a><button class="quiet" data-save-post="${html(p.id)}" aria-pressed="${saved.has(p.id)}">${saved.has(p.id)?'Сохранено ✓':'Сохранить'}</button></div></article>`;
    }).join('')||'<div class="empty"><h3>Публикации не найдены</h3><p>Попробуйте другой запрос, канал или период. Кнопка «Сбросить ленту» очищает настройки этой ленты.</p></div>';
    q('#feed-count').textContent=`Показано ${shown.length} из ${posts.length} публикаций · ${new Set(posts.map(p=>p.channel)).size} каналов`;
    q('#more-posts').hidden=shown.length>=posts.length;
    q('#more-posts').textContent=`Ещё ${Math.min(12,posts.length-shown.length)} публикаций`;
  }
  return {render,resetPage:()=>{limit=12;}};
})();
