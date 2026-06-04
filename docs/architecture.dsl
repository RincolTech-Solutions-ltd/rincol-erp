workspace "Rincol Web ERP" "Business management system for Rincol Tech Solutions Ltd — solar installations, quotations, receipts, customers, maintenance, and balancing." {

    model {

        # ── People ────────────────────────────────────────────────────────────
        hillary = person "Hillary Arinda" "Admin user. Creates quotations, manages finances, balancing, solar sizing." "Admin"
        dennis  = person "Dennis Kaweesi" "Field technician. Executes installations, views assigned jobs." "Field"
        customer = person "Customer" "End customer. Views account statement via a token-gated public link (no login required). Receives quotation, receipt, and statement emails." "External"

        # ── External systems ──────────────────────────────────────────────────
        supabase  = softwareSystem "Supabase" "Managed PostgreSQL database + Auth (JWT). Hosts all ERP data including customers, quotations, receipts, maintenance, balancing, solar sizings, catalog, and tasks." "External"
        sendgrid  = softwareSystem "SendGrid (Twilio)" "Transactional email delivery via HTTPS API. Single Sender Verification — rincoltech@gmail.com. No SMTP, no DNS required. Free tier 100 emails/day." "External"
        telegram  = softwareSystem "Telegram Bot API" "Push notifications to group channel and personal DMs for Hillary and Dennis. Two-way interaction via inline keyboards (approve quotation, update status, log notes)." "External"
        render    = softwareSystem "Render" "PaaS hosting for the Flask app. Free tier. Auto-deploys from GitHub main branch. Gunicorn WSGI server." "External"
        github    = softwareSystem "GitHub" "Source control. arindakhill/rincol-erp (private). Push to main triggers Render auto-deploy." "External"

        # ── Rincol ERP system ─────────────────────────────────────────────────
        erp = softwareSystem "Rincol Web ERP" "Flask-based business management system for Rincol Tech Solutions. Manages the full lifecycle from customer KYC through quotation, job execution, receipt, maintenance, and profit balancing." {

            webApp = container "Flask Web App" "Python 3 / Flask. Serves all HTML UI, handles form submissions, generates PDFs, fires notifications. Single process, multi-threaded via Gunicorn sync workers." "Python / Flask / Gunicorn" {

                # Auth
                authModule = component "Auth Module" "Supabase JWT login/logout. Session stored in Flask signed cookie. login_required decorator guards all internal routes." "Flask routes + Supabase Auth"

                # Core business modules
                customerModule = component "Customer Module" "CRUD for customer records (UUID PK, CUST-XXXX display ID). Deduplication of existing data by phone. Per-customer stats (quoted/paid/outstanding). Statement token management." "Flask routes /customers/*"
                quotationModule = component "Quotation Module" "Create/edit quotations with line items, VAT toggle, drag-sort rows, Quick Build templates. Status workflow: Draft→Pending→Approved→In Progress→Completed→Cancelled. Customer picker auto-fills from customers table. List filterable by job status and payment status (Unpaid/Partial/Paid)." "Flask routes /quotations/*"
                receiptModule = component "Receipt Module" "Payment receipts linked to quotations. Single source of truth for collected amounts. Collected-by tracking (Hillary/Dennis) for balancing." "Flask routes /receipts/*"
                maintenanceModule = component "Maintenance Module" "Post-job maintenance visits. Separate P&L per visit (h_ratio/d_ratio split). Statuses: Scheduled→Open→In Progress→Pending Parts→Resolved→Cancelled. Cancellation requires reason." "Flask routes /maintenance/*"
                balancingModule = component "Balancing Module" "Per-job profit split between Hillary (45%) and Dennis (55%) by default, adjustable. Spend lines, settlements, auto-computed status. Symmetric remaining formula." "Flask routes /balancing/*"
                tasksModule = component "Tasks Module" "To-do tracking with priority, due date, assignee (Hillary/Dennis/Both). Linked to quotations. Overdue alerts via Telegram. Statuses: Pending, In Progress, Done, Cancelled (cancellation reason required). Cancelled tasks excluded from Open view." "Flask routes /tasks/*"
                solarModule = component "Solar Sizing Module" "6-step engineering engine: load→battery→panel array→yield→financials→payback. LiFePO4 no-series guard. BoM with live catalog pricing. PPTX proposal export." "Flask routes /solar/*"
                catalogModule = component "Catalog & Suppliers" "Product catalog with category-aware electrical specs (JSONB). Supplier management. Used as picker in quotation line items and solar sizing." "Flask routes /catalog/*, /suppliers/*"
                statementModule = component "Public Statement" "Token-gated customer statement page at /s/<uuid>. No login required. Live data — always current. PDF opens in new tab. Web Share API share button (clipboard fallback). Back navigation via ?back=<cid> query param (PWA-safe — no auth dependency)." "Flask routes /s/<token>, /s/<token>/pdf"

                # Utilities
                pdfUtil    = component "PDF Generator" "ReportLab-based PDF generation for quotations, receipts, and customer statements. Matches desktop app design (letterhead, signature, QR code)." "utils/pdf.py"
                notifyUtil = component "Notification Service" "Sends Telegram group + personal DMs and SendGrid transactional emails. All sends are async (background thread). Customer emails include PDF attachments." "utils/notify.py"
                tgBot      = component "Telegram Bot Handler" "Handles incoming Telegram callbacks (approve quotation, update status, log note). Webhook registered at /telegram/webhook." "utils/tg_bot.py"
                dbUtil     = component "DB Utility" "psycopg2 ThreadedConnectionPool (1-5 conns). Per-request connection via Flask g. Helper functions: query, query_one, execute." "utils/db.py"
            }
        }

        # ── Relationships — People → System ───────────────────────────────────
        hillary  -> erp "Manages customers, quotations, receipts, solar sizing, balancing" "HTTPS browser"
        dennis   -> erp "Views assigned jobs, logs updates" "HTTPS browser / mobile"
        customer -> erp "Views account statement, downloads PDF" "HTTPS browser (token link)"

        # ── Relationships — System → External ─────────────────────────────────
        erp -> supabase  "Reads/writes all business data" "PostgreSQL / psycopg2"
        erp -> sendgrid  "Sends transactional emails with PDF attachments" "HTTPS / SendGrid Web API v3"
        erp -> telegram  "Sends notifications and receives bot callbacks" "HTTPS / Telegram Bot API"
        erp -> render    "Deployed and hosted on"
        erp -> github    "Source code, auto-deploy triggers"

        # ── Relationships — Container internal ────────────────────────────────
        hillary  -> webApp "Uses via browser"
        dennis   -> webApp "Uses via browser / mobile"
        customer -> webApp "Views public statement"

        webApp -> supabase "Auth + DB queries" "PostgreSQL / psycopg2"
        webApp -> sendgrid "Email delivery" "HTTPS"
        webApp -> telegram "Notifications + bot" "HTTPS"

        # ── Component relationships ────────────────────────────────────────────
        authModule      -> dbUtil      "Session validation"
        customerModule  -> dbUtil      "CRUD customers, link quotations"
        customerModule  -> notifyUtil  "Send statement email"
        customerModule  -> pdfUtil     "Generate statement PDF"
        quotationModule -> dbUtil      "CRUD quotations + items"
        quotationModule -> notifyUtil  "Notify on create/update/status change"
        quotationModule -> pdfUtil     "Generate quotation PDF"
        receiptModule   -> dbUtil      "CRUD receipts"
        receiptModule   -> notifyUtil  "Notify on receipt + email PDF to customer"
        receiptModule   -> pdfUtil     "Generate receipt PDF"
        maintenanceModule -> dbUtil    "CRUD maintenance records"
        maintenanceModule -> notifyUtil "Notify on create/update"
        balancingModule -> dbUtil      "CRUD balancing jobs, spend lines, settlements"
        balancingModule -> notifyUtil  "Notify on settlement"
        tasksModule     -> dbUtil      "CRUD tasks"
        tasksModule     -> notifyUtil  "Notify on create/assign"
        solarModule     -> dbUtil      "CRUD solar sizings, BoM"
        solarModule     -> pdfUtil     "Generate PPTX proposal"
        catalogModule   -> dbUtil      "CRUD catalog items, suppliers"
        statementModule -> dbUtil      "Read customer + quotations (read-only)"
        statementModule -> pdfUtil     "Generate statement PDF"
        notifyUtil      -> sendgrid    "Send email via HTTPS API"
        notifyUtil      -> telegram    "Send messages + keyboards"
        tgBot           -> dbUtil      "Update quotation/task status from bot callback"
        tgBot           -> notifyUtil  "Fire confirmation notifications"
        dbUtil          -> supabase    "SQL via psycopg2 connection pool"
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
            description "The Flask web app is the single deployable unit. All data lives in Supabase. Email via SendGrid, notifications via Telegram."
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
