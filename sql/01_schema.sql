/* ============================================================================
   La Poste Tunisienne — National Reporting
   SQL Server schema (SSMS-manageable, idempotent).

   NOTE: The canonical schema is created by the app via Flask-Migrate/Alembic
   (`flask db upgrade`) or `flask init-db`. This script MIRRORS that schema for
   teams who prefer to provision tables manually in SSMS, and as documentation.
   Run it against the `lp_national` database.
   ============================================================================ */

IF DB_ID('lp_national') IS NULL
    CREATE DATABASE lp_national;
GO
USE lp_national;
GO

/* ── users ─────────────────────────────────────────────────────────────────── */
IF OBJECT_ID('dbo.users', 'U') IS NULL
CREATE TABLE dbo.users (
    id            INT IDENTITY(1,1) PRIMARY KEY,
    username      NVARCHAR(80)  NOT NULL UNIQUE,
    email         NVARCHAR(255) NULL,
    password_hash NVARCHAR(255) NOT NULL,
    is_admin      BIT NOT NULL DEFAULT 0,
    is_active     BIT NOT NULL DEFAULT 1,
    created_at    DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    last_login_at DATETIME2 NULL
);
GO

/* ── profiles (optional 1-1 with users) ────────────────────────────────────── */
IF OBJECT_ID('dbo.profiles', 'U') IS NULL
CREATE TABLE dbo.profiles (
    id           INT IDENTITY(1,1) PRIMARY KEY,
    user_id      INT NOT NULL UNIQUE
                 REFERENCES dbo.users(id) ON DELETE CASCADE,
    full_name    NVARCHAR(160) NULL,
    region_scope NVARCHAR(80)  NULL,
    phone        NVARCHAR(40)  NULL
);
GO

/* ── national_shipments (one row per national parcel) ──────────────────────── */
IF OBJECT_ID('dbo.national_shipments', 'U') IS NULL
CREATE TABLE dbo.national_shipments (
    id                        INT IDENTITY(1,1) PRIMARY KEY,
    mailitm_fid               NVARCHAR(40)  NOT NULL UNIQUE,   -- MAILITM_FID
    weight_kg                 FLOAT NULL,                      -- poids
    crbt_amount               DECIMAL(18,3) NULL,              -- CRBT
    shipment_type             NVARCHAR(20)  NULL,              -- CRBT/ORD
    is_crbt                   BIT NOT NULL DEFAULT 0,          -- derived
    revenue_ca                DECIMAL(18,3) NULL,              -- CA
    weight_tier_2_3kg         FLOAT NULL,                      -- "sup à 2 kg jusquà 3 kg"
    weight_extra_per_kg       FLOAT NULL,                      -- "Pour chaque kg supp …"
    sender_name               NVARCHAR(255) NULL,              -- Nom_exp
    sender_firstname          NVARCHAR(255) NULL,              -- Pre_exp
    sender_address            NVARCHAR(512) NULL,              -- Exp_adresse
    sender_city               NVARCHAR(160) NULL,              -- Exp_cité
    sender_postal_code        NVARCHAR(20)  NULL,              -- Exp_code_postale
    sender_phone              NVARCHAR(40)  NULL,              -- Exp_phone
    origin_country            NVARCHAR(80)  NULL,              -- Pays origine
    destination_country       NVARCHAR(80)  NULL,              -- Pays Destination
    deposit_date              DATETIME2 NULL,                  -- Date depot
    deposit_month             INT NULL,                        -- Mois_depot
    deposit_year              INT NULL,                        -- Annee_depot
    depot_office              NVARCHAR(255) NULL,              -- Bureau depot
    depot_region              NVARCHAR(80)  NULL,              -- Region Depot
    last_event                NVARCHAR(255) NULL,              -- Dernier E
    last_event_date           DATETIME2 NULL,                  -- Date dernier E
    last_event_office         NVARCHAR(255) NULL,              -- Bureau dernier E
    last_event_region         NVARCHAR(80)  NULL,              -- Region dernier E
    is_delivered              BIT NOT NULL DEFAULT 0,          -- derived from Dernier E
    next_office               NVARCHAR(255) NULL,              -- Bureau next
    next_region               NVARCHAR(80)  NULL,              -- Region Next
    interval_days             INT NULL,                        -- Intervalle en jours
    interval_edi_deposit      FLOAT NULL,                      -- intervalle liv EDI/dépôt
    failure_or_delivery_date  DATETIME2 NULL,                  -- date echec ou livraison
    edi_event                 NVARCHAR(255) NULL,              -- EDI_Event  (='X' for national)
    edi_date                  NVARCHAR(64)  NULL,              -- EDI_Date
    edi_cause                 NVARCHAR(255) NULL,              -- EDI_Cause
    edi_action                NVARCHAR(512) NULL,              -- EDI_action
    import_batch              NVARCHAR(64)  NULL,
    created_at                DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    updated_at                DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
);
GO

/* Indexes for reporting / Power BI */
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='ix_ns_depot_region')
    CREATE INDEX ix_ns_depot_region      ON dbo.national_shipments(depot_region);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='ix_ns_last_event_region')
    CREATE INDEX ix_ns_last_event_region ON dbo.national_shipments(last_event_region);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='ix_ns_deposit_ym')
    CREATE INDEX ix_ns_deposit_ym        ON dbo.national_shipments(deposit_year, deposit_month);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='ix_ns_is_delivered')
    CREATE INDEX ix_ns_is_delivered      ON dbo.national_shipments(is_delivered);
GO

/* ── export_shipments & import_shipments ───────────────────────────────────── *
   Same column structure as national_shipments. The application creates these
   (with PK / unique / defaults) via `flask init-db`. For a quick manual mirror
   in SSMS, clone the empty structure:                                          */
IF OBJECT_ID('dbo.export_shipments', 'U') IS NULL
    SELECT * INTO dbo.export_shipments FROM dbo.national_shipments WHERE 1 = 0;
IF OBJECT_ID('dbo.import_shipments', 'U') IS NULL
    SELECT * INTO dbo.import_shipments FROM dbo.national_shipments WHERE 1 = 0;
GO

/* ── report_jobs (queue) ───────────────────────────────────────────────────── */
IF OBJECT_ID('dbo.report_jobs', 'U') IS NULL
CREATE TABLE dbo.report_jobs (
    id            INT IDENTITY(1,1) PRIMARY KEY,
    user_id       INT NOT NULL REFERENCES dbo.users(id),
    job_type      NVARCHAR(40) NOT NULL DEFAULT 'national_report',
    params_json   NVARCHAR(MAX) NOT NULL DEFAULT '{}',
    status        NVARCHAR(20) NOT NULL DEFAULT 'pending',
    log_text      NVARCHAR(MAX) NULL,
    success_count INT NOT NULL DEFAULT 0,
    error_message NVARCHAR(MAX) NULL,
    created_at    DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    started_at    DATETIME2 NULL,
    finished_at   DATETIME2 NULL
);
GO

/* ── generated_reports ─────────────────────────────────────────────────────── */
IF OBJECT_ID('dbo.generated_reports', 'U') IS NULL
CREATE TABLE dbo.generated_reports (
    id          INT IDENTITY(1,1) PRIMARY KEY,
    job_id      INT NOT NULL REFERENCES dbo.report_jobs(id) ON DELETE CASCADE,
    region      NVARCHAR(80)  NULL,
    file_name   NVARCHAR(255) NOT NULL,
    file_format NVARCHAR(20)  NOT NULL DEFAULT 'html',
    emailed_to  NVARCHAR(255) NULL,
    created_at  DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
);
GO

/* ── import_logs (audit trail of imports) ──────────────────────────────────── */
IF OBJECT_ID('dbo.import_logs', 'U') IS NULL
CREATE TABLE dbo.import_logs (
    id            INT IDENTITY(1,1) PRIMARY KEY,
    batch_id      NVARCHAR(64) NOT NULL,
    source_file   NVARCHAR(512) NULL,
    sheet_name    NVARCHAR(120) NULL,
    status        NVARCHAR(20) NOT NULL DEFAULT 'running',
    rows_read     INT NOT NULL DEFAULT 0,
    rows_inserted INT NOT NULL DEFAULT 0,
    rows_updated  INT NOT NULL DEFAULT 0,
    rows_skipped  INT NOT NULL DEFAULT 0,
    message       NVARCHAR(MAX) NULL,
    started_at    DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    finished_at   DATETIME2 NULL
);
GO
