/* ============================================================================
   Power BI / SSRS reporting views — national data only.
   Apply after the schema + after data import:
     sqlcmd -S localhost -d lp_national -U sa -P <pwd> -C -i sql/02_views.sql
   or:  flask create-views
   ============================================================================ */
USE lp_national;
GO

/* ── vw_national_shipments_clean — flat, report-ready fact table ───────────── */
CREATE OR ALTER VIEW dbo.vw_national_shipments_clean AS
SELECT
    s.id,
    s.mailitm_fid,
    s.weight_kg,
    s.crbt_amount,
    s.shipment_type,
    s.is_crbt,
    s.revenue_ca,
    s.deposit_date,
    s.deposit_year,
    s.deposit_month,
    DATEFROMPARTS(
        CASE WHEN s.deposit_year  BETWEEN 1753 AND 9999 THEN s.deposit_year  END,
        CASE WHEN s.deposit_month BETWEEN 1    AND 12   THEN s.deposit_month END,
        1)                                                       AS deposit_month_start,
    s.depot_office,
    s.depot_region,
    s.last_event,
    s.last_event_date,
    s.last_event_office,
    s.last_event_region,
    s.next_region,
    s.interval_days,
    s.interval_edi_deposit,
    s.is_delivered,
    CASE WHEN s.is_delivered = 1 THEN N'Livré' ELSE N'Non livré' END AS delivery_status
FROM dbo.national_shipments s;
GO

/* ── vw_kpi_national — single-row headline KPIs ────────────────────────────── */
CREATE OR ALTER VIEW dbo.vw_kpi_national AS
SELECT
    COUNT(*)                                              AS total_shipments,
    SUM(CASE WHEN is_delivered = 1 THEN 1 ELSE 0 END)     AS delivered,
    SUM(CASE WHEN is_delivered = 0 THEN 1 ELSE 0 END)     AS failed,
    CAST(100.0 * SUM(CASE WHEN is_delivered = 1 THEN 1 ELSE 0 END)
         / NULLIF(COUNT(*), 0) AS DECIMAL(5,1))           AS delivery_rate_pct,
    SUM(CASE WHEN is_crbt = 1 THEN 1 ELSE 0 END)          AS crbt_count,
    SUM(crbt_amount)                                      AS crbt_amount_total,
    SUM(revenue_ca)                                       AS revenue_total,
    AVG(CASE WHEN is_delivered = 1 AND interval_days >= 0
             THEN CAST(interval_days AS FLOAT) END)       AS avg_interval_days,
    SUM(CASE WHEN interval_days > 3 THEN 1 ELSE 0 END)    AS late_deliveries
FROM dbo.national_shipments;
GO

/* ── vw_shipments_by_region — depot region breakdown ───────────────────────── */
CREATE OR ALTER VIEW dbo.vw_shipments_by_region AS
SELECT
    depot_region,
    COUNT(*)                                           AS total_shipments,
    SUM(CASE WHEN is_delivered = 1 THEN 1 ELSE 0 END)  AS delivered,
    SUM(revenue_ca)                                    AS revenue_total,
    SUM(CASE WHEN is_crbt = 1 THEN 1 ELSE 0 END)       AS crbt_count,
    AVG(CASE WHEN is_delivered = 1 AND interval_days >= 0
             THEN CAST(interval_days AS FLOAT) END)    AS avg_interval_days
FROM dbo.national_shipments
GROUP BY depot_region;
GO

/* ── vw_shipments_by_month — monthly evolution ─────────────────────────────── */
CREATE OR ALTER VIEW dbo.vw_shipments_by_month AS
SELECT
    deposit_year,
    deposit_month,
    DATEFROMPARTS(
        CASE WHEN deposit_year  BETWEEN 1753 AND 9999 THEN deposit_year  END,
        CASE WHEN deposit_month BETWEEN 1    AND 12   THEN deposit_month END,
        1)                                             AS month_start,
    COUNT(*)                                           AS total_shipments,
    SUM(CASE WHEN is_delivered = 1 THEN 1 ELSE 0 END)  AS delivered,
    SUM(revenue_ca)                                    AS revenue_total
FROM dbo.national_shipments
WHERE deposit_year IS NOT NULL AND deposit_month IS NOT NULL
GROUP BY deposit_year, deposit_month;
GO

/* ── vw_delivery_status — delivered vs failed ──────────────────────────────── */
CREATE OR ALTER VIEW dbo.vw_delivery_status AS
SELECT
    CASE WHEN is_delivered = 1 THEN N'Livré' ELSE N'Non livré' END AS delivery_status,
    COUNT(*)        AS shipments,
    SUM(revenue_ca) AS revenue_total
FROM dbo.national_shipments
GROUP BY CASE WHEN is_delivered = 1 THEN N'Livré' ELSE N'Non livré' END;
GO

/* ── vw_failure_causes — last event of NON-delivered parcels ───────────────── *
   For national data, EDI_Cause is the placeholder 'X', so the meaningful
   "cause" is the last delivery event (Dernier E) of undelivered parcels.       */
CREATE OR ALTER VIEW dbo.vw_failure_causes AS
SELECT
    ISNULL(last_event, N'(inconnu)') AS failure_event,
    last_event_region,
    COUNT(*) AS shipments
FROM dbo.national_shipments
WHERE is_delivered = 0
GROUP BY ISNULL(last_event, N'(inconnu)'), last_event_region;
GO
