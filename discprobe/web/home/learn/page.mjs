import { lightingDiagram } from "../lighting-diagram.mjs";

const root = document.documentElement;
let theme = new URLSearchParams(location.search).get("theme");
try { theme ??= localStorage.getItem("dp-theme"); } catch {}
root.dataset.theme = theme === "dark" || theme === "light" ? theme
  : matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
document.querySelectorAll("a[data-doc]").forEach(link => {
  const url = new URL(link.href);
  url.searchParams.set("theme", root.dataset.theme);
  link.href = url.href;
});
const example = document.querySelector(".learn-diagram");
if (example) {
  const chinese = root.lang === "zh-CN";
  example.innerHTML = lightingDiagram(chinese ? "小灯、盘面和眼睛位置的示意图" : "Diagram of the small light, disc surface and eye",
    chinese ? "图案" : "picture");
}
