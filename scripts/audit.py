import json, re, glob, sys, subprocess
sys.stdout.reconfigure(encoding='utf-8')

print("=" * 60)
print("DEFINITIVE AUDIT")
print("=" * 60)

with open('src/i18n/locales/zh-CN.json', 'r', encoding='utf-8') as f:
    zh = json.load(f)
with open('src/i18n/locales/en-US.json', 'r', encoding='utf-8') as f:
    en = json.load(f)

def flatten(d, pref=''):
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            f = f'{pref}.{k}' if pref else k
            if isinstance(v, dict):
                out.update(flatten(v, f))
            else:
                out[f] = v
    return out

zhf = flatten(zh)
enf = flatten(en)

all_src = (list(glob.glob('src/**/*.vue', recursive=True)) +
           list(glob.glob('src/**/*.ts', recursive=True)))
all_src = [f for f in all_src if '__tests__' not in f and '/i18n/' not in f and '/helpers/' not in f]

crit = []
warn = []
info = []

# 1. Symmetry
zho = set(zhf) - set(enf)
eno = set(enf) - set(zhf)
for k in zho: crit.append(f'SYMMETRY: zh key missing from en: {k}')
for k in eno: crit.append(f'SYMMETRY: en key missing from zh: {k}')
print(f'Symmetry: {len(zho)+len(eno)} issues')

# 2. Resolution
for fp in sorted(all_src):
    with open(fp, 'r', encoding='utf-8') as f:
        c = f.read()
    for m in re.finditer(r"\bt\s*\(\s*'([^']+)'\)", c):
        if m.group(1) not in zhf:
            crit.append(f'UNRESOLVED: {fp}:{c[:m.start()].count(chr(10))+1} t({m.group(1)})')
    for m in re.finditer(r"i18n\.global\.t\s*\(\s*'([^']+)'\)", c):
        if m.group(1) not in zhf:
            crit.append(f'UNRESOLVED: {fp}:{c[:m.start()].count(chr(10))+1} i18n.t({m.group(1)})')
print(f'Resolution: {sum(1 for i in crit if "UNRESOLVED" in i)} issues')

# 3. Placeholder
for fp in sorted(all_src):
    with open(fp, 'r', encoding='utf-8') as f:
        c = f.read()
    for m in re.finditer(r"\bt\s*\(\s*'([^']+)'(\s*,\s*\{[^}]*\})?\)", c):
        key = m.group(1)
        params = m.group(2) or ''
        val = str(zhf.get(key, ''))
        for ph in re.findall(r'\{(\w+)\}', val):
            if ph not in params:
                crit.append(f'PLACEHOLDER: {fp}:{c[:m.start()].count(chr(10))+1} t({key}) needs {{{ph}}}')
print(f'Placeholder: {sum(1 for i in crit if "PLACEHOLDER" in i)} issues')

# 4. Missing imports
for fp in sorted(glob.glob('src/components/**/*.vue', recursive=True)) + ['src/App.vue']:
    with open(fp, 'r', encoding='utf-8') as f:
        c = f.read()
    uses = bool(re.search(r'\{\{\s*t\(', c)) or bool(re.search(r":t\('", c))
    has = 'useI18n' in c
    if uses and not has:
        crit.append(f'IMPORT: {fp} uses t() but no useI18n')
print(f'Import: {sum(1 for i in crit if "IMPORT" in i)} issues')

# 5. Template syntax
for fp in sorted(glob.glob('src/components/**/*.vue', recursive=True)):
    with open(fp, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            if re.search(r'>t\([\'"]', line):
                crit.append(f'TEMPLATE: {fp}:{i}: {line.strip()[:80]}')
print(f'Template: {sum(1 for i in crit if "TEMPLATE" in i)} issues')

# 6. Dead keys
used = set()
for fp in sorted(all_src):
    with open(fp, 'r', encoding='utf-8') as f:
        c = f.read()
    for m in re.finditer(r"\bt\s*\(\s*'([^']+)'\)", c):
        used.add(m.group(1))
    for m in re.finditer(r"i18n\.global\.t\s*\(\s*'([^']+)'\)", c):
        used.add(m.group(1))
dead = set(zhf) - used
if dead:
    for k in sorted(dead)[:15]:
        warn.append(f'DEAD KEY: {k}')
print(f'Dead keys: {len(dead)}')

# 7. async useI18n
for fp in sorted(glob.glob('src/components/**/*.vue', recursive=True)):
    with open(fp, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    in_async = False
    for i, line in enumerate(lines, 1):
        if 'async function' in line:
            in_async = True
        if in_async and 'useI18n()' in line:
            crit.append(f'ASYNC: {fp}:{i} useI18n() in async')
        if in_async and line.strip().startswith('}'):
            in_async = False
print(f'Async: {sum(1 for i in crit if "ASYNC" in i)} issues')

# 8. Remaining hardcoded Chinese (categorized)
OK_PATTERNS = [
    r'研墨?', r'简体中文', r'English',
    r'思源', r'霞鹜', r'微软雅黑', r'宋体', r'文楷',
    r'Noto Sans', r'Noto Serif', r'LXGW', r'SimSun', r'Microsoft YaHei',
    r'API Key', r'Base URL',
    r'console\.', r'//.*', r'<!--.*',
    r'placeholder="gpt-4o"', r'placeholder="https://',
    r'📋|📑|🔤|📚|⚡|📖|✅|⚠️|❓|🟢|🟡|🔴',
]
needs_fix = []
for fp in sorted(glob.glob('src/components/**/*.vue', recursive=True)):
    with open(fp, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    in_style = False
    in_script = False
    for i, line in enumerate(lines, 1):
        if '<style' in line: in_style = True
        if '<script' in line: in_script = True
        if '</script>' in line: in_script = False
        if in_style or in_script:
            continue
        if re.search(r'[一-鿿]', line):
            s = line.strip()
            if s.startswith('<!--') or s.startswith('*'):
                continue
            if any(re.search(p, s) for p in OK_PATTERNS):
                continue
            bad = re.sub(r'[研墨\s]', '', s)
            if not bad.strip():
                continue
            needs_fix.append((fp, i, s[:80]))

print(f'Hardcoded remaining: {len(needs_fix)}')
for fp, i, s in needs_fix:
    short = fp.replace('src/components/', '')
    warn.append(f'CHINESE: {short:40s} L{i}: {s[:55]}')

# 9. Tests
print('Running tests...')
try:
    r = subprocess.run(['npx', 'vitest', 'run'], capture_output=True, text=True,
                       timeout=120, cwd='D:/pycharm_study/translator')
    passed = 'Tests  373 passed' in (r.stdout + r.stderr)
    print(f'  Tests: {"PASS" if passed else "FAIL"}')
    if not passed:
        crit.append('TESTS FAILED')
except Exception as e:
    crit.append(f'TEST ERROR: {e}')

# 10. Build
print('Running build...')
try:
    r = subprocess.run(['npm', 'run', 'build'], capture_output=True, text=True,
                       timeout=120, shell=True, cwd='D:/pycharm_study/translator')
    ok = 'built in' in (r.stdout + r.stderr)
    print(f'  Build: {"OK" if ok else "FAIL"}')
    if not ok:
        crit.append(f'BUILD FAILED: {r.stderr[-200:]}')
except Exception as e:
    crit.append(f'BUILD ERROR: {e}')

# === FINAL ===
print("\n" + "=" * 60)
if crit:
    print(f"CRITICAL ({len(crit)}):")
    for c in crit:
        print(f"  {c}")
if warn:
    print(f"\nWARNING ({len(warn)}):")
    for w in warn[:25]:
        print(f"  {w}")
    if len(warn) > 25:
        print(f"  ... and {len(warn)-25} more")
print(f"\nTotal: {len(crit)} critical, {len(warn)} warning, {len(info)} info")
if not crit:
    print(">> CLEAN: No critical issues. <<")
