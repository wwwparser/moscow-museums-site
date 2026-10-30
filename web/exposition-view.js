'use strict';
window.ExpositionView=(()=>{
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const safe=u=>{try{const x=new URL(u);return ['https:','http:'].includes(x.protocol)?x.href:'';}catch{return '';}};
  function render(m,detail=false){
    const note=m.exposition;
    if(!note?.facts?.length)return `<p class="exposition-missing">Описание экспозиции пока не подтверждено.</p>`;
    const urls=[...new Set(note.facts.map(f=>safe(f.source)).filter(Boolean))];
    const date=new Date(note.checked_at).toLocaleDateString('ru-RU');
    return `<section class="exposition-note ${detail?'exposition-detail':''}" aria-label="Что посмотреть в музее"><h4>Что посмотреть</h4><p>${note.facts.map(f=>esc(f.text)).join(' ')}</p><div class="exposition-sources">${urls.map((u,i)=>`<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${urls.length===1?'Об экспозиции':'Источник '+(i+1)} ↗</a>`).join('')}<span>Проверено ${esc(date)}</span></div>${note.status==='stale'?'<p class="exposition-warning">Показано прежнее описание: источник изменился или недоступен, сведения требуют повторной проверки.</p>':''}</section>`;
  }
  return {render};
})();
