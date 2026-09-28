"""Offline evidence page; never promotes a prototype into a qualified upgrade."""

from html import escape
from pathlib import Path


def build_report(root, report):
    root = Path(root)

    def link(path):
        return escape(str(Path(path).relative_to(root)), quote=True)

    cards = []
    for record in report["records"]:
        i = record["round"]
        if record["state"] != "reviewed":
            cards.append(
                f"<section><h2>第 {i + 1} 轮 · 已拒绝</h2><pre>{escape(str(record['attempts']))}</pre></section>"
            )
            continue
        result = record["candidate"]
        bundle = Path(result["directory"])
        selected = i == report["selected_round"]
        title = f"第 {i + 1} 轮" + (" · GLM 最终选择" if selected else "")
        step = bundle / "cad" / result["part_body"] / "part.step"
        cards.append(f'''<section><h2>{title}</h2><p>{escape(record["review"]["reason"])}</p>
        <img src="{link(bundle / "views.png")}" alt="实际整机四视图"><div class="pair">
        <a href="{link(bundle / "head.png")}"><img src="{link(bundle / "head.png")}" alt="头部近景"></a>
        <a href="{link(bundle / "part.png")}"><img src="{link(bundle / "part.png")}" alt="独立 STEP 零件"></a></div>
        <p>视觉评价：{escape(record["review"]["verdict"])} · 新增估算质量：{result["added_mass_kg"] * 1000:.2f} g
        · 结构证明：{result["proof_accepted"]} · 接口验证：尚未完成</p>
        <p><a href="{link(step)}">STEP</a> · <a href="{link(step.with_suffix(".stl"))}">STL</a> ·
        <a href="{link(bundle / "robot.urdf")}">整机 URDF</a> · <a href="{link(bundle / "motion-checks.json")}">姿态筛查</a></p>
        <details><summary>评审发现</summary><pre>{escape(str(record["review"]["findings"]))}</pre></details></section>''')
    brief = (root / "brief.txt").read_text()
    html = f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>FluxKernel · 个性化机器人原型</title><style>
    body{{margin:0;background:#101721;color:#e6edf3;font:16px/1.65 system-ui,sans-serif}}main{{max-width:1100px;margin:auto;padding:36px 20px}}
    h1{{font-size:32px}}h2{{font-size:23px}}a{{color:#80d0eb}}section{{border:1px solid #344153;border-radius:14px;padding:22px;margin:24px 0;background:#17212e}}
    img{{width:100%;border-radius:8px}}.pair{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}
    .note{{color:#ffd58c}}small{{color:#aab9ca}}</style><main><small>DATAFLUX DYNAMICS / FLUXKERNEL</small>
    <h1>个性化机器人外观件</h1><p>{escape(brief)}</p>
    <p>GLM-5.3-Flash · {escape(report["mode"])} · 最多 {report["max_rounds"]} 轮 · 实际调用 {report.get("model_calls", 0)} 次</p>
    <p>运行状态：{escape(report['status'])} · 最终选择：{report['selected_round'] + 1 if report['selected_round'] is not None else '无'}。{escape(report.get('selection', {}).get('reason', report.get('error', '')))}</p>
    <p class="note">当前是可检查的外观原型。安装贴合、粘接保持力、打印工艺和真实运动性能尚未验证，不能直接视为可上机升级件。</p>
    <details><summary>原机器人</summary><img src="baseline.png" alt="原机器人"></details>
    {"".join(cards)}<p><a href="run.json">完整运行记录</a> · <a href="workflow.json">工作流与软件版本</a> · <a href="zone.json">冻结约束</a></p></main></html>"""
    (root / "index.html").write_text(html)
