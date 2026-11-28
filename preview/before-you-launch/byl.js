/* Before You Launch (private preview): theme control and async readings. Each card is replaced on its own;
   a failed request turns remaining skeletons into Unavailable cards. Nothing is filled in. */
(function(){
  var root=document.documentElement,btns=document.querySelectorAll('.th button');
  function cur(){try{return localStorage.getItem('coastalBrief.theme')||'auto'}catch(e){return 'auto'}}
  function apply(t){try{if(t==='auto')localStorage.removeItem('coastalBrief.theme');else localStorage.setItem('coastalBrief.theme',t)}catch(e){}
    var dark=t==='dark'||(t==='auto'&&matchMedia('(prefers-color-scheme: dark)').matches);root.classList.toggle('dark',dark);
    btns.forEach(function(b){b.setAttribute('aria-pressed',String(b.dataset.t===t))})}
  btns.forEach(function(b){b.addEventListener('click',function(){apply(b.dataset.t)})});apply(cur());
  var bar=document.querySelector('.bar');function pad(){if(bar)root.style.setProperty('--barh',bar.offsetHeight+'px')}pad();addEventListener('resize',pad);
  var main=document.getElementById('main');if(!main||!main.dataset.id)return;
  function fail(){document.querySelectorAll('.skel').forEach(function(s){var l=s.querySelector('.lbl');s.outerHTML='<section class="card un"><div class="top"><span class="lbl">'+(l?l.textContent:'Reading')+'</span><span class="tag t-unav"><i class="g"></i>Unavailable</span></div><p>Readings could not be loaded. Check the official sources before you go.</p></section>'})}
  var ctl=window.AbortController?new AbortController():null;var to=setTimeout(function(){if(ctl)ctl.abort()},20000);
  fetch(location.pathname.replace(/\/$/,'')+'.json',{credentials:'same-origin',signal:ctl&&ctl.signal}).then(function(r){if(!r.ok)throw 0;return r.json()}).then(function(d){
    clearTimeout(to);Object.keys(d.fragments||{}).forEach(function(k){var el=document.querySelector('[data-card="'+CSS.escape(k)+'"]');if(el)el.outerHTML=d.fragments[k]});
    fail();document.getElementById('live').textContent='Readings loaded.'}).catch(fail);
})();
/* Interactive charts (Ed t572u): drag, tap or use arrow keys on a chart to read the exact value and time
   at that point. Values come only from the plotted readings or predictions; nothing is interpolated. */
(function(){
  function wire(svg){
    if(svg.dataset.wired)return;svg.dataset.wired='1';
    var rows;try{rows=JSON.parse(svg.dataset.scrub)}catch(e){return}
    if(!rows.length)return;
    var NS='http://www.w3.org/2000/svg',vb=svg.viewBox.baseVal,cur=document.createElementNS(NS,'line');
    cur.setAttribute('class','cur');cur.setAttribute('y1',4);cur.setAttribute('y2',vb.height-14);cur.style.display='none';svg.appendChild(cur);
    var out=document.createElement('p');out.className='readout';out.setAttribute('aria-live','polite');
    out.textContent='Drag across the chart to read values';svg.after(out);var i=rows.length-1;
    function show(k){i=Math.max(0,Math.min(rows.length-1,k));cur.setAttribute('x1',rows[i][0]);cur.setAttribute('x2',rows[i][0]);cur.style.display='';
      out.textContent=svg.dataset.hint+': '+rows[i][1]}
    function at(ev){var r=svg.getBoundingClientRect(),x=(ev.clientX-r.left)/r.width*vb.width,b=0;
      rows.forEach(function(p,k){if(Math.abs(p[0]-x)<Math.abs(rows[b][0]-x))b=k});show(b)}
    svg.addEventListener('pointerdown',function(e){at(e)});svg.addEventListener('pointermove',function(e){if(e.buttons||e.pointerType==='mouse')at(e)});
    svg.addEventListener('keydown',function(e){if(e.key==='ArrowRight'||e.key==='ArrowLeft'){e.preventDefault();show(i+(e.key==='ArrowRight'?1:-1))}});
    svg.addEventListener('focus',function(){show(i)});
  }
  function scan(){document.querySelectorAll('svg[data-scrub]').forEach(wire)}
  scan();new MutationObserver(scan).observe(document.getElementById('main')||document.body,{childList:true,subtree:true});
})();
