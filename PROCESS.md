# Rincol ERP Development Process

## Agile Hierarchy

```
Epic (strategic milestone; multi-sprint)
 └─ Feature (capability; business value)
     └─ Story (sprint-sized outcome)
         ├─ Task (implementation; PR raised here)
         ├─ Bug (defect; fix PR raised in child Task)
         └─ Spike (time-boxed research; ADR output)
Chore (maintenance; standalone leaf)
```

**PRs are always raised against Task or Chore.** Features/Stories describe outcomes; only leaves carry code.

## PR Workflow

1. **Create issue** (Epic/Feature/Story/Task/Bug/Spike/Chore)
   - Assign Phase label (phase-1, phase-2, phase-3)
   - Add to milestone
   - Estimate at leaf only (Task/Bug/Chore) in whole hours

2. **Branch naming:** `<type>/<slug>-issue-<N>`
   - Types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `spike`
   - Example: `fix/appliance-form-array-issue-12`

3. **Commit messages:** `<type>(<scope>): <subject> (#<task>)`
   - Example: `fix(solar): use sentinel-based parsing in appliance form (#2)`
   - Escape hatches: `chore:`, `docs:`, `style:`, `test:` may omit `#N`

4. **Create PR**
   - Link in body: `Closes #<task-number>`
   - Title: `<type>: <subject> (#<task>)`
   - Require: ✅ CI pass, ✅ Code review, ✅ Linked issue

5. **Review & Merge**
   - Requires ≥1 approval
   - Must pass all CI checks
   - Squash merge to main (linear history)
   - Auto-deletes branch

6. **Tag release** (manual after merge)
   - Tag: `v<YYYY.MM.DD>` with fix summary
   - Example: `git tag -a v2026.08.25 -m "Fix appliance form array alignment"`

## Milestones & Phases

| Phase | Duration | Focus |
|-------|----------|-------|
| **Phase 1: Foundation** | Current | Core modules, critical fixes, infrastructure |
| **Phase 2: Features** | Next | New capabilities (Telegram, advanced analytics) |
| **Phase 3: Hardening** | Later | Comprehensive testing, monitoring, docs |

Stories are scheduled **into** phases; Epics/Features **span** phases.

## Traceability

Every commit traces: `Commit → PR (#Task) → Task → Story (#S) → Feature (#F) → Epic (#E)`

A commit without a traceable Epic is a smell (or a Chore, marked with `chore:` prefix).

## Enforcement

- **Branch protection on `main`:**
  - PR required
  - ≥1 review approval
  - All status checks must pass
  - CODEOWNERS validation
  - Linear history (no merge commits)
  - No force-push, no deletion

- **Linked-issue guard CI:** Every code PR must close an issue (#N)
  - Escapes: `docs/`, `references/`, `office/` (documentation-only)

- **Estimate at leaf only.** Stories, Features, Epics carry no estimate — they roll up via sub-issue progress.

## Hours & Timesheet

- Estimate on Task/Bug/Chore only (whole hours)
- Update **Actual (h)** field after merge
- The Projects board Estimate column is the true load (no double-counting)
- One Task = one owner for timesheet accountability

## Tools

- **GitHub Issues:** issue hierarchy (Epic → Feature → Story → Task)
- **GitHub Projects v2:** Rincol ERP Backlog board
- **GitHub Milestones:** Phase buckets (Phase 1, Phase 2, Phase 3)
- **GitHub Actions:** linked-issue-guard CI, tests, lint

## Deploy pipeline split (two repos, two keys, two concerns)

Deploying `rincol-erp` to the Hetzner box is split across two independent CI pipelines, each with its own dedicated SSH key on the box's root `authorized_keys`. They never touch the other's concern:

| Concern | Owner | Trigger | Key |
|---|---|---|---|
| Nginx vhost, systemd **unit file**, TLS cert wiring | `rincol-deploy` repo (`scripts/deploy.sh`) | push to `rincol-deploy` main | `rincol-deploy-ci@github-actions` |
| App **code**: `git reset --hard origin/main`, `pip install`, `systemctl restart` | `rincol-erp` repo (`.github/workflows/deploy.yml`) | push to `rincol-erp` main | `rincol-erp-ci@github-actions` |

A normal code change (this repo) only ever triggers the second pipeline. The first only runs when the systemd unit template or nginx config changes in `rincol-deploy`. Keeping them separate avoids one script having to reason about both infra and app-code failure modes at once.

## Getting Started

1. **Pick an issue** from the backlog (not scheduled → Phase 1 now; later phases → when scheduled)
2. **Create a branch:** `git checkout -b fix/slug-issue-N`
3. **Commit:** follow `<type>(<scope>): <subject> (#N)` format
4. **Push & create PR:** `git push -u origin fix/slug-issue-N` then `gh pr create`
5. **Link:** include `Closes #N` in PR body
6. **Review:** wait for approval + CI
7. **Merge:** squash to main
8. **Tag:** maintainer tags the release after merging

---

**Reference:** [GitHub Project](https://github.com/orgs/RincolTech-Solutions-ltd/projects/2)
