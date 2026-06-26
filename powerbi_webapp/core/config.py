"""Shared configuration & constants for the La Poste Tunisienne reporting webapp."""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.dirname(BASE_DIR)  # Code_PFE_Master/

# ── Power BI ─────────────────────────────────────────────────────────────────
REPORT_URL  = "https://app.powerbi.com/groups/me/reports/36c0dd62-e78a-4f8a-a7b9-8ef80ffcda46/28a6e6bc3a83d0b03f92?experience=power-bi"
REPORT_ID   = "36c0dd62-e78a-4f8a-a7b9-8ef80ffcda46"
PROFILE_DIR = os.path.join(BASE_DIR, "powerbi_profile")
API_BASE    = "https://api.powerbi.com/v1.0/myorg"

# ── Data files ───────────────────────────────────────────────────────────────
XLSX_PATH       = os.path.join(DATA_DIR, "dépôt2026_nettoyé.xlsx")
IMPORT_XLS_PATH = os.path.join(DATA_DIR, "import.xls")
LOGO_PATH       = os.path.join(DATA_DIR, "powerbi_automate_email", "logo_laposte.jpg")

# ── Email (SMTP) ─────────────────────────────────────────────────────────────
EMAIL_FROM     = "aalabouzid2002@gmail.com"
EMAIL_PASSWORD = "nwsj xmwh jvxz rspv"
DEFAULT_EMAIL  = "ala-eddine.bouzid@esprit.tn"

# ── Regions ──────────────────────────────────────────────────────────────────
REGIONS = [
    "ARIANA", "BEJA", "BEN AROUS", "BIZERTE", "GABES", "GAFSA", "JENDOUBA",
    "KAIROUAN", "KASSERINE", "KEBILI", "KEF", "MAHDIA", "MANOUBA", "MEDENINE",
    "MONASTIR", "NABEUL", "SFAX", "SIDI BOUZID", "SILIANA", "SOUSSE",
    "TATAOUINE", "TOZEUR", "TUNIS", "ZAGHOUAN",
]
REGION_NAMES_UPPER = [r.upper() for r in REGIONS]
MANUAL_SLICER_MAP  = {r: "Region Depot" for r in REGIONS}

# Default per-region recipient (empty -> falls back to DEFAULT_EMAIL); editable in DB.
DEFAULT_REGION_EMAILS = {r: "" for r in REGIONS}

FIXED_CATEGORY  = "Agences"
CATEGORY_CHOICES = ["Agences", "Centres de distribution", "Bureaux"]

# ── Section labels (table indices in the merged 4-table report) ─────────────
SECTION_LABELS = {0: "DEPOT", 2: "LIVRAISON"}

_COMPUTED_COLS = {
    frozenset({"Agences", "Centres de distribution", "Bureaux"}): (
        "Categorie_Bureau_Dernier_E_nle",
        lambda v: "Agences" if "agence" in str(v).lower()
                  else "Centres de distribution" if "centre" in str(v).lower()
                  else "Bureaux"
    ),
}

_BLANK_TOKENS = {"(blank)", "(vide)", "(empty)", "(null)", ""}

# ── Colonnes sélectionnables pour les tableaux KPI ────────────────────────────
# Format : (clé interne, libellé affiché, coché par défaut)
DEPOT_COLUMNS = [
    ("crbt", "CRBT", True),
    ("ca",   "CA",   True),
]

LIVRAISON_COLUMNS = [
    ("dernier_e",  "Dernier E",            True),
    ("taux_liv",   "Taux livraison (%)",   True),
    ("intervalle", "Intervalle moyen (j)", True),
]

# Catégories de bureau dépôt — filtre affiché dans le formulaire
DEPOT_CATEGORIES = [
    ("agences",  "Agences",                 True),
    ("bureaux",  "Bureaux",                 True),
    ("centres",  "Centres de distribution", True),
]

DEPOT_COL_KEYS_DEFAULT      = [k for k, _, _ in DEPOT_COLUMNS]
LIVRAISON_COL_KEYS_DEFAULT  = [k for k, _, _ in LIVRAISON_COLUMNS]
DEPOT_CAT_KEYS_DEFAULT      = [k for k, _, _ in DEPOT_CATEGORIES]
LIVRAISON_CAT_KEYS_DEFAULT  = [k for k, _, _ in DEPOT_CATEGORIES]  # same categories

_NATIONAL_DIMS       = {"Bureau depot", "Region dernier E"}
_NATIONAL_EXTRA_COLS = ["poids", "Dernier E", "CA"]

# ── Colors (HTML branding) ───────────────────────────────────────────────────
C_NAVY   = "#0B2A6F"
C_YELLOW = "#F4C20D"
C_BG     = "#F7F9FC"
C_LIGHT  = "#EEF4FF"

# ── Webapp ───────────────────────────────────────────────────────────────────
SECRET_KEY  = "change-me-in-production-please"
DB_PATH     = os.path.join(BASE_DIR, "app.db")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
