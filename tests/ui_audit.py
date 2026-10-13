import json
from playwright.sync_api import sync_playwright
import sys; OUT=sys.argv[2]; URL=sys.argv[1]; PRE=sys.argv[3]
with sync_playwright() as pw:
    b=pw.chromium.launch()
    for tag,vp in (('desktop',{'width':1440,'height':900}),('mobile',{'width':390,'height':844})):
        ctx=b.new_context(viewport=vp,is_mobile=tag=='mobile',has_touch=tag=='mobile'); pg=ctx.new_page()
        pg.goto(URL+('?drive=0' if tag=='mobile' else '')); 
        if tag=='mobile' and pg.query_selector('#drive:not([hidden])'): pg.click('#dExit')
        pg.wait_for_selector('#results:not([hidden])',timeout=240000); pg.wait_for_timeout(7000)
        pg.screenshot(path=f'{OUT}{PRE}_{tag}_first_screen.png')
        pg.screenshot(path=f'{OUT}{PRE}_{tag}_full.png',full_page=True)
        m=pg.evaluate("""()=>{const p=document.getElementById('panel'); const grps=[...p.querySelectorAll('.grp')].map(g=>(g.querySelector('h2')||{}).textContent||g.id);
          const y=document.getElementById('results').getBoundingClientRect().top+scrollY;
          return {groups:grps.length, names:grps, chips:p.querySelectorAll('.chip').length, inputs:p.querySelectorAll('input,select').length, buttons:document.querySelectorAll('button').length,
            resultsTop:Math.round(y), pageH:document.documentElement.scrollHeight, presets:document.querySelectorAll('#ideas .chip').length,
            cardH:Math.round((document.querySelector('#cards .card')||{getBoundingClientRect:()=>({height:0})}).getBoundingClientRect().height),
            cardBadges:(document.querySelector('#cards .card')||document.body).querySelectorAll('.ob > *').length}}""")
        print(tag,json.dumps(m))
        pg.evaluate("document.getElementById('cards').scrollIntoView()"); pg.wait_for_timeout(500); pg.screenshot(path=f'{OUT}{PRE}_{tag}_cards.png')
        pg.click('#cards .card',position={'x':8,'y':8}); pg.wait_for_selector('.drawer',timeout=60000); pg.wait_for_timeout(2000); pg.screenshot(path=f'{OUT}{PRE}_{tag}_drawer.png')
        print(tag,'drawer sections',pg.eval_on_selector_all('.drawer h3','e=>e.map(x=>x.textContent.trim().slice(0,40))'), 'drawerH', pg.evaluate("document.querySelector('.drawer').scrollHeight"))
        ctx.close()
