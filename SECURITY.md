# Security Policy

## Overview

The Maritime OSINT platform aggregates sensitive intelligence data: sanctions
lists, vessel behavioral signals, and ownership information. We take the
security of this platform and the integrity of its data seriously.

---

## Supported Versions

Security fixes are applied to the `main` branch. No separate release branches
are maintained at this time.

| Branch | Supported |
|---|---|
| `main` | ✅ Yes |
| Older commits | ❌ No |

---

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Report vulnerabilities privately using GitHub's Security Advisory feature:

1. Go to the repository on GitHub.
2. Click the **Security** tab.
3. Click **Report a vulnerability**.
4. Provide a clear description, reproduction steps, and potential impact.

---

## What to Report

Report anything that could:

- Allow unauthenticated access to the dashboard or API when `APP_PASSWORD` is set
- Allow extraction of sanctions data or vessel intelligence without authentication
- Allow SQL injection, command injection, or template injection
- Allow session hijacking or authentication bypass
- Expose environment variables, credentials, or API keys
- Allow data corruption in the sanctions database or vessel registry

---

## Known Limitations (Not Vulnerabilities)

- TLS is not handled by the application — use Railway or a reverse proxy.
- `APP_PASSWORD` is a simple shared-password gate, not multi-user access
  control.
- AIS data is publicly broadcast and is not sensitive.

---

## Response Timeline

- Acknowledge receipt: within 3 business days
- Initial assessment: within 7 business days
- Fix or mitigation plan: within 30 days for confirmed vulnerabilities

---

## Security Recommendations for Operators

**Authentication:** Set `APP_PASSWORD` for any network-accessible deployment.
Set `SECRET_KEY` explicitly — auto-generated values change on restart and
invalidate sessions.

**TLS:** Place the application behind a TLS-terminating reverse proxy (nginx,
Caddy, or Railway's built-in proxy) in production.

**Database:** Use PostgreSQL via `DATABASE_URL` for production deployments.

**API keys:** Rotate `AISSTREAM_API_KEY` via the aisstream.io dashboard if
compromised.
