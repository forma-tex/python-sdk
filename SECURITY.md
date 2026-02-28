# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.x     | ✅ Yes     |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Email us at **security@formatex.io** with:

1. A description of the vulnerability
2. Steps to reproduce
3. Potential impact
4. Any suggested fix (optional)

We will acknowledge your report within **48 hours** and aim to ship a patch within **7 days** for critical issues.

## Scope

This SDK is a thin HTTP client. The attack surface is limited to:

- API key handling (keys are never logged or stored by the SDK)
- HTTP requests to `api.formatex.io` only
- Parsing of API responses

Out of scope: vulnerabilities in the FormaTex API service (report those at security@formatex.io separately).
