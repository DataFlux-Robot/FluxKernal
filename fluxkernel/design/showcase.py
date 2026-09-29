"""Local self-contained HTML, using recorded exact checks and Lean certificates.

Frames are discrete audited configurations, not a continuous dynamics simulation.
"""

import copy
import json
from pathlib import Path

from .examples import fourbar
from .model import Design, canonical, const
from .proof import certify


def generate(directory):
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=False)
    cases = []
    phases = ["1/4", "1/2", "3/4", "1", "3/2"]
    for mode in ("valid", "thin", "wrong-pin", "broken-loop"):
        for i, phase in enumerate(phases):
            document = copy.deepcopy(fourbar())
            inputs = {"phase": phase}
            if mode == "thin":
                inputs["thickness"] = "2"
            elif mode == "wrong-pin":
                inputs["pin"] = "8"
            elif mode == "broken-loop":
                document["members"][1]["length"] = const(65, "mm")
            design = Design(document)
            report = design.check(inputs)
            if mode == "valid":
                report = certify(document, root / f"certificate-{i}", inputs)
            elif report["accepted"]:
                raise ValueError("Counterexample unexpectedly accepted: " + mode)
            cases.append(
                {
                    "mode": mode,
                    "phase": phase,
                    "report": report,
                    "members": [
                        {k: m[k] for k in ("id", "a", "b")} for m in document["members"]
                    ],
                }
            )
    result = {
        "accepted": True,
        "model_calls": 0,
        "frames": len(phases),
        "lean_certificates": len(phases),
        "rejected_counterexamples": len(cases) - len(phases),
        "scope": "discrete exact-rational configurations, not continuous dynamics",
        "cases": cases,
    }
    (root / "evidence.json").write_bytes(canonical(result) + b"\n")
    (root / "design.json").write_bytes(canonical(fourbar()) + b"\n")
    data = json.dumps(cases, ensure_ascii=False).replace("<", "\\u003c")
    (root / "index.html").write_text(HTML.replace("__DATA__", data), encoding="utf-8")
    return {k: v for k, v in result.items() if k != "cases"} | {
        "html": str(root / "index.html")
    }


HTML = """<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FluxKernal · Executable design definitions</title>
<style>
body{margin:0;background:#0b1320;color:#e7edf6;font:16px system-ui,sans-serif}main{max-width:1100px;margin:auto;padding:36px 24px}
h1{font-size:clamp(28px,4vw,48px);margin:14px 0}p{color:#b3c2d5;line-height:1.7}a{color:#70e0cc}label{display:inline-block;margin:12px 24px 12px 0}
select,input{font:inherit;padding:8px;background:#152539;color:#eef;border:1px solid #526174;border-radius:5px}input{vertical-align:middle}
.grid{display:grid;grid-template-columns:2fr 1fr;gap:18px}.panel{background:#122031;border:1px solid #314355;border-radius:12px;padding:20px;min-width:0;overflow-x:auto}
svg{width:100%;height:auto}#state{font-size:22px;font-weight:700}.good{color:#65dfbd}.bad{color:#ff9898}table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:10px 5px;text-align:left;border-bottom:1px solid #314355}code{overflow-wrap:anywhere}
@media(max-width:700px){.grid{grid-template-columns:1fr}main{padding:20px 12px}}
</style><main>
<a href="https://github.com/DataFlux-Robot/FluxKernal">FluxKernal</a>
<h1>定义机构，也定义它必须满足什么。</h1>
<p>闭链 · 带单位的参数关系 · 隐式 CSG · 接口匹配 · 制造要求 · Lean 检查<br>
本页面完全离线，无模型调用。滑块选择 5 个已计算构型；不是连续动力学仿真。</p>
<label>设计方案 <select id="mode"><option value="valid">有效四连杆</option><option value="thin">反例：厚度不足</option><option value="wrong-pin">反例：装配孔径不匹配</option><option value="broken-loop">反例：杆长与闭链不一致</option></select></label>
<label>构型 <input id="phase" type="range" min="0" max="4" value="1" step="1"> <span id="phaseLabel"></span></label>
<div class="grid"><div class="panel"><svg id="mechanism" viewBox="0 0 650 320" role="img" aria-label="四连杆构型"></svg>
<p>杆件构成一个独立闭环。位置由尺寸表达式生成，杆长约束用精确有理数检查。</p></div>
<div class="panel"><div id="state"></div><p id="proof"></p><svg id="plate" viewBox="0 0 200 170" role="img" aria-label="参数化开孔安装板"></svg>
<p id="dimensions"></p><p>板件定义为 box − cylinder。图为孔穿过板件处的截面；精确成员测试见下方 probe 项。</p></div></div>
<div class="panel" style="margin-top:18px"><h2>设计义务</h2><table><thead><tr><th>要求</th><th>类别</th><th>结果</th><th>精确差值（SI）</th></tr></thead><tbody id="checks"></tbody></table></div>
<p>绿色意味着该构型通过声明的检查。制造要求是尺寸/简化公式约束，不是可制造性认证；未证明全局无碰撞、强度或动力学稳定。
Lean 证明覆盖生成的表达式与探针，JSON 解析和表达式生成仍属于 Python 信任边界。</p>
<p><a href="evidence.json">完整证据</a> · <a href="design.json">原始设计定义</a> · <a id="certificate" href="certificate-1/Instance.lean">当前 Lean 证书</a></p>
<script>const cases=__DATA__;const $=id=>document.getElementById(id);
const number=s=>{const p=s.split('/').map(Number);return p.length===2?p[0]/p[1]:p[0]};
const node=(tag,attrs,text)=>{let n=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v]of Object.entries(attrs))n.setAttribute(k,v);if(text)n.textContent=text;return n};
function render(){const i=Number($('phase').value),mode=$('mode').value,c=cases.filter(c=>c.mode===mode)[i],r=c.report;
$('phaseLabel').textContent='t = '+c.phase;$('state').textContent=r.accepted?'通过当前设计义务':'已拒绝此设计';$('state').className=r.accepted?'good':'bad';
$('proof').textContent=r.proof.accepted?'真实 Lean 内核已检查此构型':'约束检查失败，不签发证书';
const svg=$('mechanism');svg.replaceChildren();const xy={};for(const [name,p]of Object.entries(r.positions_si))xy[name]=[100+number(p[0])*2500,260-number(p[1])*2500];
for(const m of c.members){const a=xy[m.a],b=xy[m.b],failed=r.checks.some(x=>x.id==='closure:'+m.id&&!x.passed);svg.append(node('line',{x1:a[0],y1:a[1],x2:b[0],y2:b[1],stroke:failed?'#ff7777':'#65dfbd','stroke-width':12,'stroke-linecap':'round'}));svg.append(node('text',{x:(a[0]+b[0])/2,y:(a[1]+b[1])/2-12,fill:'#eef','font-size':14},m.id))}
for(const [name,p]of Object.entries(xy)){svg.append(node('circle',{cx:p[0],cy:p[1],r:7,fill:'#0b1320',stroke:'#cbe5ef','stroke-width':2}));svg.append(node('text',{x:p[0]+10,y:p[1]+20,fill:'#eef'},name))}
const plate=$('plate');plate.replaceChildren();plate.append(node('rect',{x:40,y:20,width:120,height:120,fill:'#70a9cd',rx:0}));plate.append(node('circle',{cx:100,cy:80,r:number(r.parameters_si.pin)*2000,fill:'#122031'}));
$('dimensions').textContent='厚度 '+(number(r.parameters_si.thickness)*1000)+' mm · 孔径 '+(number(r.parameters_si.pin)*1000)+' mm';
const body=$('checks');body.replaceChildren();for(const check of r.checks){let row=document.createElement('tr');for(const text of [check.id,check.category,check.passed?'PASS':'FAIL',check.residual_si??'—']){let cell=document.createElement('td');cell.textContent=text;row.append(cell)}row.className=check.passed?'good':'bad';body.append(row)}
$('certificate').hidden=!r.accepted;$('certificate').href='certificate-'+i+'/Instance.lean';}
$('mode').addEventListener('change',render);$('phase').addEventListener('input',render);render();</script></main></html>"""
