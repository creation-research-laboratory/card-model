/**
 * Static server for the spike.
 *
 * Not a production concern — it exists so the measurements reflect how the app
 * would actually be delivered:
 *
 *   * correct MIME types (a wrong type on .wasm defeats streaming compilation
 *     and inflates boot time, which would make the numbers pessimistic);
 *   * on-the-fly brotli/gzip, because GitHub Pages compresses too, and the
 *     payload figure is meaningless uncompressed — the wasm alone is 9.15 MB
 *     raw against 3.43 MB compressed;
 *   * optional bandwidth throttling via THROTTLE_KBPS, to answer "what does
 *     this cost someone not on office wifi".
 */
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { join, extname, normalize } from "node:path";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync, brotliCompressSync, constants } from "node:zlib";

const root = dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.PORT || 8422);
const THROTTLE_KBPS = Number(process.env.THROTTLE_KBPS || 0);

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".wasm": "application/wasm",
  ".zip": "application/zip",
  ".whl": "application/octet-stream",
  ".py": "text/plain; charset=utf-8",
};

// Compressing the 9 MB wasm on every request would dominate the timings, so
// each encoding is compressed once and reused.
const cache = new Map();

function encode(body, encoding) {
  if (encoding === "br") {
    // Quality 5 rather than the default 11: comparable ratio on this content
    // for a fraction of the CPU, and closer to what a CDN actually serves.
    return brotliCompressSync(body, {
      params: { [constants.BROTLI_PARAM_QUALITY]: 5 },
    });
  }
  if (encoding === "gzip") return gzipSync(body, { level: 6 });
  return body;
}

async function send(res, path, acceptEncoding) {
  const ext = extname(path);
  const type = TYPES[ext] || "application/octet-stream";

  let raw;
  try {
    raw = await readFile(path);
  } catch {
    console.log(`  404  ${path.replace(root, "")}`);
    res.writeHead(404, { "content-type": "text/plain" });
    res.end("not found");
    return;
  }
  console.log(`  200  ${path.replace(root, "")}  (${(raw.length / 1024).toFixed(0)} kB)`);

  // Already-compressed formats gain nothing and cost CPU.
  const compressible = ![".zip", ".whl", ".png", ".woff2"].includes(ext);
  let encoding = "identity";
  if (compressible) {
    if (/\bbr\b/.test(acceptEncoding)) encoding = "br";
    else if (/\bgzip\b/.test(acceptEncoding)) encoding = "gzip";
  }

  // Keyed on size as well as path so editing a file during a session
  // invalidates its compressed copy.  Without this the server happily serves
  // a stale worker.mjs after you have just changed it, and the resulting
  // measurement quietly describes the old code.
  const key = `${path}:${encoding}:${raw.length}`;
  if (!cache.has(key)) cache.set(key, encode(raw, encoding));
  const body = cache.get(key);

  const headers = {
    "content-type": type,
    "content-length": body.length,
    // NO_STORE=1 forces a genuinely cold fetch every load, which is what a
    // first-visit measurement needs.  It is not the default: `no-store` on the
    // 9.4 MB wasm made reloads hang part-way through instantiation in this
    // spike, while a fresh tab was always fine.  Cold numbers come from a
    // fresh tab instead, which is both reliable and closer to a real visit.
    "cache-control": process.env.NO_STORE ? "no-store" : "max-age=60",
  };
  if (encoding !== "identity") headers["content-encoding"] = encoding;
  res.writeHead(200, headers);

  if (!THROTTLE_KBPS) {
    res.end(body);
    return;
  }

  // Crude but adequate: meter the response out in 16 kB chunks at the target
  // rate.  This models bandwidth, not latency or CPU.
  const chunk = 16 * 1024;
  const delayMs = (chunk / (THROTTLE_KBPS * 1024)) * 1000;
  let offset = 0;
  const pump = () => {
    if (offset >= body.length) return res.end();
    res.write(body.subarray(offset, offset + chunk));
    offset += chunk;
    setTimeout(pump, delayMs);
  };
  pump();
}

createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  let pathname = decodeURIComponent(url.pathname);
  if (pathname === "/") pathname = "/index.html";
  // Keep the server inside its own directory.
  const path = join(root, normalize(pathname).replace(/^(\.\.[/\\])+/, ""));
  await send(res, path, req.headers["accept-encoding"] || "");
}).listen(PORT, () => {
  const mode = THROTTLE_KBPS ? `${THROTTLE_KBPS} kB/s` : "unthrottled";
  console.log(`spike server on http://localhost:${PORT}  (${mode})`);
});
