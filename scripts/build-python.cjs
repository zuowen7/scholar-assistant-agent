/**
 * Build Python backend with PyInstaller, producing a standalone api.exe.
 *
 * Output: src-tauri/python-dist/api/api.exe + all dependencies
 * This replaces copy-python.cjs in the Tauri build pipeline.
 */
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const rootDir = path.resolve(__dirname, '..');
const specFile = path.join(rootDir, 'scripts', 'api.spec');
const outputBase = path.join(rootDir, 'src-tauri', 'python-dist');
const apiExePath = path.join(outputBase, 'api', 'api.exe');

console.log('[INFO] Running PyInstaller...');

const workPath = path.join(rootDir, 'build', 'pyi-work');

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
