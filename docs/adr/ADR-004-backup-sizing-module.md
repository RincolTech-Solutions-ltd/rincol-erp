# ADR-004: Backup Sizing Module with Catalog-Driven Recommendations

## Status: Accepted

## Context

Field work requires scoping battery backup systems before quoting. Previously this was done manually in a separate spreadsheet, then transcribed into the quotation. There was no audit trail, no consistency in product selection, and no customer-facing load declaration document.

The key constraint: product selection should use the actual SRNE catalog (with real sell prices at 20% margin) so that a quotation created from the sizing already has the correct line items and totals.

## Decision

Built a Backup Sizing module as a first-class ERP feature:

- Load declaration table: equipment items with qty and watts per unit, live total
- User inputs desired backup hours (flexible, 0.5h steps)
- System queries catalog for all batteries with spec_data JSONB (ah, voltage, dod_rated, max_parallel), computes units needed for the target hours, finds the cheapest matching inverter by bus voltage, ranks all viable combinations by total system cost
- Best value row highlighted; every row has a Quote button that creates a Draft quotation pre-filled with customer details and line items
- Backup sizing requires a linked customer (FK to customers table) before a quotation can be created, enforcing that all quotes are scoped to a real customer record
- SRNE Uganda wholesale pricelist (2026-05-27) seeded: 7 batteries, 11 inverters, 6 charge controllers, 1 panel
- PDF assessment report generated via ReportLab for customer delivery alongside the quotation

## Consequences

Better: load declarations are recorded and auditable; product selection is consistent and uses live catalog pricing; quotation creation from a sizing is one click; customer details carry over automatically.

Worse: relies on catalog spec_data being populated correctly; if a product has no spec_data it is silently excluded from recommendations.

Watch for: bus voltage matching logic (12/24/48V) must stay in sync if new battery voltages are added to the catalog.
