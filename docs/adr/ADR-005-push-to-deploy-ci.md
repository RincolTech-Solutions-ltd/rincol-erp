# ADR-005: Push-to-deploy CI for app code, split from infra CI

## Status: Accepted

## Context
Deploying a new commit to `erp.rincoltech.com` required manually SSHing into the Hetzner box and running `git pull` + `systemctl restart` by hand — no automation existed for the app-code half of deployment. A separate repo, `rincol-deploy`, already had a live, adversarially-reviewed CI pipeline for this box, but it only manages Nginx vhosts and the systemd unit template — it never touches the checked-out app code at `/opt/rincol-erp-hetzner`.

GitHub Actions on a private repo also has a monthly minutes cap; the org's Actions billing had a failed payment, blocking the first CI run entirely.

## Decision
1. Added `.github/workflows/deploy.yml` directly in `rincol-erp`: on push to `main`, SSH to the box with a **new, dedicated** ed25519 key (`rincol-erp-ci@github-actions`, separate from `rincol-deploy`'s own key), `git reset --hard origin/main`, reinstall pip deps only if `requirements.txt` changed, `systemctl restart rincol-erp`, poll a health check on `127.0.0.1:8003`, and roll back to the previous commit on ANY failure (fetch, reset, install, restart, or health check) — not just a failed health check.
2. Kept this pipeline **strictly separate** from `rincol-deploy`'s: that repo still owns Nginx/systemd-unit config only. Documented the split in `PROCESS.md` so it's not accidentally duplicated or merged later without a deliberate decision.
3. Made the `RincolTech-Solutions-ltd/rincol-erp` repo **public** to get unlimited free GitHub Actions minutes (public repos aren't billed for Actions). Verified first that no secrets, API keys, or real customer PII were committed anywhere in tracked files before flipping visibility — only catalog/pricing seed data and business logic are exposed.
4. Added `linked-issue-guard.yml` as a required status check on `main` (this was documented in `PROCESS.md` from the start but never actually wired — GitHub Pro was required for required-status-checks on a private repo, which blocked it until the repo went public).

## Consequences
- **Better:** `git push` to `main` now deploys automatically, matching the discipline already used on NFE's repos. Every failure path (not just health-check failure) explicitly rolls back, so a bad deploy can't strand the box on broken code.
- **Worse:** the repo's source, commit history, and issue tracker are now publicly visible. Business logic and catalog pricing structure are exposed permanently, even if visibility is reverted later (once public, it can be cloned/indexed).
- **Watch for:** two independent root-capable SSH keys now exist on the same box for two different CI pipelines targeting the same app. If `rincol-deploy`'s scope ever needs to expand into app-code territory (or vice versa), reconcile deliberately — don't let both scripts start touching the same files.
