#!/usr/bin/env python3
"""Silent walkthrough of saved *real* runs, not a simulated live inference."""
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright
p=argparse.ArgumentParser();p.add_argument('--phone',required=True);p.add_argument('--car',required=True);p.add_argument('--aircraft',required=True);p.add_argument('--revision',required=True);p.add_argument('--browser');p.add_argument('--url',default='http://127.0.0.1:8740');p.add_argument('--output',default='.demo/video');args=p.parse_args()
out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
with sync_playwright() as pw:
    options={'headless':True,'args':['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']}
    if args.browser:options['executable_path']=args.browser
    browser=pw.chromium.launch(**options)
    context=browser.new_context(viewport={'width':1600,'height':1150},record_video_dir=str(out),record_video_size={'width':1600,'height':1150})
    page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    def load(id):
        page.goto(args.url+'/?run='+id)
        page.wait_for_function("!document.querySelector('#details').hidden")
        page.wait_for_timeout(2200)
    def explode(value):
        page.locator('#explode').fill(str(value));page.locator('#explode').dispatch_event('input');page.wait_for_timeout(1500)
    load(args.phone)
    for value in [15,30,45,60]:explode(value)
    page.locator('.tree-row').nth(4).click();page.wait_for_timeout(2000)
    page.locator('[data-view="equipment"]').click();explode(0);page.locator('#fit-view').click();page.wait_for_timeout(2500)
    explode(25)
    page.locator('[data-view="graph"]').click();page.wait_for_timeout(2500)
    page.locator('#graph').evaluate('(e)=>{e.scrollLeft=320;e.scrollTop=110}');page.wait_for_timeout(1800)
    page.locator('#proof-title').scroll_into_view_if_needed();page.wait_for_timeout(1800)
    page.locator('#details').scroll_into_view_if_needed();page.wait_for_timeout(2200)
    load(args.car);explode(35);page.locator('[data-view="equipment"]').click();explode(0);page.locator('#fit-view').click();page.wait_for_timeout(2200)
    load(args.aircraft);explode(30);page.locator('[data-view="equipment"]').click();explode(0);page.locator('#fit-view').click();page.wait_for_timeout(2200)
    load(args.revision);page.wait_for_timeout(2500)
    page.screenshot(path=str(out/'final-frame.png'),full_page=True)
    video=page.video;context.close();path=video.path();browser.close()
    assert not errors,errors
    print(path)
