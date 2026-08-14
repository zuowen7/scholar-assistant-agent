# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Scholar Assistant, please report it responsibly:

- **Email**: [zuowen7](https://github.com/zuowen7) via GitHub's private vulnerability reporting
- **GitHub**: Use [Security Advisories](https://github.com/zuowen7/scholar-assistant-agent/security/advisories/new)

**Please do not** open a public GitHub issue for security vulnerabilities.

### What to include

- Description of the vulnerability
- Steps to reproduce
- Affected version
- Potential impact

### Response time

I will acknowledge reports within 48 hours and aim to provide a fix or mitigation within 7 days.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.5.x | Yes |
| < 0.5.0 | No |

## Security Model

- All data is processed locally on your machine
- Cloud LLM providers are optional — API keys are stored locally in `config/default.local.yaml` (gitignored) and never sent anywhere except the chosen provider's API; keys are masked in `/api/config` responses and never committed to the repository
- Image OCR prefers local engines (Tesseract / PaddleOCR): images only leave your machine when a vision API key is configured
- The update checker is proxied through the local backend and reports only your current vs. latest version — no analytics or telemetry
- Agent file operations are scoped to the project workspace; out-of-scope access requires explicit user approval

## Key Handling

If you suspect a key has been exposed (e.g. committed by accident):

1. **Revoke it immediately** in the provider's console — rotation, not history rewriting, is the reliable fix for a public repository
2. Rotate the replacement key into `config/default.local.yaml` via the Settings panel
3. Report the exposure via the channels above if you believe third parties were affected
