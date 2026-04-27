# CJK Fonts for PDF Overlay Export

This directory contains bundled fonts for bilingual PDF overlay rendering.

## Files

| File | Description | Source |
|------|-------------|--------|
| `NotoSansSC-Regular.ttf` | Noto Sans SC (Chinese Simplified), Regular, ~10 MB | Google Fonts / gstatic |

## Download

These fonts are already bundled in the repo. If you need to replace them:

```bash
# Noto Sans SC (Chinese Simplified) — Google Fonts
curl -L -o NotoSansSC-Regular.ttf \
  "https://fonts.gstatic.com/s/notosanssc/v40/k3kCo84MPvpLmixcA63oeAL7Iqp5IZJF9bmaG9_FnYw.ttf"
```

Without a CJK font, overlay PDF export will fall back to Helvetica and CJK characters may render as tofu ().