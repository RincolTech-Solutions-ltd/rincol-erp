# ADR-002: Customer Module — UUID PK + CUST-XXXX Display ID + Token-Gated Statement

## Status: Accepted

## Context
Customer data existed only as free-text fields on quotation records. Same customer appeared multiple times across quotations with no deduplication. No way to see per-customer totals, outstanding balances, or send a professional statement. Dennis and customers both complained.

## Decision
Introduce a `customers` table with:
- UUID primary key (immutable, survives all data changes)
- `customer_no` (CUST-0001...) generated via PostgreSQL sequence — human-readable display ID
- `statement_token` UUID — powers a public, login-free statement URL at `/s/<token>`

Migration deduplicates existing customers by phone number (fallback: name), assigns CUST numbers chronologically, and links all existing quotations + receipts via nullable `customer_id` FK.

Public statement page at `/s/<token>` requires no login — token acts as the access credential. Token can be regenerated to revoke access. Customer can be sent the link via WhatsApp, email, or any channel.

Statement PDF downloadable from the public page and also emailable directly from the customer profile.

## Consequences
- Better: Single customer record regardless of how many quotations. Clean per-customer P&L view. Professional branded statement shareable via WhatsApp link or email.
- Better: Quotation form now has a customer search picker — type name/phone, select, fields auto-fill. Reduces re-entry errors.
- Watch: `customer_id` is nullable on quotations — quotations created before migration or without selecting a customer from the picker will not link. Run migration SQL before deploying this code.
- Watch: Phone is the dedup key during migration. If two different people share a phone number in the DB they will be merged into one customer record. Review after migration.
