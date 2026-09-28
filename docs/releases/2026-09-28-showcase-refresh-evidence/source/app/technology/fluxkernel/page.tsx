import type { Metadata } from "next";
import { Arrow, CorporatePage } from "../../_components/CorporateChrome";
import styles from "./fluxkernel.module.css";

export const metadata: Metadata = {
  title: "FluxKernel — 从产品图片到制造计划 | 数瀚衍动",
  description: "FluxKernel 结合 Lean 4 形式化验证、URDF/MJCF 导出与 GLM-5.3-Flash 的有限轮 Perception–Action Loop，探索产品拆解和机器人个性化设计。",
  alternates: { canonical: "https://www.datafluxdynamics.ltd/technology/fluxkernel/" }
};

const flow = [
  ["01", "生成候选 CAD", "从参考图片与需求出发，建立具名零件与几何。"],
  ["02", "看见实际几何", "渲染 CAD 四视图，与输入图片一起送回模型。"],
  ["03", "评审与局部修订", "GLM 检查轮廓、比例和布局，提出受约束的修改。"],
  ["04", "再评审、保留候选", "在有限预算内比较结果，记录退步与未解决问题。"]
];

export default function FluxKernelPage() {
  return <CorporatePage active="technology">
    <section className={styles.hero}>
      <div>
        <p className={styles.eyebrow}>FLUXKERNEL <span>有限迭代 · 工程原型</span></p>
        <h1>看见一个产品。<br />拆解它，<br /><em>也拆解制造它的设备。</em></h1>
        <p className={styles.lead}>让 Agent 看见自己生成的 CAD，评审、修改，再次验证。通过 Perception–Action Loop，把产品图片逐步推进为零件、加工设备与有证据的制造计划。</p>
        <div className={styles.experimentBadges} aria-label="本次演示的模型与迭代预算"><span>模型 <b>GLM-5.3-Flash</b></span><span>机制 <b>Perception–Action Loop</b></span><span>每次运行预算 <b>最多 3 轮评审</b></span></div>
        <p className={styles.experimentScope}>当前展示有限迭代预算下的中间结果：观察系统如何发现问题、修订设计并保留候选。外观与工程性能仍需继续验证。</p>
        <div className={styles.actions}>
          <a className="corp-button primary" href="#interactive">探索三维案例 <span aria-hidden="true">↓</span></a>
          <a className="corp-button outline-light" href="#robot-bridge">查看机器人设计能力 <Arrow /></a>
        </div>
      </div>
      <figure className={styles.flow} aria-label="从图片到设备和证据的研发路径">
        <figcaption>PERCEPTION → ACTION → EVALUATION</figcaption>
        <ol>{flow.map(([n,title,body]) => <li key={n}><span>{n}</span><div><strong>{title}</strong><p>{body}</p></div></li>)}</ol>
        <div className={styles.flowFoot}>本次汽车完成 3 轮，飞机完成 2 轮后由模型停止。</div>
      </figure>
    </section>
    <nav className={`technology-detail-nav ${styles.detailNav}`} aria-label="技术路线导航">
      <a href="/technology/">技术总览</a><a href="/technology/fluxprsi/">FluxPRSI</a><a href="/technology/mechanogenesis/">Mechanogenesis</a><a href="/technology/edge-model/">端侧模型</a><a className="active" aria-current="page" href="/technology/fluxkernel/">FluxKernel</a>
    </nav>
    <section className={styles.metrics} aria-label="内部原型验证结果">
      <div><strong>3</strong><span>真实图片案例</span><small>手机 / 汽车 / 飞机</small></div>
      <div><strong>1<span>轮</span></strong><span>加工设备展开</span><small>每例生成 20 个设备概念部件</small></div>
      <div><strong>272</strong><span>本地自动测试通过</span><small>v0.10 · 含机器人与真实 Lean 检查</small></div>
      <div><strong>39<span>/40</span></strong><span>修订后复用的零件</span><small>仅重建手机后盖的真实运行</small></div>
    </section>
    <section className={`${styles.section} ${styles.robotSection}`} id="robot-bridge" aria-labelledby="robot-bridge-title">
      <div className={styles.sectionHead}><p className={styles.label}>NEW / 原生机器人 · v0.10</p><h2 id="robot-bridge-title">可验证的设计，<br />可延展的机器人。</h2><p>Microduck 与 XGO 已支持设计修改、工程检查和 URDF / MJCF 导出。以可复用的机器人资产为起点，探索面向不同用户的个性化硬件。</p></div>
      <div className={styles.robotBridge} aria-label="机器人设计、形式化验证和工具协作">
        <div className={styles.robotAuthority}><span>设计与复用</span><h3>FluxKernel 原生机器人</h3><p>保留已有机构，探索新的外观与功能。<br />设计修改有记录，验证结果可追溯。</p></div>
        <div className={styles.robotBranches}>
          <article><span>01 / 工程可信度</span><h3>Lean 4 形式化验证</h3><p>为限定范围的工程检查提供形式化支持，让设计结果有可核验的依据。</p></article>
          <article><span>02 / 工具协作</span><h3>URDF / MJCF 导出</h3><p>连接常用机器人展示与仿真工具，支持设计结果继续进入后续研发流程。</p></article>
        </div>
      </div>
      <div className={styles.robotStatus} aria-label="链路实现状态">
        <p><b>已跑通</b><span>Microduck / XGO 设计修改、验证与导出已完成案例测试。</span></p>
        <p><b>能力边界</b><span>当前不提供 Lean ↔ URDF 双向无损转换；导出通过检查不代表实机已验证。</span></p>
      </div>
      <div className={styles.robotCases}>
        <article><a href="/fluxkernel/native-robots/microduck-head.png"><img src="/fluxkernel/native-robots/microduck-head.png" width="1024" height="816" loading="lazy" alt="Microduck 原机器人与 GLM 设计的黄色头顶附加装饰件四视图" /></a><div><span>MICRODUCK / 模型选择第 1 轮</span><h3>保留机构，添加个性化零件。</h3><p>GLM 调用 4 次 · 新增估算质量 2.06 g。变体已完成工程检查与导出测试，实际安装仍待验证。</p></div></article>
        <article><a href="/fluxkernel/native-robots/xgoduck-head.png"><img src="/fluxkernel/native-robots/xgoduck-head.png" width="1024" height="816" loading="lazy" alt="XGO Duck 原机器人与 GLM 设计的黄色头顶附加装饰件四视图" /></a><div><span>XGO DUCK / 模型选择第 3 轮</span><h3>修订有边界，失败有记录。</h3><p>GLM 调用 9 次 · 新增估算质量 2.15 g。已完成有限姿态采样检查，连续运动与实际安装仍待验证。</p></div></article>
      </div>
      <div className={styles.budgetContext}><div><span>个性化零件实验条件</span><strong>GLM-5.3-Flash · Perception–Action Loop · 最多 3 轮</strong></div><p>造型、修订和最终选择均由模型完成；系统执行工程检查并保存结果。展示的是小型附加外观件原型，模型评价并非独立外观验收。</p></div>
      <p className={styles.note}>形式化验证仅覆盖已声明的范围与前提，不构成完整几何或物理性能证明。安装贴合、相机视场、打印工艺及行走性能尚未验证。</p>
      <div className={styles.robotLinks}><a href="/fluxkernel/native-robots/evidence.json">查看验证摘要 <Arrow /></a><a href="/fluxkernel/native-robots/sources.json">模型来源与许可 <Arrow /></a><a href="#interactive">继续探索产品与加工设备 <Arrow /></a></div>
    </section>
    <section className={styles.section} id="interactive" aria-labelledby="interactive-title">
      <div className={styles.sectionHead}><p className={styles.label}>01 / 真实运行 · 交互查看</p><h2 id="interactive-title">从外形，<br />走进制造层级。</h2><p>选择产品，查看有限预算下保留的候选，再向下对比每轮变化。汽车已更新为 v0.6 参数化案例，飞机已更新为 v0.7 整体装配案例；手机保留早期生成记录。新图片生成由研发后端执行。</p></div>
      <div className={styles.budgetContext}><div><span>本次实验条件</span><strong>Perception–Action Loop × GLM-5.3-Flash</strong></div><p id="fk-budget-context">GLM-5.3-Flash · 每次运行最多 3 轮评审。汽车实际完成 3 轮，飞机完成 2 轮后由模型停止；均展示模型最终保留的候选。</p></div>
      <div className={styles.caseTabs} role="group" aria-label="选择案例">
        <button data-fk-case="phone" aria-pressed="false"><span>01</span> 手机 <small>20 个产品件 · 早期记录</small></button>
        <button data-fk-case="car" aria-pressed="false"><span>02</span> 汽车 <small>v0.6 · 29 件 · 3 轮评审</small></button>
        <button data-fk-case="aircraft" aria-pressed="true"><span>03</span> 飞机 <small>v0.7 · 32 件 · 2 轮评审</small></button>
      </div>
      <div className={styles.explorer}>
        <div className={styles.stage}>
          <div className={styles.stageTop}><div className={styles.switches} role="group" aria-label="查看层级"><button data-fk-view="product" aria-pressed="true">产品设计</button><button data-fk-view="equipment" aria-pressed="false">加工设备 M₁</button></div><span id="fk-run-status" role="status">正在载入真实案例</span></div>
          <div className={styles.canvasWrap}><canvas id="fk-canvas" aria-label="可旋转、缩放和选择零件的三维概念模型" /><div className={styles.canvasCaption}><span id="fk-case-title">飞机制造概念</span><small>参数化概念几何 · 毫米坐标</small></div><img id="fk-input-image" className={styles.inputImage} src="/fluxkernel/aircraft-input.png" alt="本次运行的产品参考图片" /><button id="fk-fit" className={styles.fit} aria-label="适配三维视图">⤢</button><p id="fk-view-error" className={styles.viewerError} hidden /></div>
          <div className={styles.stageBottom}><label htmlFor="fk-explode">装配 <input id="fk-explode" type="range" min="0" max="100" defaultValue="0" /> 爆炸</label><span>拖动旋转 · 滚轮缩放 · 点击选件</span></div>
        </div>
        <aside className={styles.parts}><div className={styles.partsHead}>零件与制造路线 <span id="fk-part-count">32 件</span></div><div id="fk-parts" className={styles.partList} /><div id="fk-inspector" className={styles.inspector}><span>PART INSPECTOR</span><h3>选择一个零件</h3><p>查看它的材料、尺寸、来源和制造路线。</p></div></aside>
      </div>
      <div className={styles.proofStrip}><div><span>LEAN 4 / ENGINEERING VALIDATION</span><strong id="fk-proof-status">工程检查结果</strong></div><p id="fk-proof-detail">提供限定范围的形式化验证；材料、工艺、装配和整机性能仍需验证。</p><a href="#verification">理解验证范围 <Arrow /></a></div>
      <p className={styles.note}>三维模型为候选工程架构。采购件显示布局包络，加工件显示毛坯；它们不是对原产品全部隐藏结构的复刻。</p>
      <section className={styles.perception} aria-labelledby="fk-perception-title">
        <div className={styles.perceptionHead}><div><p className={styles.label}>PERCEPTION–ACTION LOOP · 有限次迭代</p><h3 id="fk-perception-title">有限预算，记录每次修改与取舍。</h3></div><strong id="fk-visual-status" role="status">等待案例</strong></div>
        <p id="fk-visual-detail" />
        <div id="fk-visual-rounds" className={styles.visualRounds} />
        <p className={styles.note}>评分来自模型判断，不是图像相似度或工程验收。尚未对齐照片相机；计划通过 Lean 检查，也不代表外观或物理性能通过。</p>
      </section>
      <details className={styles.details}><summary>查看当前案例的假设与待验证事项</summary><div className={styles.detailGrid}><div><h3>设计前提</h3><ul id="fk-assumptions" /></div><div><h3>待验证事项</h3><ul id="fk-gaps" /></div></div></details>
      <noscript><p>三维交互需要 JavaScript。下方操作回放和验证说明仍可查看。</p></noscript>
    </section>
    <section className={`${styles.section} ${styles.recording}`} id="walkthrough" aria-labelledby="walkthrough-title">
      <div className={styles.sectionHead}><p className={styles.label}>02 / 历史归档</p><h2 id="walkthrough-title">保留过程，<br />区分当前与历史。</h2><p>2026 年 9 月 26 日的 47 秒历史回放，展示产品拆解、设备展开与一次参数修订。它尚未包含本次视觉反馈闭环，也不代表实时生成速度。</p></div>
      <details className={styles.details} id="historical-recording"><summary>展开早期操作回放（旧版几何，不代表上方当前案例）</summary><video className={styles.video} controls preload="none" playsInline poster="/fluxkernel/walkthrough-poster.png" aria-label="FluxKernel 47 秒实际操作回放"><source src="/fluxkernel/walkthrough.mp4" type="video/mp4" />浏览器无法播放视频，<a href="/fluxkernel/walkthrough.mp4">下载操作回放</a>。</video></details>
      <div className={styles.runTimes}><span>历史手机案例 <b>47.77 s</b></span><span>汽车 <b>53.39 s</b></span><span>飞机（含一次修正） <b>110.20 s</b></span><span>内部单次运行，非速度承诺</span></div>
    </section>
    <section className={styles.section} id="verification" aria-labelledby="verification-title">
      <div className={styles.sectionHead}><p className={styles.label}>03 / 验证与边界</p><h2 id="verification-title">让结论，<br />对应它的证据。</h2><p>形式化证明、几何检查与物理实验各自承担不同责任。每个结论保留前提和未完成的验证。</p></div>
      <div className={styles.evidenceGrid}>
        <article><span>已实现</span><h3>设计与证据闭环</h3><p>具名零件、独立 STEP/STL、制造依赖和版本轨迹。修改后盖时，40 个产品与设备实体中复用了 39 个。</p></article>
        <article><span>已形式化检查</span><h3>限定范围的工程验证</h3><p>采用 Lean 4 支持限定范围的形式化验证。结果以本次设计、已声明的前提和检查范围为准。</p></article>
        <article><span>仍需工程验证</span><h3>真实制造与整机性能</h3><p>目录型号、材料与打印工艺、设备刚度和精度、刀路、装配配合及最终功能，仍需要供应商证据、仿真和实物试验。</p></article>
      </div>
      <div className={styles.assumption}><strong>演示的制造条件</strong><p>演示假设提供不限成型尺寸的打印资源，聚合物、铝与钢各有对应工艺，并具备原料、电源和基础装配能力。取消成型尺寸限制，不等于取消材料与精度限制。</p></div>
      <div className={styles.closing}><div><p className={styles.label}>BUILD ON A REAL TASK</p><h2>从一个真实产品，<br />开始下一轮研发。</h2></div><div><p>带上产品参考、功能目标和已有制造条件，一起检查哪些设计能复用、哪些环节还需要证据。</p><a className="corp-button primary" href="/talk/">预约完整生成演示 <Arrow /></a><a className={styles.textLink} href="/technology/">返回技术总览 <Arrow /></a></div></div>
      <p className={styles.version}>更新于 2026.09.28 · 机器人 v0.10 · 汽车 v0.6 · 飞机 v0.7 · 工程原型 · <a href="/fluxkernel/release.json">案例与验证记录</a> · <a href="/fluxkernel/photo-sources.json">图片来源</a></p>
    </section>
  </CorporatePage>;
}
