/* explorable-plan kit: generic parts. Page-specific interactions go in a <script> inside the
   content (build.py moves it after this one) and use window.Plan. The strings this file shows
   come from window.PLAN_UI, written by build.py for the page language.
   Without JavaScript the page stays readable: tabs and disclosures show everything. */
(function(){
'use strict';
const UI=window.PLAN_UI||{};
const $=(s,r)=>(r||document).querySelector(s);
const $$=(s,r)=>[...(r||document).querySelectorAll(s)];
const el=(tag,cls,txt)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(txt!=null)e.textContent=txt;return e;};
const fmt=(n,d)=>n.toFixed(d==null?2:d).replace('.',UI.decimal||'.');
const dateLong=s=>{const[y,m,d]=s.split('-');return (UI.date_fmt||'{d} {m} {y}').replace('{d}',+d).replace('{m}',(UI.months||[])[+m-1]||m).replace('{y}',y);};

/* WAI-ARIA tabs: arrows, Home, End. root = element with a direct child [role=tablist]. */
function initTabs(root,onSelect){
  const list=root.querySelector(':scope > [role=tablist]');
  const tabs=[...list.querySelectorAll('[role=tab]')];
  const panels=tabs.map(t=>document.getElementById(t.getAttribute('aria-controls')));
  list.hidden=false;
  function select(i,focus){
    tabs.forEach((t,j)=>{const on=i===j;t.setAttribute('aria-selected',on?'true':'false');t.tabIndex=on?0:-1;panels[j].hidden=!on;});
    if(focus)tabs[i].focus();
    if(onSelect)onSelect(i,tabs.length);
  }
  tabs.forEach((t,i)=>{
    t.type='button';
    t.addEventListener('click',()=>select(i));
    t.addEventListener('keydown',e=>{
      let k=null;
      if(e.key==='ArrowRight')k=(i+1)%tabs.length;
      else if(e.key==='ArrowLeft')k=(i-1+tabs.length)%tabs.length;
      else if(e.key==='Home')k=0;
      else if(e.key==='End')k=tabs.length-1;
      if(k!==null){e.preventDefault();select(k,true);}
    });
  });
  select(0);
  return {select,count:tabs.length,current:()=>tabs.findIndex(t=>t.getAttribute('aria-selected')==='true')};
}

/* steps: tabs plus [data-step=prev|next] buttons inside .step-ctrl */
function initSteps(root){
  const prev=$('[data-step=prev]',root),next=$('[data-step=next]',root);
  const t=initTabs(root,(i,n)=>{if(prev)prev.disabled=i===0;if(next)next.disabled=i===n-1;});
  if(prev)prev.addEventListener('click',()=>t.select(Math.max(0,t.current()-1)));
  if(next)next.addEventListener('click',()=>t.select(Math.min(t.count-1,t.current()+1)));
  return t;
}

/* disclosure: in a .disc-group the first is open and the others closed; data-start="closed" closes all */
function initDisc(g){
  const allClosed=g.dataset.start==='closed';
  $$('.disc-btn',g).forEach((b,i)=>{
    const body=document.getElementById(b.getAttribute('aria-controls'));
    const set=open=>{b.setAttribute('aria-expanded',open?'true':'false');body.hidden=!open;};
    set(!allClosed&&i===0);
    b.addEventListener('click',()=>set(b.getAttribute('aria-expanded')!=='true'));
  });
}

/* decisions: form.decisions[data-intro]; every .decision[data-question] becomes a line "N) question: answer".
   Radio and checkbox give the text of their label (or data-text); number, date, text and textarea give
   their value, with optional data-prefix and data-suffix. */
function initDecisions(form){
  const out=$('.dec-out',form),btn=$('.dec-copy',form),msg=$('.dec-copied',form);
  if(!out)return;
  function answer(d){
    const parts=[];
    $$('input,select,textarea',d).forEach(x=>{
      if(x.readOnly)return;
      if(x.type==='radio'||x.type==='checkbox'){
        if(x.checked)parts.push(x.dataset.text||(x.closest('label')||{}).textContent.trim());
      }else if(x.value.trim()){
        const pre=x.dataset.prefix?x.dataset.prefix+' ':'',suf=x.dataset.suffix?' '+x.dataset.suffix:'';
        parts.push(pre+(x.type==='date'?dateLong(x.value):x.value.trim())+suf);
      }
    });
    return parts.length?parts.join(', '):(UI.to_decide||'to be decided.');
  }
  function compose(){
    const lines=$$('.decision[data-question]',form).map((d,i)=>(i+1)+') '+d.dataset.question+': '+answer(d));
    out.value=(form.dataset.intro?form.dataset.intro+'\n':'')+lines.join('\n');
  }
  $$('input,select,textarea',form).forEach(x=>{if(x!==out){x.addEventListener('input',compose);x.addEventListener('change',compose);}});
  form.addEventListener('submit',e=>e.preventDefault());
  compose();
  if(btn)btn.addEventListener('click',async()=>{
    try{await navigator.clipboard.writeText(out.value);if(msg)msg.textContent=UI.copied||'Copied.';}
    catch(e){out.focus();out.select();if(msg)msg.textContent=UI.selected||'Selected: copy it with Ctrl+C or Cmd+C.';}
  });
  return compose;
}

/* auto-init; a tab group with data-manual is initialised by the page with Plan.initTabs */
$$('.tabs').forEach(r=>{if(r.dataset.manual==null)(r.classList.contains('steps')?initSteps:initTabs)(r);});
$$('.disc-group').forEach(initDisc);
$$('form.decisions').forEach(initDecisions);

/* print: everything visible, then back to the state before (a cancelled preview included);
   the page can listen to plan:print and plan:afterprint for the rest */
let beforePrint=null;
window.addEventListener('beforeprint',()=>{
  beforePrint=$$('[role=tabpanel],.disc-body').map(p=>[p,p.hidden]);
  beforePrint.forEach(([p])=>p.hidden=false);
  window.dispatchEvent(new Event('plan:print'));
});
window.addEventListener('afterprint',()=>{
  if(beforePrint)beforePrint.forEach(([p,h])=>p.hidden=h);
  beforePrint=null;
  window.dispatchEvent(new Event('plan:afterprint'));
});

window.Plan={$,$$,el,fmt,dateLong,ui:UI,initTabs,initSteps,initDisc,initDecisions};
})();
