# Invoice Pilot 2.0

Offline invoicing and financial dashboard for Windows. Python 3.11.9 - CustomTkinter, SQLite, ReportLab, Pillow.
Your existing data (`%APPDATA%\InvoicePilot\invoicepilot.db`) is kept and upgraded automatically.

## Install & run
```
py -3.11 -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```
Or double-click `run.bat`.

## Files
- `main.py` - UI: sidebar, splash (5 s), dark/light theme, dashboard charts, all screens, embedded logo.
- `database.py` - SQLite schema, business rules, analytics, reports, backup/restore, PDF generation.

## Features
Dashboard (KPIs, 5 charts, date filter, quick actions) - Invoices (draft/sent/partial/paid/overdue) - Payments with
partial payments, duplicate and overpayment protection - Quotations convertible to invoices - Clients - Products -
Expenses - Reports (10, CSV/PDF export) - Settings (branding, numbering, tax, theme) - Backup/restore.
Statuses are computed from stored records; nothing is emailed or sent externally.
