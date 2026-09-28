import type { Metadata } from "next";
import styles from "./technology.module.css";
import {
  Arrow,
  CorporatePage,
  PageHero,
  SectionLabel
} from "../_components/CorporateChrome";

export const metadata: Metadata = {
  title: "核心技术 — DataFlux Dynamics 数瀚衍动",
  description:
    "FluxPRSI、FluxKernel、Mechanogenesis Engine 与端侧模型：从研发策略、设计制造到仿真与现场执行。"
};

const technologies = [
  {
    index: "01",
    status: "已形成运行基础与效果证据",
    title: "FluxPRSI",
    subtitle: "Physical Recursive Self-Improvement",
    body: "把真实状态、可执行世界模型、实验策略与独立证据连成闭环，让每次真实研发都加速下一次研发。",
    proof: "约一周 → 十几分钟 → 资产复用后数秒",
    href: "/technology/fluxprsi/",
    tone: "blue"
  },
  {
    index: "02",
    status: "可运行工程原型",
    title: "FluxKernel",
    subtitle: "Verified design · Robot customization",
    body: "结合 Lean 4 形式化验证与 URDF/MJCF 导出，通过有限轮视觉反馈，推进产品拆解与机器人个性化设计。",
    proof: "Microduck / XGO 链路已验证 · 272 项本地测试",
    href: "/technology/fluxkernel/",
    tone: "light"
  },
  {
    index: "03",
    status: "正在开发",
    title: "Mechanogenesis Engine",
    subtitle: "Constructive simulation & research kernel",
    body: "为 Agent 提供可构造、可修改、可验证且不可自证成功的物理世界，连接机器设计、仿真与实验反馈。",
    proof: "核心原型 · 形式化验证 · 100 余项自动测试",
    href: "/technology/mechanogenesis/",
    tone: "dark"
  },
  {
    index: "04",
    status: "COMING SOON",
    title: "PRSI 端侧模型",
    subtitle: "Edge model for physical research",
    body: "在设备现场低延迟理解结构化上下文、观察真实状态并执行受约束动作，让持续适配发生在物理世界边缘。",
    proof: "本地上下文 · 工具编排 · 证据门控更新",
    href: "/technology/edge-model/",
    tone: "light"
  }
];

export default function TechnologyPage() {
  return (
    <CorporatePage active="technology">
      <PageHero
        index="03"
        eyebrow="FOUR TECHNOLOGIES / ONE PRSI LOOP"
        title={
          <>
            四条技术路线，
            <br />
            共同指向
            <br />
            <em>物理递归自改进。</em>
          </>
        }
        lead="从 FluxPRSI 的研发策略，到 FluxKernel 的设计与制造计划、Mechanogenesis 的构造式仿真，再到设备现场的端侧模型。选择一条路线进入详细页面。"
      />

      <section className="technology-catalog" aria-labelledby="technology-catalog-title">
        <div className="corp-catalog-head">
          <SectionLabel>TECHNOLOGY SYSTEM / 01—04</SectionLabel>
          <h2 id="technology-catalog-title">先看全局，再按兴趣进入技术细节。</h2>
          <p>
            技术总览只负责说明四项技术各自解决什么问题；架构、证据、成熟度和路线图放在对应子页面。
          </p>
        </div>

        <div className={`technology-catalog-grid ${styles.grid}`}>
          {technologies.map((technology) => (
            <a
              className={`technology-catalog-card ${technology.tone}`}
              href={technology.href}
              key={technology.title}
            >
              <div>
                <span>{technology.index}</span>
                <small>{technology.status}</small>
              </div>
              <p>{technology.subtitle}</p>
              <h3>{technology.title}</h3>
              <strong>{technology.body}</strong>
              <b>{technology.proof}</b>
              <em>
                进入技术专页 <Arrow />
              </em>
            </a>
          ))}
        </div>

        <div className={`technology-catalog-loop ${styles.loop}`} aria-label="四项技术的关系">
          <span>FLUXPRSI · 决定如何研究与改进</span>
          <i>→</i>
          <span>FLUXKERNEL · 拆解设计与制造路径</span>
          <i>→</i>
          <span>MECHANOGENESIS · 提供可执行物理世界</span>
          <i>→</i>
          <span>EDGE MODEL · 把能力带到设备现场</span>
        </div>
      </section>
    </CorporatePage>
  );
}
