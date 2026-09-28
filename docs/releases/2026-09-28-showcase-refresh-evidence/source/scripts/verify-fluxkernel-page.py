"""Verify the frozen FluxKernel static release with Playwright and trusted HTTP.
Usage: python verify-fluxkernel-page.py BASE_URL PAYLOAD EVIDENCE
Requires playwright, httpx and Chromium (CHROME_BINARY optionally overrides).
"""
import hashlib, json, os, sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import httpx
from playwright.sync_api import sync_playwright

base, root, evidence = sys.argv[1:]
root, evidence = Path(root), Path(evidence)
evidence.mkdir(parents=True,exist_ok=True)
report={'base':base,'routes':[], 'viewports':[], 'interactions':[], 'errors':[]}
with httpx.Client(trust_env=False,timeout=60,follow_redirects=True) as client:
    for file in sorted(root.rglob('index.html')):
        name=file.relative_to(root).as_posix()
        response=client.get(base.rstrip('/')+'/'+name)
        assert response.status_code==200,(name,response.status_code)
        if base.startswith('http://127.'):
            assert response.content==file.read_bytes(),name
        report['routes'].append({'path':name,'status':response.status_code})
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=os.environ.get('CHROME_BINARY','/home/exuber/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome'),args=['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
    page=browser.new_page(ignore_https_errors=False)
    asset_requests=[]
    page.on('request',lambda r:asset_requests.append(r.url) if urlparse(r.url).path in ('/fluxkernel/viewer.js','/fluxkernel/car.json','/fluxkernel/aircraft.json','/fluxkernel/phone.json') else None)
    page.on('pageerror',lambda error:report['errors'].append(str(error)))
    page.on('console',lambda message:report['errors'].append(message.text) if message.type=='error' else None)
    for width in [1440,768,390,320]:
        page.set_viewport_size({'width':width,'height':960})
        for route in ['technology/index.html','technology/fluxkernel/index.html']:
            response=page.goto(base.rstrip('/')+'/'+route,wait_until='networkidle',timeout=90000)
            assert response.status==200
            page.evaluate('document.fonts.ready')
            if 'fluxkernel/' in route:
                page.wait_for_function("document.querySelector('#fk-run-status').textContent.includes('真实运行')",timeout=60000)
                assert page.locator('#fk-view-error').is_hidden()
                assert page.locator('[data-fk-part]').count()==32
            layout=page.evaluate('''() => ({scroll:document.documentElement.scrollWidth, clipped:[...document.querySelectorAll('h1,h2,h3,p,dt,dd,figcaption,summary')].filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&(r.left< -1||r.right>innerWidth+1)}).map(e=>e.textContent.trim())})''')
            assert layout['scroll']<=width+1,(width,route,layout)
            assert not layout['clipped'],(width,route,layout)
            assert page.get_by_text('Copyright © 2026 陕西省数瀚衍动科技有限公司 版权所有',exact=True).count()==1
            label='fluxkernel' if 'fluxkernel/' in route else 'technology'
            page.screenshot(path=str(evidence/f'{label}-{width}.png'),full_page=True)
            report['viewports'].append({'width':width,'route':route,**layout})
        for case,count in [('car',29),('aircraft',32),('phone',20)]:
            page.locator(f'[data-fk-case="{case}"]').click()
            page.wait_for_function("([key,count])=>document.querySelector(`[data-fk-case='${key}']`).getAttribute('aria-pressed')==='true'&&document.querySelectorAll('[data-fk-part]').length===count",arg=[case,count],timeout=60000)
            if case in ('car','aircraft'):
                case_data=json.loads((root/f'fluxkernel/{case}.json').read_text())
                pal=case_data['perception']
                expected_status='达到模型评审门槛' if pal['quality_status']=='model-threshold-met' else '外观仍待改进'
                assert expected_status in page.locator('#fk-visual-status').inner_text()
                assert page.locator('[data-fk-round]').count()==len(pal['rounds'])
                assert page.locator(f'[data-fk-round="{pal["selected_round"]}"]').get_attribute('data-selected')=='true'
                assert case_data['version'] in page.locator('#fk-budget-context').inner_text()
                page.locator('#fk-canvas').screenshot(path=str(evidence/f'{case}-current-{width}.png'))
                assert page.locator('[data-fk-round][data-selected="true"]').count()==1
                for img in page.locator('#fk-visual-rounds img').all():
                    img.scroll_into_view_if_needed()
                    img.evaluate('(img)=>img.decode()')
                    assert img.evaluate('(img)=>img.naturalWidth')==896
                page.locator('#fk-visual-rounds').screenshot(path=str(evidence/f'{case}-feedback-{width}.png'))
            else:
                assert '尚未进行视觉评审' in page.locator('#fk-visual-status').inner_text()
            page.locator('[data-fk-view="equipment"]').click()
            assert page.locator('[data-fk-part]').count()==20
            page.locator('[data-fk-part]').nth(2).click()
            assert page.locator('[data-fk-part]').nth(2).get_attribute('aria-pressed')=='true'
            assert 'mm' in page.locator('#fk-inspector').inner_text()
            page.locator('#fk-explode').evaluate("e=>{e.value='80';e.dispatchEvent(new Event('input',{bubbles:true}))}")
            page.locator('#fk-fit').click()
            page.locator('#fk-canvas').screenshot(path=str(evidence/f'{case}-equipment-{width}.png'))
            page.locator('[data-fk-view="product"]').click()
            assert page.locator('[data-fk-part]').count()==count
            assert '工程检查通过' in page.locator('#fk-proof-status').inner_text()
            report['interactions'].append({'width':width,'case':case,'product':count,'equipment':20,'partsSelection':True,'explode':True})
        page.locator('details:has(#fk-assumptions) summary').click()
        assert page.locator('#fk-assumptions li').count()>0
        assert page.locator('#fk-gaps li').count()>0
        page.locator('details:has(#fk-assumptions) summary').focus(); page.keyboard.press('Enter')
        assert page.locator('details:has(#fk-assumptions)').get_attribute('open') is None
    assert page.locator('#historical-recording').get_attribute('open') is None
    page.locator('#historical-recording summary').click()
    page.locator('video').scroll_into_view_if_needed()
    page.locator('video').evaluate('v=>{v.muted=true;return v.play()}')
    page.wait_for_function("document.querySelector('video').currentTime>0.5",timeout=30000)
    report['video']=page.locator('video').evaluate('v=>({duration:v.duration,currentTime:v.currentTime,paused:v.paused})')
    assert 46<report['video']['duration']<49
    assert not report['video']['paused']
    assert asset_requests and all(parse_qs(urlparse(url).query).get('v') for url in asset_requests),asset_requests
    report['versioned_asset_requests']=len(asset_requests)
    browser.close()
assert not report['errors'],report['errors']
(evidence/'browser-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({'routes':len(report['routes']),'viewports':len(report['viewports']),'caseChecks':len(report['interactions']),'video':report['video'],'errors':report['errors']},ensure_ascii=False))
