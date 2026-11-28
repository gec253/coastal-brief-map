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
