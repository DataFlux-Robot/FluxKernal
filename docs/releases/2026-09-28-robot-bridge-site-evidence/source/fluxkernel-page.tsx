import type { Metadata } from "next";
import { Arrow, CorporatePage } from "../../_components/CorporateChrome";
import styles from "./fluxkernel.module.css";

export const metadata: Metadata = {
  title: "FluxKernel — 从产品图片到制造计划 | 数瀚衍动",
  description: "FluxKernel 原生机器人模型已接通 Lean 4 结构检查与 URDF/MJCF 导出，经 Microduck、XGO 及个性化变体验证。结合 GLM-5.3-Flash 的有限轮 Perception–Action Loop，连接设计、制造与证据。",
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
        <div className={styles.experimentBadges} aria-label="本次演示的模型与迭代预算"><span>模型 <b>GLM-5.3-Flash</b></span><span>机制 <b>Perception–Action Loop</b></span><span>汽车 / 飞机 <b>3 轮评审 · 2 次候选修订</b></span></div>
        <p className={styles.experimentScope}>当前展示有限迭代预算下的中间结果：观察系统如何发现问题、修订设计并保留候选。外观与工程性能仍需继续验证。</p>
        <div className={styles.actions}>
          <a className="corp-button primary" href="#interactive">探索三维案例 <span aria-hidden="true">↓</span></a>
          <a className="corp-button outline-light" href="#robot-bridge">查看 Lean / URDF 链路 <Arrow /></a>
        </div>
      </div>
      <figure className={styles.flow} aria-label="从图片到设备和证据的研发路径">
        <figcaption>PERCEPTION → ACTION → EVALUATION</figcaption>
        <ol>{flow.map(([n,title,body]) => <li key={n}><span>{n}</span><div><strong>{title}</strong><p>{body}</p></div></li>)}</ol>
        <div className={styles.flowFoot}>本次汽车 / 飞机：初始评审 + 两次候选修订。</div>
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
      <div className={styles.sectionHead}><p className={styles.label}>NEW / 原生机器人 · v0.10</p><h2 id="robot-bridge-title">同一份设计，<br />接通 Lean 与 URDF。</h2><p>Microduck 与 XGO 已进入 FluxKernel 原生模型。结构证明与交换文件来自同一版本；修改设计后，重新生成 Lean 检查与 URDF / MJCF，并使旧的控制适用性证据失效。</p></div>
      <div className={styles.robotBridge} aria-label="源模型进入原生模型，再分别生成 Lean 证明与 URDF/MJCF">
        <div className={styles.robotAuthority}><span>设计源 · robot.json</span><h3>FluxKernel 原生机器人</h3><p>刚体 / 关节 / 惯量 / 几何<br />来源 / 需求 / 控制绑定 / 版本证据</p></div>
        <div className={styles.robotBranches}>
          <article><span>01 / 形式化分支</span><h3>Lean 4 结构检查</h3><p>检查身份唯一、父子无环、关节引用与限位、驱动覆盖和控制绑定。检查由真实 Lean 4 工具链执行。</p></article>
          <article><span>02 / 交换分支</span><h3>URDF / MJCF 导出</h3><p>从原生数据生成机械模型，并在三个配置下对照坐标、质心、质量、惯量及网格位置。当前是数值回归验证。</p></article>
        </div>
      </div>
      <div className={styles.robotStatus} aria-label="链路实现状态">
        <p><b>已跑通</b><span>原生模型 → Lean 结构证明 + URDF / MJCF 导出；修改后重新生成与复检。</span></p>
        <p><b>下一步</b><span>通用 URDF 导入、导出语义保持的形式化证明。当前尚未实现 Lean ↔ URDF 双向无损转换。</span></p>
      </div>
      <div className={styles.robotCases}>
        <article><a href="/fluxkernel/native-robots/microduck-head.png"><img src="/fluxkernel/native-robots/microduck-head.png" width="1024" height="816" loading="lazy" alt="Microduck 原机器人与 GLM 设计的黄色头顶附加装饰件四视图" /></a><div><span>MICRODUCK / 模型选择第 1 轮</span><h3>保留机构，添加个性化零件。</h3><p>GLM 调用 4 次 · 新增估算质量 2.06 g。原模型保持不变，变体通过 Lean 复检及 URDF / MJCF 数值一致性检查。</p></div></article>
        <article><a href="/fluxkernel/native-robots/xgoduck-head.png"><img src="/fluxkernel/native-robots/xgoduck-head.png" width="1024" height="816" loading="lazy" alt="XGO Duck 原机器人与 GLM 设计的黄色头顶附加装饰件四视图" /></a><div><span>XGO DUCK / 模型选择第 3 轮</span><h3>修订有边界，失败有记录。</h3><p>GLM 调用 9 次 · 新增估算质量 2.15 g。两台变体各检查 31 个姿态的间隙；采样检查不等于连续运动或实际安装验证。</p></div></article>
      </div>
      <div className={styles.budgetContext}><div><span>个性化零件实验条件</span><strong>GLM-5.3-Flash · Perception–Action Loop · 最多 3 轮</strong></div><p>造型、修订和最终选择均由模型完成；系统执行几何、冻结约束与证据检查。展示的是小型附加外观件原型，模型评价并非独立外观验收。</p></div>
      <p className={styles.note}>Lean 当前不证明网格几何、运动学导出等价或实机稳定性；.lean 结构记录不能独立还原完整 URDF。URDF 主要用于显示与运动学交换，部分执行器限制仍待补齐。安装贴合、相机视场、打印工艺及行走性能尚未验证。</p>
      <div className={styles.robotLinks}><a href="/fluxkernel/native-robots/evidence.json">查看验证摘要 <Arrow /></a><a href="/fluxkernel/native-robots/sources.json">模型来源与许可 <Arrow /></a><a href="#interactive">继续探索产品与加工设备 <Arrow /></a></div>
    </section>
    <section className={styles.section} id="interactive" aria-labelledby="interactive-title">
      <div className={styles.sectionHead}><p className={styles.label}>01 / 真实运行 · 交互查看</p><h2 id="interactive-title">从外形，<br />走进制造层级。</h2><p>选择产品，查看有限预算下保留的候选，再向下对比每轮变化。汽车和飞机均由 GLM-5.3-Flash 完成三轮评审；手机为早期生成记录。新图片生成由研发后端执行。</p></div>
      <div className={styles.budgetContext}><div><span>本次实验条件</span><strong>Perception–Action Loop × GLM-5.3-Flash</strong></div><p id="fk-budget-context">汽车 / 飞机：3 轮评审（初始 + 2 次候选修订）。展示预算结束时保留的中间方案，尚未达到外观验收门槛；手机为早期记录。</p></div>
      <div className={styles.caseTabs} role="group" aria-label="选择案例">
        <button data-fk-case="phone" aria-pressed="true"><span>01</span> 手机 <small>20 个产品件 · 早期记录</small></button>
        <button data-fk-case="car" aria-pressed="false"><span>02</span> 汽车 <small>29 个产品件 · 3 轮评审</small></button>
        <button data-fk-case="aircraft" aria-pressed="false"><span>03</span> 飞机 <small>32 个产品件 · 3 轮评审</small></button>
      </div>
      <div className={styles.explorer}>
        <div className={styles.stage}>
          <div className={styles.stageTop}><div className={styles.switches} role="group" aria-label="查看层级"><button data-fk-view="product" aria-pressed="true">产品设计</button><button data-fk-view="equipment" aria-pressed="false">加工设备 M₁</button></div><span id="fk-run-status" role="status">正在载入真实案例</span></div>
          <div className={styles.canvasWrap}><canvas id="fk-canvas" aria-label="可旋转、缩放和选择零件的三维概念模型" /><div className={styles.canvasCaption}><span id="fk-case-title">手机制造概念</span><small>参数化概念几何 · 毫米坐标</small></div><img id="fk-input-image" className={styles.inputImage} src="/fluxkernel/phone-input.png" alt="本次运行的产品参考图片" /><button id="fk-fit" className={styles.fit} aria-label="适配三维视图">⤢</button><p id="fk-view-error" className={styles.viewerError} hidden /></div>
          <div className={styles.stageBottom}><label htmlFor="fk-explode">装配 <input id="fk-explode" type="range" min="0" max="100" defaultValue="0" /> 爆炸</label><span>拖动旋转 · 滚轮缩放 · 点击选件</span></div>
        </div>
        <aside className={styles.parts}><div className={styles.partsHead}>零件与制造路线 <span id="fk-part-count">20 件</span></div><div id="fk-parts" className={styles.partList} /><div id="fk-inspector" className={styles.inspector}><span>PART INSPECTOR</span><h3>选择一个零件</h3><p>查看它的材料、尺寸、来源和制造路线。</p></div></aside>
      </div>
      <div className={styles.proofStrip}><div><span>LEAN 4 / ACTUAL PLAN CHECK</span><strong id="fk-proof-status">条件化制造计划</strong></div><p id="fk-proof-detail">检查本次实际计划的依赖与路线，不替代材料、工艺、装配和整机性能验证。</p><a href="#verification">理解验证范围 <Arrow /></a></div>
      <p className={styles.note}>三维模型为候选工程架构。采购件显示布局包络，加工件显示毛坯；它们不是对原产品全部隐藏结构的复刻。</p>
      <section className={styles.perception} aria-labelledby="fk-perception-title">
        <div className={styles.perceptionHead}><div><p className={styles.label}>PERCEPTION–ACTION LOOP · 有限次迭代</p><h3 id="fk-perception-title">三轮之内，记录每次修改与取舍。</h3></div><strong id="fk-visual-status" role="status">等待案例</strong></div>
        <p id="fk-visual-detail" />
        <div id="fk-visual-rounds" className={styles.visualRounds} />
        <p className={styles.note}>评分来自模型判断，不是图像相似度或工程验收。尚未对齐照片相机；计划通过 Lean 检查，也不代表外观或物理性能通过。</p>
      </section>
      <details className={styles.details}><summary>查看当前案例的假设与待验证事项</summary><div className={styles.detailGrid}><div><h3>设计前提</h3><ul id="fk-assumptions" /></div><div><h3>待验证事项</h3><ul id="fk-gaps" /></div></div></details>
      <noscript><p>三维交互需要 JavaScript。下方操作回放和验证说明仍可查看。</p></noscript>
    </section>
    <section className={`${styles.section} ${styles.recording}`} id="walkthrough" aria-labelledby="walkthrough-title">
      <div className={styles.sectionHead}><p className={styles.label}>02 / 操作回放</p><h2 id="walkthrough-title">设计有过程，<br />结果可追溯。</h2><p>2026 年 9 月 26 日的 47 秒历史回放，展示产品拆解、设备展开与一次参数修订。它尚未包含本次视觉反馈闭环，也不代表实时生成速度。</p></div>
      <video className={styles.video} controls preload="none" playsInline poster="/fluxkernel/walkthrough-poster.png" aria-label="FluxKernel 47 秒实际操作回放"><source src="/fluxkernel/walkthrough.mp4" type="video/mp4" />浏览器无法播放视频，<a href="/fluxkernel/walkthrough.mp4">下载操作回放</a>。</video>
      <div className={styles.runTimes}><span>历史手机案例 <b>47.77 s</b></span><span>汽车 <b>53.39 s</b></span><span>飞机（含一次修正） <b>110.20 s</b></span><span>内部单次运行，非速度承诺</span></div>
    </section>
    <section className={styles.section} id="verification" aria-labelledby="verification-title">
      <div className={styles.sectionHead}><p className={styles.label}>03 / 验证与边界</p><h2 id="verification-title">让结论，<br />对应它的证据。</h2><p>形式化证明、几何检查与物理实验各自承担不同责任。每个结论保留前提和未完成的验证。</p></div>
      <div className={styles.evidenceGrid}>
        <article><span>已实现</span><h3>设计与证据闭环</h3><p>具名零件、独立 STEP/STL、制造依赖和版本轨迹。修改后盖时，40 个产品与设备实体中复用了 39 个。</p></article>
        <article><span>已形式化检查</span><h3>有限制造计划闭合</h3><p>Lean 4 核验依赖先后、禁止自举、路线类型、设备展开深度和产品覆盖。证据来自实际计划，不是固定证明示例。</p></article>
        <article><span>仍需工程验证</span><h3>真实制造与整机性能</h3><p>目录型号、材料与打印工艺、设备刚度和精度、刀路、装配配合及最终功能，仍需要供应商证据、仿真和实物试验。</p></article>
      </div>
      <div className={styles.assumption}><strong>明确的初始能力 K₀</strong><p>演示假设提供不限成型尺寸的打印资源，聚合物、铝与钢各有对应工艺，并具备原料、电源和基础装配能力。取消成型尺寸限制，不等于取消材料与精度限制。</p></div>
      <div className={styles.closing}><div><p className={styles.label}>BUILD ON A REAL TASK</p><h2>从一个真实产品，<br />开始下一轮研发。</h2></div><div><p>带上产品参考、功能目标和已有制造条件，一起检查哪些设计能复用、哪些环节还需要证据。</p><a className="corp-button primary" href="/talk/">预约完整生成演示 <Arrow /></a><a className={styles.textLink} href="/technology/">返回技术总览 <Arrow /></a></div></div>
      <p className={styles.version}>更新于 2026.09.28 · 原生机器人 v0.10 / 图片案例 v0.5 · 工程原型 · <a href="/fluxkernel/release.json">案例与验证记录</a> · <a href="/fluxkernel/photo-sources.json">图片来源</a></p>
    </section>
  </CorporatePage>;
}
