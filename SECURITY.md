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
| >= 0.3.x | Yes |
| < 0.3.0 | No |

## Security Model

- All data is processed locally on your machine
- Cloud LLM providers are optional — API keys are stored locally in `config/default.local.yaml` and never sent anywhere except the chosen provider's API
- Agent file operations are scoped to the project workspace; out-of-scope access requires explicit user approval
