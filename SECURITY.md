# Security

This kit handles session-level credentials for third-party sites
(Notion, hack2hire, 1point3acres). Treat each one as a personal secret.

## What's a secret here

| Surface | Where it lives | Risk if leaked |
|---|---|---|
| `NOTION_TOKEN` | Env var or `.notion-token` | Full read/write on your Notion workspace via the integration's grant |
| `ALGRO_TOKEN` | Env var for `scrape/hack2hire/scrape_all_daemon.py` | hack2hire session impersonation |
| `ACRES_COOKIE` | Env var or `~/.1p3a-cookie` | 1point3acres session impersonation |

The `.gitignore` excludes `.notion-token`, `.env`, `*.token`,
`.1p3a-cookie`, and `*.zip` (which can contain rendered output that
sometimes includes the source URLs of paywalled content).

## What to do if you commit one by accident

1. Rotate the secret at the source **first**: revoke the Notion
   integration token from `notion.so/my-integrations`, log out of all
   1point3acres sessions, etc.
2. Then rewrite history with `git filter-repo` (preferred) or
   `git filter-branch` to remove the secret from prior commits.
3. Force-push to all remotes only after coordinating with the team —
   the new tokens make the old ones useless either way.

## Reporting issues

Open a private GitHub security advisory on the repository or DM the
maintainer. Don't file a public issue with reproducer details.

## Out of scope

- This kit is offline tooling. It doesn't expose a network service, so
  there's no auth flow, no session management, no rate-limit code
  hardening to discuss here.
- The Notion API is rate-limited by Notion. We don't proxy it or
  expose it.
