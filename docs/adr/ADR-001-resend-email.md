# ADR-001: Switch from Gmail SMTP to SendGrid API

## Status: Accepted

## Context
Rincol ERP sends transactional emails (quotation PDFs, receipt PDFs, team notifications) via Gmail SMTP (port 587). After deployment to Render, emails silently stopped delivering. Root cause: Render's free tier blocks outbound SMTP on port 587. Gmail App Password was valid but the TCP connection never reached Google's SMTP servers. The silent `except: pass` in notify.py masked the failure.

Resend was tried first but requires domain DNS verification to send to arbitrary customer emails — blocked because DNS for rincoltech.com is controlled by a third party.

## Decision
Use SendGrid Web API (HTTPS port 443, never blocked). Single Sender Verification — `rincoltech@gmail.com` verified as a sender, no DNS changes required. Free tier: 100 emails/day permanent. Env vars: `SENDGRID_API_KEY` + `EMAIL_FROM=rincoltech@gmail.com`.

## Consequences
- Better: Works on Render free tier. Delivers to any customer email worldwide. No DNS dependency.
- Better: SendGrid dashboard shows delivery status, bounces, opens.
- Watch: 100 emails/day limit on free tier — sufficient for current volume, upgrade if the business scales.
- Watch: Single sender verification tied to rincoltech@gmail.com. If that Gmail account is lost, re-verify a new sender.
