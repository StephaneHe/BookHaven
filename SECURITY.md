# Security Policy

## Scope and threat model

BookHaven is a **self-hosted** application intended to run on a **private,
trusted network** (a home LAN or a personal VPN). The threat model assumes every
device that can reach the server is trusted. It is **not** designed to be
exposed directly to the public internet.

## Reporting a vulnerability

Please report security issues privately by opening a
[GitHub security advisory](https://github.com/StephaneHe/BookHaven/security/advisories/new)
rather than a public issue. Include reproduction steps and the affected version
(shown in the UI footer and at `GET /api/version`).

## Hardening in place

- **Uploads** are validated by extension **and leading magic bytes**, given a
  filesystem-safe name, and confined to the configured library root
  (`os.path.abspath` + `os.sep` boundary) — no path traversal or arbitrary
  write outside the library.
- **EPUB resources** are streamed from the archive with a MIME allowlist;
  anything that isn't an image/CSS/font is forced to `attachment` with
  `nosniff` and a locked-down CSP, so a crafted EPUB cannot execute script on
  the app's origin.
- **Outbound metadata fetches** (cover/description enrichment) are restricted to
  public `http(s)` hosts; `file://`, and private/loopback/link-local addresses
  are rejected (SSRF guard).
- **Login PIN** (when set) uses a constant-time comparison and a per-IP
  brute-force lockout.
- **Sessions**: `HttpOnly`, `SameSite=Lax`, rebuilt on login (anti-fixation);
  `Secure` when `BOOKHAVEN_COOKIE_SECURE=1`.
- **Security headers** (CSP, `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`) on every response.
- A test-mode auth bypass exists for the automated suite but **fails closed**:
  it refuses to start unless `BOOKHAVEN_ENV` is a dev/test environment.

## Known limitations (by design)

These are conscious trade-offs for a trusted-network deployment, documented so
they are not mistaken for oversights:

- **No per-user passwords.** Authentication is by user selection plus an optional
  **shared** PIN. With no PIN configured, access is passwordless.
- **The user list is readable pre-auth** (`GET /api/auth/users`) so the login
  screen can show accounts.
- **No CSRF token**; cross-site request forgery is mitigated by `SameSite=Lax`
  cookies, which block the practical cross-site POST vector here.
- The server binds `0.0.0.0`. Put it behind a VPN or reverse proxy; do not
  expose it directly to the internet.
