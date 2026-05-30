/**
 * Build Python backend with PyInstaller, producing a standalone api.exe.
 *
 * Output: src-tauri/python-dist/api/api.exe + all dependencies
 * This replaces copy-python.cjs in the Tauri build pipeline.
 */
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const https = require('https');
const zlib = require('zlib');

const rootDir = path.resolve(__dirname, '..');
const specFile = path.join(rootDir, 'scripts', 'api.spec');
const outputBase = path.join(rootDir, 'src-tauri', 'python-dist');
const apiExePath = path.join(outputBase, 'api', 'api.exe');

// Persistent local cache for downloaded build tools (pandoc.exe, tectonic.exe).
// Lives OUTSIDE python-dist (which PyInstaller wipes on --clean). Lets the build
// work on networks that can't reach GitHub releases (e.g. behind GFW): drop the
// exe here once and every future build copies it instead of downloading.
const TOOLS_CACHE = path.join(rootDir, 'scripts', '.tools-cache');

// Try to satisfy a bundled tool from the local cache. Returns true if copied.
function provisionFromCache(name, destExe) {
  const cached = path.join(TOOLS_CACHE, name);
  if (fs.existsSync(cached)) {
    fs.mkdirSync(path.dirname(destExe), { recursive: true });
    fs.copyFileSync(cached, destExe);
    console.log(`[INFO] ${name} provisioned from local cache.`);
    return true;
  }
  return false;
}

// Save a freshly-downloaded tool into the cache for future offline builds.
function saveToCache(name, srcExe) {
  try {
    fs.mkdirSync(TOOLS_CACHE, { recursive: true });
    fs.copyFileSync(srcExe, path.join(TOOLS_CACHE, name));
  } catch (_) {}
}

// ── Tectonic bundling ──────────────────────────────────────────────
const TECTONIC_URL = 'https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.16.9/tectonic-0.16.9-x86_64-pc-windows-msvc.zip';
const TECTONIC_VERSION = '0.16.9';

// ── Pandoc bundling (Markdown -> LaTeX/PDF export) ─────────────────
const PANDOC_VERSION = '3.6.2';
const PANDOC_URL = `https://github.com/jgm/pandoc/releases/download/${PANDOC_VERSION}/pandoc-${PANDOC_VERSION}-windows-x86_64.zip`;

// ── Embedding model bundling (chromadb RAG / 文献库, offline-capable) ──
// chromadb's DefaultEmbeddingFunction downloads all-MiniLM-L6-v2 from S3 on
// first use; bundling it lets 文献库 work offline on a fresh machine.
const EMBED_MODEL_URL = 'https://chroma-onnx-models.s3.amazonaws.com/all-MiniLM-L6-v2/onnx.tar.gz';

function downloadFile(url, dest, timeoutMs = 45000) {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(dest);
    const req = https.get(url, (res) => {
      if (res.statusCode === 302 || res.statusCode === 301) {
        const redirectUrl = res.headers.location;
        const req2 = https.get(redirectUrl, (res2) => {
          if (res2.statusCode !== 200) {
            file.close();
            try { fs.unlinkSync(dest); } catch (_) {}
            reject(new Error(`HTTP ${res2.statusCode} on redirect`));
            return;
          }
          res2.pipe(file);
          file.on('finish', () => { file.close(); resolve(); });
        });
        req2.on('error', (e) => { try { file.close(); fs.unlinkSync(dest); } catch (_) {} reject(e); });
        return;
      }
      if (res.statusCode !== 200) {
        file.close();
        try { fs.unlinkSync(dest); } catch (_) {}
        reject(new Error(`HTTP ${res.statusCode}`));
        return;
      }
      res.pipe(file);
      file.on('finish', () => { file.close(); resolve(); });
    });
    req.on('error', (e) => { try { file.close(); fs.unlinkSync(dest); } catch (_) {} reject(e); });
    // Timeout the request
    const timer = setTimeout(() => {
      req.destroy();
      try { file.close(); fs.unlinkSync(dest); } catch (_) {}
      reject(new Error('Download timeout'));
    }, timeoutMs);
    req.on('response', () => clearTimeout(timer));
    req.on('close', () => clearTimeout(timer));
  });
}

async function downloadTectonic(apiDir) {
  const toolsDir = path.join(apiDir, 'tools');
  const tectonicExe = path.join(toolsDir, 'tectonic.exe');
  if (fs.existsSync(tectonicExe)) {
    console.log('[INFO] Tectonic already bundled, skipping download.');
    return;
  }
  if (provisionFromCache('tectonic.exe', tectonicExe)) return;
  fs.mkdirSync(toolsDir, { recursive: true });
  const tmpZip = path.join(apiDir, 'tectonic.zip');
  console.log(`[INFO] Downloading Tectonic ${TECTONIC_VERSION}...`);
  try {
    await downloadFile(TECTONIC_URL, tmpZip);
    // Extract using Python (available in dev env)
    const pythonCmd = process.platform === 'win32' ? 'python' : 'python3';
    const extractScript = `
import zipfile, os, sys
zip_path, tools_dir, dest = sys.argv[1], sys.argv[2], sys.argv[3]
with zipfile.ZipFile(zip_path, 'r') as z:
    for entry in z.namelist():
        info = z.getinfo(entry)
        if not info.is_dir() and entry.lower().endswith('.exe'):
            z.extract(entry, tools_dir)
            src = os.path.join(tools_dir, os.path.basename(entry))
            if src != dest and os.path.exists(src):
                os.rename(src, dest)
            break
`;
    const { error } = require('child_process').spawnSync(pythonCmd, [
      '-c', extractScript, tmpZip, toolsDir, tectonicExe,
    ], { encoding: 'utf8' });
    if (error) {
      console.warn(`[WARN] Python extraction failed: ${error}`);
    }
    fs.unlinkSync(tmpZip);
    if (fs.existsSync(tectonicExe)) {
      console.log('[INFO] Tectonic bundled successfully.');
      saveToCache('tectonic.exe', tectonicExe);
    }
  } catch (e) {
    console.warn(`[WARN] Failed to bundle Tectonic: ${e.message}. Drop tectonic.exe into scripts/.tools-cache/ to bundle it offline.`);
    try { fs.unlinkSync(tmpZip); } catch (_) {}
  }
}

async function downloadPandoc(apiDir) {
  const toolsDir = path.join(apiDir, 'tools');
  const pandocExe = path.join(toolsDir, 'pandoc.exe');
  if (fs.existsSync(pandocExe)) {
    console.log('[INFO] Pandoc already bundled, skipping download.');
    return;
  }
  if (provisionFromCache('pandoc.exe', pandocExe)) return;
  fs.mkdirSync(toolsDir, { recursive: true });
  const tmpZip = path.join(apiDir, 'pandoc.zip');
  console.log(`[INFO] Downloading Pandoc ${PANDOC_VERSION}...`);
  try {
    await downloadFile(PANDOC_URL, tmpZip);
    // Pandoc zip nests the exe under pandoc-<ver>/pandoc.exe — match by basename.
    const extractScript = `
import zipfile, os, sys
zip_path, tools_dir, dest = sys.argv[1], sys.argv[2], sys.argv[3]
with zipfile.ZipFile(zip_path, 'r') as z:
    for entry in z.namelist():
        info = z.getinfo(entry)
        if not info.is_dir() and os.path.basename(entry).lower() == 'pandoc.exe':
            z.extract(entry, tools_dir)
            src = os.path.join(tools_dir, *entry.split('/'))
            if os.path.normpath(src) != os.path.normpath(dest) and os.path.exists(src):
                os.replace(src, dest)
            break
`;
    const pythonCmd = process.platform === 'win32' ? 'python' : 'python3';
    const { error } = require('child_process').spawnSync(pythonCmd, [
      '-c', extractScript, tmpZip, toolsDir, pandocExe,
    ], { encoding: 'utf8' });
    if (error) {
      console.warn(`[WARN] Python extraction failed: ${error}`);
    }
    fs.unlinkSync(tmpZip);
    if (fs.existsSync(pandocExe)) {
      console.log('[INFO] Pandoc bundled successfully.');
      saveToCache('pandoc.exe', pandocExe);
    }
  } catch (e) {
    console.warn(`[WARN] Failed to bundle Pandoc: ${e.message}. Drop pandoc.exe into scripts/.tools-cache/ to bundle it offline.`);
    try { fs.unlinkSync(tmpZip); } catch (_) {}
  }
}

async function prewarmTectonic(apiDir) {
  // Compile a few representative docs so Tectonic fetches the common LaTeX
  // support files into a cache we bundle — PDF export then works offline.
  // Tectonic caches each file as it's fetched, so even a doc that ultimately
  // errors still warms the cache for everything it pulled first.
  const tectonicExe = path.join(apiDir, 'tools', 'tectonic.exe');
  if (!fs.existsSync(tectonicExe)) {
    console.warn('[WARN] Tectonic not bundled; skipping LaTeX cache pre-warm.');
    return;
  }
  const cacheDir = path.join(apiDir, 'tectonic-cache');
  fs.mkdirSync(cacheDir, { recursive: true });

  // Fast path: seed from a previously-saved cache (avoids slow network fetches,
  // works offline / behind GFW). Populate scripts/.tools-cache/tectonic-cache/
  // once and every build reuses it.
  const cachedTexCache = path.join(TOOLS_CACHE, 'tectonic-cache');
  if (fs.existsSync(path.join(cachedTexCache, 'formats')) || fs.existsSync(path.join(cachedTexCache, 'bundles'))) {
    fs.cpSync(cachedTexCache, cacheDir, { recursive: true });
    let mb = 0;
    try {
      const walk = (d) => { for (const e of fs.readdirSync(d, { withFileTypes: true })) {
        const p = path.join(d, e.name); if (e.isDirectory()) walk(p); else mb += fs.statSync(p).size; } };
      walk(cacheDir); mb = mb / 1024 / 1024;
    } catch (_) {}
    console.log(`[INFO] Tectonic cache provisioned from local cache: ${mb.toFixed(1)} MB (skipping network pre-warm).`);
    return;
  }

  const warmDir = fs.mkdtempSync(path.join(require('os').tmpdir(), 'tecwarm-'));

  // Union of packages used across the shipped templates + the heavy journal
  // document classes. Compiled separately (one doc class per file).
  const docs = {
    'standard.tex':
      '\\documentclass[11pt]{article}\n' +
      '\\usepackage[utf8]{inputenc}\\usepackage{etoolbox}\\usepackage{amsmath,amssymb}\n' +
      '\\usepackage{framed}\\usepackage{graphicx}\\usepackage{hyperref}\\usepackage{geometry}\n' +
      '\\usepackage{fancyhdr}\\usepackage{booktabs}\\usepackage{xcolor}\\usepackage{caption}\n' +
      '\\usepackage{multirow}\\usepackage{url}\\usepackage{microtype}\\usepackage{glossaries}\n' +
      '\\begin{document}Warm $E=mc^2$\\end{document}\n',
    'ieee.tex': '\\documentclass{IEEEtran}\\begin{document}Warm\\end{document}\n',
    'acm.tex': '\\documentclass{acmart}\\begin{document}Warm\\end{document}\n',
    'lncs.tex': '\\documentclass{llncs}\\begin{document}Warm\\end{document}\n',
    'elsevier.tex': '\\documentclass{elsarticle}\\begin{document}Warm\\end{document}\n',
  };

  const env = { ...process.env, TECTONIC_CACHE_DIR: cacheDir };
  console.log('[INFO] Pre-warming Tectonic LaTeX cache (offline PDF support)...');
  for (const [name, src] of Object.entries(docs)) {
    const texPath = path.join(warmDir, name);
    fs.writeFileSync(texPath, src, 'utf8');
    try {
      const r = require('child_process').spawnSync(
        tectonicExe, ['-X', 'compile', '--keep-intermediates', name],
        { cwd: warmDir, env, encoding: 'utf8', timeout: 240000, stdio: 'pipe' }
      );
      if (r.status === 0) {
        console.log(`[INFO]   warmed: ${name}`);
      } else {
        console.log(`[INFO]   partial warm (non-fatal): ${name}`);
      }
    } catch (e) {
      console.warn(`[WARN]   pre-warm skipped ${name}: ${e.message}`);
    }
  }
  try { fs.rmSync(warmDir, { recursive: true, force: true }); } catch (_) {}
  // Report cache size so the build log shows whether warming worked.
  try {
    let bytes = 0;
    const walk = (d) => { for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      const p = path.join(d, e.name);
      if (e.isDirectory()) walk(p); else bytes += fs.statSync(p).size;
    }};
    walk(cacheDir);
    console.log(`[OK] Tectonic cache warmed: ${(bytes / 1024 / 1024).toFixed(1)} MB`);
    // Persist for future offline builds.
    if (bytes > 0) {
      try { fs.cpSync(cacheDir, path.join(TOOLS_CACHE, 'tectonic-cache'), { recursive: true }); } catch (_) {}
    }
  } catch (_) {}
}

async function downloadEmbeddingModel(apiDir) {
  // Target layout matches chromadb's cache: <modelsDir>/all-MiniLM-L6-v2/onnx/<files>
  const modelRoot = path.join(apiDir, 'models', 'chroma-onnx', 'all-MiniLM-L6-v2');
  const onnxDir = path.join(modelRoot, 'onnx');
  const marker = path.join(onnxDir, 'model.onnx');
  if (fs.existsSync(marker)) {
    console.log('[INFO] Embedding model already bundled, skipping download.');
    return;
  }
  fs.mkdirSync(modelRoot, { recursive: true });
  const tmpTar = path.join(modelRoot, 'onnx.tar.gz');
  console.log('[INFO] Downloading embedding model (all-MiniLM-L6-v2)...');
  try {
    await downloadFile(EMBED_MODEL_URL, tmpTar, 120000);
    const extractScript = `
import tarfile, sys
tar_path, dest = sys.argv[1], sys.argv[2]
with tarfile.open(tar_path, 'r:gz') as t:
    t.extractall(path=dest, filter='data')
`;
    const pythonCmd = process.platform === 'win32' ? 'python' : 'python3';
    const { error } = require('child_process').spawnSync(pythonCmd, [
      '-c', extractScript, tmpTar, modelRoot,
    ], { encoding: 'utf8' });
    if (error) {
      console.warn(`[WARN] Model extraction failed: ${error}`);
    }
    fs.unlinkSync(tmpTar);
    if (fs.existsSync(marker)) {
      console.log('[INFO] Embedding model bundled successfully.');
    } else {
      console.warn('[WARN] Embedding model extraction produced no model.onnx.');
    }
  } catch (e) {
    console.warn(`[WARN] Failed to bundle embedding model: ${e.message}. 文献库 will download it on first use (needs internet).`);
    try { fs.unlinkSync(tmpTar); } catch (_) {}
  }
}

// Kill running api.exe / scholar-translate.exe so PyInstaller can replace files
if (process.platform === 'win32') {
  for (const name of ['api.exe', 'scholar-translate.exe']) {
    try {
      execSync(`taskkill /F /IM "${name}"`, { stdio: 'pipe' });
      console.log(`[INFO] Killed running ${name}`);
    } catch (_) {
      // not running — ignore
    }
  }
  // Give OS a moment to release file locks
  const sleep = ms => Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
  sleep(1500);
}

console.log('[INFO] Running PyInstaller...');

const workPath = path.join(rootDir, 'build', 'pyi-work');
const requiredDataDirs = [
  path.join(rootDir, 'python', 'data', 'paper_assets'),
  path.join(rootDir, 'python', 'plugins'),
];

for (const dir of requiredDataDirs) {
  fs.mkdirSync(dir, { recursive: true });
}

// Build to a temp directory first, then move — avoids EBUSY from locked old output
const tempDist = outputBase + '_tmp';

// Clean temp directory
if (fs.existsSync(tempDist)) {
  fs.rmSync(tempDist, { recursive: true, force: true });
}

try {
  const pythonCmd = process.platform === 'win32' ? 'python' : 'python3';
  execSync(
    `${pythonCmd} -m PyInstaller --clean --noconfirm --distpath "${tempDist}" --workpath "${workPath}" "${specFile}"`,
    {
      cwd: rootDir,
      stdio: 'inherit',
      env: { ...process.env },
    }
  );
} catch (e) {
  console.error('[ERROR] PyInstaller failed');
  process.exit(1);
}

const tempApiExe = path.join(tempDist, 'api', 'api.exe');
if (!fs.existsSync(tempApiExe)) {
  console.error('[ERROR] api.exe not found at', tempApiExe);
  process.exit(1);
}

// Try to remove old output, or rename it out of the way
try {
  if (fs.existsSync(outputBase)) {
    fs.rmSync(outputBase, { recursive: true, force: true });
  }
} catch (e) {
  // Old directory is locked — rename it
  const locked = outputBase + '_locked';
  try { fs.rmSync(locked, { recursive: true, force: true }); } catch (_) {}
  try { fs.renameSync(outputBase, locked); } catch (_) {}
}

// Move new build into place
try {
  fs.renameSync(tempDist, outputBase);
} catch (e) {
  // If rename fails (cross-device), do recursive copy
  console.warn('[WARN] Rename failed, copying instead...');
  fs.mkdirSync(outputBase, { recursive: true });
  fs.cpSync(path.join(tempDist, 'api'), path.join(outputBase, 'api'), { recursive: true });
  fs.rmSync(tempDist, { recursive: true, force: true });
}

// Create runtime directories next to api.exe
const apiDir = path.dirname(apiExePath);
const configDir = path.join(apiDir, 'config');
const dataDir = path.join(apiDir, 'data');

if (!fs.existsSync(configDir)) {
  fs.mkdirSync(configDir, { recursive: true });
}
if (!fs.existsSync(dataDir)) {
  fs.mkdirSync(dataDir, { recursive: true });
}

(async function main() {
  const stats = fs.statSync(apiExePath);
  console.log(`[OK] Python backend built: ${apiExePath} (${(stats.size / 1024 / 1024).toFixed(1)} MB)`);

  // Bundle external export toolchain (Tectonic for PDF, Pandoc for Markdown->LaTeX/PDF).
  const apiDir = path.dirname(apiExePath);
  try {
    await downloadTectonic(apiDir);
    await downloadPandoc(apiDir);
    await downloadEmbeddingModel(apiDir);
    await prewarmTectonic(apiDir);
    console.log('[OK] All external tools bundled.');
  } catch (e) {
    console.warn(`[WARN] Bundling extra assets incomplete: ${e.message}`);
  }
})();
