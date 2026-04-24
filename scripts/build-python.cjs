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

// ── Tectonic bundling ──────────────────────────────────────────────
const TECTONIC_URL = 'https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.16.9/tectonic-0.16.9-x86_64-pc-windows-msvc.zip';
const TECTONIC_VERSION = '0.16.9';

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
    }
  } catch (e) {
    console.warn(`[WARN] Failed to bundle Tectonic: ${e.message}. Users will need to install it manually.`);
    try { fs.unlinkSync(tmpZip); } catch (_) {}
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
  execSync(
    `pyinstaller --clean --noconfirm --distpath "${tempDist}" --workpath "${workPath}" "${specFile}"`,
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

const stats = fs.statSync(apiExePath);
console.log(`[OK] Python backend built: ${apiExePath} (${(stats.size / 1024 / 1024).toFixed(1)} MB)`);

// Bundle Tectonic for offline PDF export
downloadTectonic(path.dirname(apiExePath)).catch(() => {});
