workspace "Rincol Web ERP" "Business management system for Rincol Tech Solutions Ltd — solar installations, quotations, receipts, customers, maintenance, and balancing." {

    model {

        # ── People ────────────────────────────────────────────────────────────
        hillary = person "Hillary Arinda" "Admin user. Creates quotations, manages finances, balancing, solar sizing." "Admin"
        dennis  = person "Dennis Kaweesi" "Field technician. Executes installations, views assigned jobs." "Field"
        customer = person "Customer" "End customer. Views account statement via a token-gated public link (no login required). Receives quotations, receipts and account statements by email and WhatsApp." "External"

        # ── External systems ──────────────────────────────────────────────────
        supabase  = softwareSystem "Supabase Auth" "JWT-based login/logout only. Business data no longer lives here — migrated to self-hosted Postgres 2026-08-13 after the Supabase free-tier project paused." "External"
        postgres  = softwareSystem "Hetzner PostgreSQL 16" "Self-hosted database (89.167.121.193:5432). Hosts all ERP business data: customers, quotations, receipts, maintenance, balancing, solar sizings, catalog, and tasks." "External"
        gmailSmtp = softwareSystem "Gmail SMTP" "Email delivery as rincoltech@gmail.com over smtp.gmail.com:587 with STARTTLS and an app password. Replaced SendGrid in 2026-09 after its credits ran out silently. Port 465 is blocked outbound from the Hetzner box." "External"
        whatsappBridge = softwareSystem "WhatsApp Bridge" "Local whatsmeow bridge on the Hetzner box (127.0.0.1:8080, POST /api/send with a media_path on the shared /tmp). Sends from the business owner's WhatsApp number. Does NOT check that a number is on WhatsApp and reports success regardless, so the sender normalizes and refuses ambiguous numbers itself." "External"
        telegram  = softwareSystem "Telegram Bot API" "Push notifications to group channel and personal DMs for Hillary and Dennis. Two-way interaction via inline keyboards (approve quotation, update status, log notes)." "External"
        hetzner   = softwareSystem "Hetzner VPS" "Self-hosted box (89.167.121.193), shared with other Rincol/family apps. Flask app runs as a native systemd service (gunicorn, 127.0.0.1:8003) behind system Nginx. Served at erp.rincoltech.com. No Docker for this app." "External"
        github    = softwareSystem "GitHub" "RincolTech-Solutions-ltd/rincol-erp — PUBLIC repo (made public 2026-08-27 to get unlimited free GitHub Actions minutes; no secrets/PII committed). Two independent push-to-deploy CI pipelines target the Hetzner box, each with its own dedicated SSH key: this repo's own workflow (git reset + pip install + systemctl restart for app code) and the separate rincol-deploy repo (nginx vhost + systemd unit template, infra only). A linked-issue-guard check is required on every PR." "External"

        # ── Rincol ERP system ─────────────────────────────────────────────────
        erp = softwareSystem "Rincol Web ERP" "Flask-based business management system for Rincol Tech Solutions. Manages the full lifecycle from customer KYC through quotation, job execution, receipt, maintenance, and profit balancing." {

            webApp = container "Flask Web App" "Python 3 / Flask. Serves all HTML UI, handles form submissions, generates PDFs, fires notifications. Single process, multi-threaded via Gunicorn sync workers." "Python / Flask / Gunicorn" {

                # Auth
                authModule = component "Auth Module" "Supabase JWT login/logout. Session stored in Flask signed cookie. login_required decorator guards all internal routes." "Flask routes + Supabase Auth"

                # Core business modules
                customerModule = component "Customer Module" "CRUD for customer records (UUID PK, CUST-XXXX display ID). Deduplication of existing data by phone. Per-customer stats (quoted/paid/outstanding). Statement token management." "Flask routes /customers/*"
                quotationModule = component "Quotation Module" "Create/edit quotations with line items, VAT toggle, drag-sort rows, Quick Build templates. Status workflow: Draft→Pending→Approved→In Progress→Completed→Cancelled. Customer picker auto-fills from customers table. List filterable by job status and payment status (Unpaid/Partial/Paid)." "Flask routes /quotations/*"
                receiptModule = component "Receipt Module" "Payment receipts linked to quotations. Single source of truth for collected amounts. Collected-by tracking (Hillary/Dennis) for balancing." "Flask routes /receipts/*"
                maintenanceModule = component "Maintenance Module" "Post-job maintenance visits. Separate P&L per visit: cost split three ways (parts/labour+transport/external service), fronted-cost tracked per person (hillary_paid/dennis_paid, independent of the h_ratio/d_ratio profit split). Statuses: Scheduled→Open→In Progress→Pending Parts→Resolved→Cancelled. Cancellation requires reason." "Flask routes /maintenance/*"
                balancingModule = component "Balancing Module" "Per-job profit split between Hillary (45%) and Dennis (55%) by default, adjustable. Spend lines, settlements, auto-computed status. Symmetric remaining formula." "Flask routes /balancing/*"
                tasksModule = component "Tasks Module" "To-do tracking with priority, due date, assignee (Hillary/Dennis/Both). Linked to quotations. Overdue alerts via Telegram. Statuses: Pending, In Progress, Done, Cancelled (cancellation reason required). Cancelled tasks excluded from Open view." "Flask routes /tasks/*"
                solarModule = component "Solar Sizing Module" "6-step engineering engine: load→battery→panel array→yield→financials→payback. LiFePO4 no-series guard. BoM with live catalog pricing. PPTX proposal export." "Flask routes /solar/*"
                backupModule = component "Backup Sizing Module" "Load declaration tool for battery backup scoping. User enters equipment load items and desired backup hours. System queries catalog, ranks all viable battery+inverter combos by total cost, highlights best value. Requires a linked customer (FK). One-click quotation creation from any ranked option, pre-filling customer details and line items. PDF assessment report for customer delivery." "Flask routes /backup-sizing/*, backup_sizing table"
                catalogModule = component "Catalog & Suppliers" "Product catalog with category-aware electrical specs (JSONB). Supplier management. Used as picker in quotation line items, solar sizing, and backup sizing." "Flask routes /catalog/*, /suppliers/*"
                priceListModule = component "Price Lists" "Static PDF pricelist viewer. Lists PDFs from static/docs/pricelists/ with view and download actions. SRNE Uganda wholesale pricelist 2026-05-27 seeded." "Flask route /docs/pricelists"
                statementModule = component "Public Statement" "Token-gated customer statement page at /s/<uuid>. No login required. Live data — always current. PDF opens in new tab. Web Share API share button (clipboard fallback). Back navigation via ?back=<cid> query param (PWA-safe — no auth dependency)." "Flask routes /s/<token>, /s/<token>/pdf"

                # Utilities
                pdfUtil    = component "PDF Generator" "ReportLab-based PDF generation for quotations, receipts, and customer statements. Matches desktop app design (letterhead, signature, QR code)." "utils/pdf.py"
                notifyUtil = component "Notification Service" "Internal notifications: Telegram group and personal DMs plus internal emails, sent from a background thread. Also holds the customer email senders (quotation, receipt, statement), which customerDispatch calls synchronously." "utils/notify.py"
                customerDispatch = component "Customer Dispatch" "The one path a customer-facing document (quotation, receipt, account statement) takes to the customer: email then WhatsApp, synchronously inside the request, returning the real per-channel outcome for the flash. Builds the receipt and statement PDFs when an email OR a phone is on file. Receipt edits re-send only when the operator ticks Resend." "utils/customer_dispatch.py"
                whatsappUtil = component "WhatsApp Sender" "Normalizes the customer phone to E.164 (refusing ambiguous national numbers) and posts the PDF plus caption to the bridge with a 25s timeout so email plus WhatsApp typically fit inside the 60s gunicorn worker timeout (the SMTP 15s timeout is per operation, not a total budget)." "utils/whatsapp.py"
                tgBot      = component "Telegram Bot Handler" "Handles incoming Telegram callbacks (approve quotation, update status, log note). Webhook registered at /telegram/webhook." "utils/tg_bot.py"
                dbUtil     = component "DB Utility" "psycopg2 ThreadedConnectionPool (1-5 conns). Per-request connection via Flask g. Helper functions: query, query_one, execute." "utils/db.py"
            }
        }

        # ── Relationships — People → System ───────────────────────────────────
        hillary  -> erp "Manages customers, quotations, receipts, solar sizing, balancing" "HTTPS browser"
        dennis   -> erp "Views assigned jobs, logs updates" "HTTPS browser / mobile"
        customer -> erp "Views account statement, downloads PDF" "HTTPS browser (token link)"

        # ── Relationships — System → External ─────────────────────────────────
        erp -> supabase  "Login/logout only (JWT)" "HTTPS / Supabase Auth"
        erp -> postgres  "Reads/writes all business data" "PostgreSQL / psycopg2"
        erp -> gmailSmtp "Sends emails with PDF attachments" "SMTP 587 / STARTTLS"
        erp -> whatsappBridge "Sends quotation and receipt PDFs to customers" "HTTP (localhost)"
        erp -> telegram  "Sends notifications and receives bot callbacks" "HTTPS / Telegram Bot API"
        erp -> hetzner   "Deployed and hosted on (systemd + gunicorn + Nginx)"
        erp -> github    "Source code; push to main auto-deploys via dedicated CI"

        # ── Relationships — Container internal ────────────────────────────────
        hillary  -> webApp "Uses via browser"
        dennis   -> webApp "Uses via browser / mobile"
        customer -> webApp "Views public statement"

        webApp -> supabase "Login/logout (JWT)" "HTTPS"
        webApp -> postgres "DB queries" "PostgreSQL / psycopg2"
        webApp -> gmailSmtp "Email delivery" "SMTP 587 / STARTTLS"
        webApp -> whatsappBridge "Customer WhatsApp delivery" "HTTP (localhost)"
        webApp -> telegram "Notifications + bot" "HTTPS"

        # ── Component relationships ────────────────────────────────────────────
        authModule      -> dbUtil      "Session validation"
        customerModule  -> dbUtil      "CRUD customers, link quotations"
        customerModule  -> customerDispatch "Send account statement PDF (email and WhatsApp) with the live statement link"
        quotationModule -> dbUtil      "CRUD quotations + items"
        quotationModule -> notifyUtil  "Notify on create/update/status change"
        quotationModule -> customerDispatch "Send quotation PDF to customer on Pending/Approved"
        quotationModule -> pdfUtil     "Generate quotation PDF"
        receiptModule   -> dbUtil      "CRUD receipts"
        receiptModule   -> notifyUtil  "Notify internally on receipt"
        receiptModule   -> customerDispatch "Send receipt PDF to customer (on create; on edit only when Resend is ticked)"
        receiptModule   -> pdfUtil     "Generate receipt PDF"
        maintenanceModule -> dbUtil    "CRUD maintenance records"
        maintenanceModule -> notifyUtil "Notify on create/update"
        balancingModule -> dbUtil      "CRUD balancing jobs, spend lines, settlements"
        balancingModule -> notifyUtil  "Notify on settlement"
        tasksModule     -> dbUtil      "CRUD tasks"
        tasksModule     -> notifyUtil  "Notify on create/assign"
        solarModule     -> dbUtil      "CRUD solar sizings, BoM"
        solarModule     -> pdfUtil     "Generate PPTX proposal"
        backupModule    -> dbUtil      "CRUD backup sizings; query catalog for battery+inverter options"
        backupModule    -> pdfUtil     "Generate backup assessment PDF"
        backupModule    -> quotationModule "Creates Draft quotation pre-filled with selected option"
        catalogModule   -> dbUtil      "CRUD catalog items, suppliers"
        statementModule -> dbUtil      "Read customer + quotations (read-only)"
        statementModule -> pdfUtil     "Generate statement PDF"
        notifyUtil      -> gmailSmtp   "Send email"
        customerDispatch -> notifyUtil "Customer email senders"
        customerDispatch -> whatsappUtil "Customer WhatsApp send"
        customerDispatch -> pdfUtil    "Build receipt and statement PDFs"
        whatsappUtil    -> whatsappBridge "POST /api/send"
        tgBot           -> customerDispatch "Send receipt to customer after a bot-created receipt"
        notifyUtil      -> telegram    "Send messages + keyboards"
        tgBot           -> dbUtil      "Update quotation/task status from bot callback"
        tgBot           -> notifyUtil  "Fire confirmation notifications"
        dbUtil          -> postgres    "SQL via psycopg2 connection pool"
    }

    views {

        # ── System Context ─────────────────────────────────────────────────────
        systemContext erp "SystemContext" {
            include *
            autoLayout lr
            title "Rincol Web ERP — System Context"
            description "How the ERP fits into the broader ecosystem of users and external services."
        }

        # ── Container view ─────────────────────────────────────────────────────
        container erp "Containers" {
            include *
            autoLayout lr
            title "Rincol Web ERP — Containers"
            description "The Flask web app is the single deployable unit. All business data lives in self-hosted Hetzner PostgreSQL; Supabase is retained for login only. Email via Gmail SMTP, customer WhatsApp via the local bridge, notifications via Telegram."
        }

        # ── Component view ─────────────────────────────────────────────────────
        component webApp "Components" {
            include *
            autoLayout
            title "Flask Web App — Components"
            description "Internal modules of the Flask application. All modules share the DB utility and notification service."
        }

        # ── Styles ─────────────────────────────────────────────────────────────
        styles {
            element "Person" {
                shape Person
                background #1a1d2e
                color #89b4fa
            }
            element "Admin" {
                background #1e3a5f
                color #89b4fa
            }
            element "Field" {
                background #1e3a2f
                color #6ee7b7
            }
            element "External" {
                background #374151
                color #d1d5db
            }
            element "Software System" {
                background #1e40af
                color #ffffff
            }
            element "Container" {
                background #1d4ed8
                color #ffffff
            }
            element "Component" {
                background #2563eb
                color #ffffff
            }
        }
    }
}
