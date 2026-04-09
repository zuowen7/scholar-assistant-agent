/**
 * Copy essential Python backend files to src-tauri/python/ for bundling.
 * Run as part of beforeBuildCommand so both local and CI builds include the backend.
 */
const fs = require('fs');
const path = require('path');

const srcDir = path.resolve(__dirname, '..', 'python');
const dstDir = path.resolve(__dirname, '..', 'src-tauri', 'python');

const items = [
  'api.py',
  'api_cloud.py',
  'api_factory.py',
  'requirements.txt',
  'config',
  'src',
];

// Clean previous copy
if (fs.existsSync(dstDir)) {
  fs.rmSync(dstDir, { recursive: true });
}
fs.mkdirSync(dstDir, { recursive: true });

let count = 0;
for (const item of items) {
  const srcPath = path.join(srcDir, item);
  const dstPath = path.join(dstDir, item);
  if (!fs.existsSync(srcPath)) {
    console.warn(`[WARN] Skipping ${item}: not found at ${srcPath}`);
    continue;
  }
  if (fs.statSync(srcPath).isDirectory()) {
    fs.cpSync(srcPath, dstPath, {
      recursive: true,
      filter: (f) => !f.includes('__pycache__') && !f.includes('.pyc'),
    });
    const files = [];
    const walk = (d) => {
      for (const entry of fs.readdirSync(d, { withFileTypes: true })) {
        if (entry.isFile()) files.push(entry.name);
        else walk(path.join(d, entry.name));
      }
    };
    walk(dstPath);
    count += files.length;
  } else {
    fs.copyFileSync(srcPath, dstPath);
    count++;
  }
}
console.log(`[OK] Copied ${count} Python files to src-tauri/python/`);
