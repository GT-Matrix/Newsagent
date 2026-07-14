import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

const manifestPath = process.argv[2] || "data/output/news_cards/manifest.json";
const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
const chrome = process.env.CHROME_BIN || findChrome();

if (!chrome) {
  console.error("Chrome/Chromium was not found. Set CHROME_BIN or install chromium/google-chrome.");
  process.exit(2);
}

for (const item of manifest.items || []) {
  const htmlPath = path.resolve(item.html_path);
  const pngPath = path.resolve(item.png_path);
  fs.mkdirSync(path.dirname(pngPath), { recursive: true });
  const result = spawnSync(
    chrome,
    [
      "--headless=new",
      "--no-sandbox",
      "--disable-gpu",
      "--hide-scrollbars",
      "--force-device-scale-factor=1",
      "--window-size=1200,675",
      `--screenshot=${pngPath}`,
      pathToFileURL(htmlPath).href,
    ],
    { stdio: "inherit" },
  );
  if (result.status !== 0) {
    process.exit(result.status || 1);
  }
  item.png_path = path.relative(process.cwd(), pngPath).replaceAll(path.sep, "/");
}

fs.writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
console.log(`Rendered ${(manifest.items || []).length} PNG image(s) with ${chrome}`);

function findChrome() {
  const names =
    os.platform() === "win32"
      ? [
          "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
          "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
          path.join(process.env.LOCALAPPDATA || "", "Google\\Chrome\\Application\\chrome.exe"),
        ]
      : [
          "/usr/bin/chromium-browser",
          "/usr/bin/chromium",
          "/usr/bin/google-chrome",
          "/usr/bin/google-chrome-stable",
          "/snap/bin/chromium",
          "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ];
  return names.find((name) => name && fs.existsSync(name)) || "";
}
