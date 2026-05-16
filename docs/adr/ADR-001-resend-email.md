# ADR-001: Switch from Gmail SMTP to Resend API

## Status: Accepted

## Context
Rincol ERP sends transactional emails (quotation PDFs, receipt PDFs, team notifications) via Gmail SMTP (port 587). After deployment to Render, emails silently stopped delivering. Root cause: Render's free tier blocks outbound SMTP on port 587. Gmail App Password was valid but the TCP connection never reached Google's SMTP servers. The silent `except: pass` in notify.py masked the failure.

## Decision
Replace all smtplib/Gmail SMTP code with Resend HTTP API (resend.com). Resend uses HTTPS (port 443) which is never blocked. No new Python package required — calls made via `requests` which is already in requirements.txt. Env vars changed: `GMAIL_APP_PASSWORD` + `GMAIL_USER` replaced by `RESEND_API_KEY` + `EMAIL_FROM`.

## Consequences
- Better: Works on Render free tier. Delivery visibility via Resend dashboard. No SMTP port issues on any host.
- Watch: `EMAIL_FROM` must be `onboarding@resend.dev` (sandbox) until `rincoltech.com` is verified in Resend Domains. Sandbox can only deliver to the Resend account owner email (arinda.hillary@gmail.com). Customer emails to arbitrary addresses require domain verification.
- Pending: Add 3 DNS records to rincoltech.com once brother shares registrar access, then update `EMAIL_FROM=noreply@rincoltech.com` on Render.
