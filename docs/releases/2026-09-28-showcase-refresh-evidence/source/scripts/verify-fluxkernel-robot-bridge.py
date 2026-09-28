"""Check the public bridge announcement on desktop/mobile, locally or live."""
import json
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

base, output = sys.argv[1:]
out = Path(output)
out.mkdir(parents=True, exist_ok=True)
report = {'base': base, 'viewports': [], 'errors': []}
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox', '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
    page = browser.new_page(ignore_https_errors=False)
    page.on('pageerror', lambda e: report['errors'].append(str(e)))
    for width in [1440, 390, 320]:
        page.set_viewport_size({'width': width, 'height': 960})
        page.goto(base.rstrip('/')+'/technology/index.html', wait_until='networkidle')
        card = page.locator('a.technology-catalog-card').filter(has=page.get_by_role('heading', name='FluxKernel', exact=True))
        assert '272' in card.inner_text() and 'URDF/MJCF' in card.inner_text()
        card.click()
        page.wait_for_url('**/technology/fluxkernel/index.html')
        page.locator('a[href="#robot-bridge"]').click()
        section = page.locator('#robot-bridge')
        assert '当前不提供 Lean ↔ URDF 双向无损转换' in section.inner_text()
        assert 'GLM-5.3-Flash' in section.inner_text() and '最多 3 轮' in section.inner_text()
        for img in section.locator('img').all():
            img.scroll_into_view_if_needed()
            img.evaluate('img=>img.decode()')
            assert img.evaluate('img=>img.naturalWidth') == 1024
        assert page.evaluate('document.documentElement.scrollWidth') <= width + 1
        section.screenshot(path=str(out/f'robot-bridge-{width}.png'))
        # Follow real evidence and attribution links, not just string assertions.
        evidence_url = section.locator('a').filter(has_text='查看验证摘要').get_attribute('href')
        response = page.request.get(base.rstrip('/')+evidence_url)
        assert response.status == 200
        evidence = response.json()
        assert evidence['local_tests_passed'] == 272
        for robot in evidence['robots'].values():
            assert robot['engineering_checks']=='passed'
            assert robot['export_checks']=='passed'
            assert 'verification' not in robot and 'native_sha256' not in robot
            assert robot['interface_status'] == 'unverified' and not robot['deployment_ready']
        source_url = section.locator('a').filter(has_text='模型来源与许可').get_attribute('href')
        assert page.request.get(base.rstrip('/')+source_url).status == 200
        report['viewports'].append({'width': width, 'navigation': True, 'images': 2, 'evidence': True, 'scope_labels': True})
    browser.close()
assert not report['errors'], report['errors']
(out/'robot-bridge-browser.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
print(json.dumps(report, ensure_ascii=False))
