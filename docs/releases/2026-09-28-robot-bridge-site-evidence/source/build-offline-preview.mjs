import {
  copyFileSync,
  readFileSync,
  cpSync,
  mkdirSync,
  rmSync,
  writeFileSync
} from "node:fs";
import { createHash } from "node:crypto";
import { dirname, resolve } from "node:path";

const previewUrl = process.env.FLUXLOOP_PREVIEW_URL ?? "http://127.0.0.1:3000";
const outputDirectory = resolve("offline-preview");
const fluxkernelVersion = createHash("sha256").update(readFileSync("public/fluxkernel/viewer.js")).update(readFileSync("public/fluxkernel/release.json")).digest("hex").slice(0, 16);

const waitlistScript = `
<script>
  document.querySelector(".corp-lead-form")?.addEventListener("submit", function (event) {
    event.preventDefault();
    const form = event.currentTarget;
    const selects = form.querySelectorAll("select");
    const role = selects[0]?.value || "机器人 / 嵌入式开发者";
    const stage = selects[1]?.value || "正在调试，遇到具体问题";
    const hardware = form.querySelector("input")?.value || "待填写";
    const task = form.querySelector("textarea")?.value || "待填写";
    const title = encodeURIComponent(
      "[Early Access] " + role + "｜" + (hardware || "待补充硬件")
    );
    const body = encodeURIComponent([
      "## 使用者",
      "",
      "- 身份：" + role,
      "- 当前阶段：" + stage,
      "- 硬件：" + hardware,
      "",
      "## 希望完成的真实任务",
      "",
      task,
      "",
      "## 隐私提醒",
      "",
      "此 Issue 公开可见；我没有填写手机号、微信、未发布硬件参数或其他保密信息。"
    ].join("\\n"));
    window.location.href =
      "https://github.com/ExuberantWitness/FLUXworkbench/issues/new?title=" +
      title +
      "&body=" +
      body;
  });
</script>`;

const talkPlannerScript = `
<script>
  (function () {
    const planner = document.querySelector(".corp-talk-planner");
    if (!planner) return;

    const selects = planner.querySelectorAll("select");
    const context = planner.querySelector("textarea");
    const preview = planner.querySelector(".corp-message-preview pre");
    const button = planner.querySelector("button");

    function message() {
      return [
        "你好，我想预约一次 DataFlux Dynamics 产品交流。",
        "主题：" + (selects[0]?.value || "Flux Workbench 产品演示"),
        "方便时间：" + (selects[1]?.value || "工作日 09:00—12:00"),
        "背景：" + (context?.value || "待补充"),
        "来自：datafluxdynamics.ltd / Book a chat"
      ].join("\\n");
    }

    function updatePreview() {
      if (preview) preview.textContent = message();
    }

    [...selects, context].filter(Boolean).forEach(function (field) {
      field.addEventListener("input", updatePreview);
      field.addEventListener("change", updatePreview);
    });

    button?.addEventListener("click", async function () {
      const text = message();
      try {
        await navigator.clipboard.writeText(text);
      } catch {
        const helper = document.createElement("textarea");
        helper.value = text;
        helper.style.position = "fixed";
        helper.style.opacity = "0";
        document.body.appendChild(helper);
        helper.select();
        document.execCommand("copy");
        helper.remove();
      }
      button.innerHTML = '已复制，下一步扫码发送 <span aria-hidden="true">↗</span>';
      window.setTimeout(function () {
        button.innerHTML = '复制预约信息 <span aria-hidden="true">↗</span>';
      }, 2200);
    });

    updatePreview();
  })();
</script>`;

const bibtexCopyScript = `
<script>
  (function () {
    document.querySelectorAll("[data-copy-bibtex]").forEach(function (button) {
      button.addEventListener("click", async function () {
        const targetId = button.getAttribute("data-copy-target");
        const source = targetId ? document.getElementById(targetId) : null;
        const text = source?.textContent?.trim();
        if (!text) return;

        try {
          await navigator.clipboard.writeText(text);
        } catch {
          const helper = document.createElement("textarea");
          helper.value = text;
          helper.style.position = "fixed";
          helper.style.opacity = "0";
          document.body.appendChild(helper);
          helper.select();
          document.execCommand("copy");
          helper.remove();
        }

        const label = button.querySelector("span:first-child");
        const icon = button.querySelector("span:last-child");
        const original = button.getAttribute("data-copy-label") || "复制 BibTeX";
        if (label) label.textContent = "已复制 BibTeX";
        if (icon) icon.textContent = "✓";
        button.setAttribute("data-copy-state", "done");
        window.setTimeout(function () {
          if (label) label.textContent = original;
          if (icon) icon.textContent = "↗";
          button.removeAttribute("data-copy-state");
        }, 2200);
      });
    });
  })();
</script>`;

async function buildStaticPage(pathname, assetPrefix, extraScript = "") {
  const pageUrl = new URL(pathname, previewUrl);
  const response = await fetch(pageUrl);
  if (!response.ok) {
    throw new Error(`Unable to read ${pageUrl}: HTTP ${response.status}`);
  }

  let html = await response.text();
  const structuredDataScripts = [
    ...html.matchAll(
      /<script(?=[^>]*type=["']application\/ld\+json["'])[^>]*>[\s\S]*?<\/script>/gi
    )
  ].map((match) => match[0]);
  const stylesheetMatches = [
    ...html.matchAll(
      /<link[^>]+rel="stylesheet"[^>]+href="([^"]+)"[^>]*>/g
    )
  ];

  if (stylesheetMatches.length === 0) {
    throw new Error(`Unable to locate stylesheets for ${pageUrl}`);
  }

  const stylesheets = await Promise.all(
    stylesheetMatches.map(async (match) => {
      const stylesheetUrl = new URL(match[1], pageUrl);
      const stylesheetResponse = await fetch(stylesheetUrl);
      if (!stylesheetResponse.ok) {
        throw new Error(
          `Unable to read ${stylesheetUrl}: HTTP ${stylesheetResponse.status}`
        );
      }
      return stylesheetResponse.text();
    })
  );

  html = html
    .replace(/<link[^>]+rel="stylesheet"[^>]*>/g, "")
    .replace(/<link[^>]+rel="modulepreload"[^>]*>/g, "")
    .replace(/<script[\s\S]*?<\/script>/g, "")
    .replaceAll('src="/media/', `src="${assetPrefix}media/`)
    .replaceAll('poster="/media/', `poster="${assetPrefix}media/`)
    .replaceAll('href="/media/', `href="${assetPrefix}media/`)
    .replace(
      /href="\/icon\.svg[^"]*"/,
      `href="${assetPrefix}icon.svg"`
    )
    .replace(
      "</head>",
      `${structuredDataScripts.join("\n")}<style>${stylesheets.join("\n")}</style></head>`
    );

  const localRoutes = [
    "research/mechanogenesisbench",
    "research/machines-that-accelerate-machine-making",
    "technology/fluxprsi",
    "technology/fluxkernel",
    "technology/mechanogenesis",
    "technology/edge-model",
    "platform",
    "products",
    "technology",
    "research",
    "contact",
    "evidence",
    "company",
    "fluxworkbench",
    "fluxnode",
    "devready",
    "waitlist",
    "talk",
    "en"
  ];

  html = html.replace(/href="\/(#[^"]*)?"/g, (_match, hash = "") =>
    `href="${assetPrefix}index.html${hash}"`
  );

  for (const route of localRoutes) {
    html = html.replace(
      new RegExp(`href="/${route}/(#[^"]*)?"`, "g"),
      (_match, hash = "") =>
        `href="${assetPrefix}${route}/index.html${hash}"`
    );
  }

  if (extraScript) {
    html = html.replace("</body>", `${extraScript}</body>`);
  }

  return html;
}

const staticPages = [
  { pathname: "/", output: "index.html", assetPrefix: "" },
  {
    pathname: "/en/",
    output: "en/index.html",
    assetPrefix: "../"
  },
  {
    pathname: "/platform/",
    output: "platform/index.html",
    assetPrefix: "../"
  },
  {
    pathname: "/products/",
    output: "products/index.html",
    assetPrefix: "../"
  },
  {
    pathname: "/technology/",
    output: "technology/index.html",
    assetPrefix: "../"
  },
  {
    pathname: "/technology/fluxprsi/",
    output: "technology/fluxprsi/index.html",
    assetPrefix: "../../"
  },
  {
    pathname: "/technology/fluxkernel/",
    output: "technology/fluxkernel/index.html",
    assetPrefix: "../../",
    extraScript: `<script type="module" src="/fluxkernel/viewer.js?v=${fluxkernelVersion}"></script>`
  },
  {
    pathname: "/technology/mechanogenesis/",
    output: "technology/mechanogenesis/index.html",
    assetPrefix: "../../"
  },
  {
    pathname: "/technology/edge-model/",
    output: "technology/edge-model/index.html",
    assetPrefix: "../../"
  },
  {
    pathname: "/research/",
    output: "research/index.html",
    assetPrefix: "../"
  },
  {
    pathname: "/research/mechanogenesisbench/",
    output: "research/mechanogenesisbench/index.html",
    assetPrefix: "../../",
    extraScript: bibtexCopyScript
  },
  {
    pathname: "/research/machines-that-accelerate-machine-making/",
    output: "research/machines-that-accelerate-machine-making/index.html",
    assetPrefix: "../../",
    extraScript: bibtexCopyScript
  },
  {
    pathname: "/contact/",
    output: "contact/index.html",
    assetPrefix: "../"
  },
  {
    pathname: "/evidence/",
    output: "evidence/index.html",
    assetPrefix: "../"
  },
  {
    pathname: "/company/",
    output: "company/index.html",
    assetPrefix: "../"
  },
  {
    pathname: "/fluxworkbench/",
    output: "fluxworkbench/index.html",
    assetPrefix: "../"
  },
  {
    pathname: "/fluxnode/",
    output: "fluxnode/index.html",
    assetPrefix: "../"
  },
  {
    pathname: "/devready/",
    output: "devready/index.html",
    assetPrefix: "../"
  },
  {
    pathname: "/waitlist/",
    output: "waitlist/index.html",
    assetPrefix: "../",
    extraScript: waitlistScript
  },
  {
    pathname: "/talk/",
    output: "talk/index.html",
    assetPrefix: "../",
    extraScript: talkPlannerScript
  }
];

rmSync(outputDirectory, { recursive: true, force: true });
mkdirSync(outputDirectory, { recursive: true });
cpSync(resolve("public/media"), resolve(outputDirectory, "media"), {
  recursive: true
});
cpSync(resolve("public/research"), resolve(outputDirectory, "research"), {
  recursive: true
});
copyFileSync(resolve("app/icon.svg"), resolve(outputDirectory, "icon.svg"));

for (const page of staticPages) {
  const target = resolve(outputDirectory, page.output);
  const html = await buildStaticPage(
    page.pathname,
    page.assetPrefix,
    page.extraScript
  );
  mkdirSync(dirname(target), { recursive: true });
  writeFileSync(target, html);
  console.log(`${page.pathname} -> ${target}`);
}

writeFileSync(resolve(outputDirectory, "CNAME"), "www.datafluxdynamics.ltd\n");
writeFileSync(resolve(outputDirectory, ".nojekyll"), "");

cpSync(resolve("public/fluxkernel"), resolve(outputDirectory, "fluxkernel"), { recursive: true });
