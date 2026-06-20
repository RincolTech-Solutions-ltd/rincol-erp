# ADR-003: Repo migration to org + BoM-as-source-of-truth reconciliation

## Status: Accepted (2026-06-20)

## Context

Two unrelated problems surfaced in the same session:

1. **Repo on a suspended account.** The repo lived at `arindakhill/rincol-erp`. That
   GitHub account was suspended (June 2026), so no new commits could be pushed and
   Render's auto-deploy was frozen on a stale revision.

2. **Solar proposal drifted from the quoted BoM.** When a Solar Sizing's Bill of
   Materials is hand-edited (e.g. 4 panels in one series string instead of the
   auto-recommended 2, or 1 battery instead of 2), the stored engineering calc
   fields (`panels_recommended`, `total_batteries`, `annual_yield_kwh`, financials)
   go stale. The detail page and the PPTX proposal rendered those stale values, so
   a customer proposal showed 2 panels / 2 batteries while the actual quote (and
   the locked BoM) was 4 panels / 1 battery. The numbers, payback, and savings were
   all wrong, plus a false "Array needs 2 strings but inverter supports max 1"
   warning showed because the sizing engine had capped the array under-spec.

## Decision

1. **Move the repo to the `RincolTech-Solutions-ltd` GitHub org** (Hillary is org
   admin). Local `origin` repointed to `git@github.com:RincolTech-Solutions-ltd/rincol-erp.git`.
   The existing Render service was repointed to the new source (Settings → Build →
   Update Source). Render cannot switch an existing service's repo while its GitHub
   *identity* is the suspended account — the fix was to disconnect/reconnect the
   GitHub connection in Render account settings as the active `arindahills` login.

2. **Make the BoM the source of truth for display.** A shared helper
   `_reconcile_results_with_bom(s, bom_list)` in `app.py` re-derives panel/battery
   counts, array arrangement (NS × 1P), annual yield, and all financials from the
   actual BoM before rendering. Both `solar_view` and `solar_pptx` use it, so the
   engineering summary, financial appraisal, and the proposal always agree with the
   quoted BoM, and the stale string warning is cleared.

3. **Fix the sizing engine to pack panels in series when string-current-limited.**
   `utils/solar.py` previously capped the array under the energy requirement when
   the inverter supported fewer parallel strings than energy needed. It now grows
   panels-per-series (within MPPT max-V and OC voltage headroom) first, only warning
   if the array still falls short. A 1-string inverter with a 60–450V MPPT window
   now correctly recommends 4S × 1P instead of 2 panels + a false warning.

## Consequences

- **Better:** deploy pipeline restored under an org-owned repo not tied to a
  personal account; proposals and on-screen figures always match the quoted BoM;
  sizing recommendations are electrically valid (never under-spec).
- **Worse / watch for:** reconciliation only protects a **locked** BoM. Unlocking a
  sizing and recalculating rebuilds the BoM from the auto-recommendation, replacing
  manual edits. The stored calc fields remain the auto-recommendation; the BoM-true
  values are computed at render time, not persisted.
- **Operational:** Render's GitHub identity must stay on the active `arindahills`
  account. If the org's Render GitHub App install is removed, deploys break.
