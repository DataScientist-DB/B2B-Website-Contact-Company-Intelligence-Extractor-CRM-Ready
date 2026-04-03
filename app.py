from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List
from urllib.parse import urlparse

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from apify_api import ApifyClientLite
from export_utils import df_to_csv_bytes, df_to_xlsx_bytes, pick_columns, safe_dataframe

# -------------------------------
# SECRETS HELPER
# -------------------------------
def get_secret(key: str, default: str = "") -> str:
    import os
    try:
        return st.secrets.get(key, os.getenv(key, default))
    except Exception:
        return os.getenv(key, default)


# -------------------------------
# CONFIG
# -------------------------------
APP_PASSWORD = get_secret("APP_PASSWORD", "demo123")
DEFAULT_TOKEN = get_secret("APIFY_TOKEN", "")
DEFAULT_ACTOR_ID = get_secret("APIFY_ACTOR_ID", "gBBp9t5KjUcEt1ESS")
# -------------------------------
# TOKEN VALIDATION
# -------------------------------
token = DEFAULT_TOKEN

if not token:
    st.sidebar.error("Missing APIFY_TOKEN in .streamlit/secrets.toml or environment.")
    st.stop()
load_dotenv()



def get_secret(name: str, default: str = "") -> str:
    try:
        return str(st.secrets[name]).strip()
    except Exception:
        return os.getenv(name, default).strip()


DEMO_MODE = False
MAX_RUNS_PER_SESSION = 3
APP_PASSWORD = get_secret("APP_PASSWORD", "demo123")

DEFAULT_TOKEN = get_secret("APIFY_TOKEN", "")
DEFAULT_ACTOR_ID = get_secret(
    "APIFY_ACTOR_ID",
    "gBBp9t5KjUcEt1ESS",
)

token = DEFAULT_TOKEN
if not token:
    st.sidebar.error("Missing APIFY_TOKEN in .streamlit/secrets.toml or environment.")
# -------------------------------------------------
# CONFIG
# -------------------------------------------------
BLOCKED_DOMAINS = {
    "console.apify.com",
    "apify.com",
    "www.apify.com",
    "linkedin.com",
    "www.linkedin.com",
}

PREFERRED_COLS = [
    "inputUrl",
    "url",
    "finalUrl",
    "companyName",
    "organization_name",
    "emails",
    "phones",
    "socialLinks",
    "linkedin",
    "facebook",
    "instagram",
    "twitter",
    "country",
]

DEFAULT_WEBSITES = """curlsask.ca/contact/
nicherecruitment.ca/contact-us.html
https://www.adinfosys.net"""

# -------------------------------------------------
# PAGE SETUP
# -------------------------------------------------
st.set_page_config(
    page_title="B2B Website Contact Intelligence Dashboard",
    page_icon="📇",
    layout="wide",
)

st.markdown(
    """
    <style>
        .block-container {
            padding-top: 1.2rem;
            padding-bottom: 2rem;
            max-width: 1400px;
        }

        h1, h2, h3 {
            letter-spacing: -0.02em;
        }

        .stMetric {
            background: linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.02));
            border: 1px solid rgba(128,128,128,0.18);
            border-radius: 18px;
            padding: 16px 18px;
            box-shadow: 0 6px 18px rgba(0,0,0,0.06);
        }

        div[data-testid="stDataFrame"] {
            border-radius: 16px;
            overflow: hidden;
            border: 1px solid rgba(128,128,128,0.18);
        }

        .premium-banner {
            padding: 1rem 1.2rem;
            border-radius: 18px;
            background: linear-gradient(135deg, rgba(34,197,94,0.10), rgba(59,130,246,0.10));
            border: 1px solid rgba(128,128,128,0.16);
            margin-bottom: 1rem;
        }

        .section-card {
            padding: 1rem 1rem 0.6rem 1rem;
            border-radius: 18px;
            border: 1px solid rgba(128,128,128,0.14);
            background: rgba(255,255,255,0.02);
            margin-bottom: 1rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# -------------------------------------------------
# HELPERS
# -------------------------------------------------
def validate_urls(urls: list[str]) -> tuple[list[str], list[str]]:
    good, bad = [], []
    blocked_domains_normalized = {d.replace("www.", "") for d in BLOCKED_DOMAINS}

    for u in urls:
        try:
            host = (urlparse(u).netloc or "").lower().replace("www.", "")
            if host in blocked_domains_normalized:
                bad.append(u)
            else:
                good.append(u)
        except Exception:
            bad.append(u)

    return good, bad


def normalize_urls(raw: str) -> List[str]:
    urls: List[str] = []

    for line in (raw or "").splitlines():
        u = line.strip()
        if not u:
            continue

        if not (u.startswith("http://") or u.startswith("https://")):
            u = "https://" + u

        parsed = urlparse(u)
        if not parsed.netloc:
            continue

        urls.append(u)

    seen = set()
    out: List[str] = []
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)

    return out


def extract_domain(value: Any) -> str:
    if value is None:
        return ""

    text = str(value).strip()
    if not text or text.lower() == "none":
        return ""

    if not text.startswith(("http://", "https://")):
        text = "https://" + text

    try:
        parsed = urlparse(text)
        host = (parsed.netloc or "").lower().replace("www.", "")
        return host
    except Exception:
        return ""


def count_listish(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, list):
        return len([x for x in value if str(x).strip()])
    text = str(value).strip()
    if not text or text.lower() == "none":
        return 0
    return 1


def flatten_cell(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(v) for v in value if str(v).strip())
    if pd.isna(value):
        return ""
    return str(value)


def get_lead_quality(row: pd.Series) -> str:
    score = 0

    if row.get("email_count", 0) > 0:
        score += 2
    if row.get("phone_count", 0) > 0:
        score += 1

    linkedin_value = row.get("linkedin", "")
    if linkedin_value and str(linkedin_value).strip().lower() not in {"", "none", "nan"}:
        score += 1

    if score >= 3:
        return "High"
    if score == 2:
        return "Medium"
    if score == 1:
        return "Low"
    return "Very Low"


def save_outputs_locally(df: pd.DataFrame) -> tuple[str, str]:
    output_dir = "outputs"
    os.makedirs(output_dir, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(output_dir, f"website_contact_export_{ts}.csv")
    xlsx_path = os.path.join(output_dir, f"website_contact_export_{ts}.xlsx")

    export_df = df.copy()
    for col in export_df.columns:
        export_df[col] = export_df[col].apply(flatten_cell)

    export_df.to_csv(csv_path, index=False)
    export_df.to_excel(xlsx_path, index=False)

    return csv_path, xlsx_path


def prepare_analytics(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()

    url_candidates = ["finalUrl", "url", "inputUrl", "website", "input_url"]
    url_source = None
    for col in url_candidates:
        if col in work.columns:
            url_source = col
            break

    if url_source:
        work["domain"] = work[url_source].apply(extract_domain)
    else:
        work["domain"] = ""

    if "emails" in work.columns:
        work["email_count"] = work["emails"].apply(count_listish)
    else:
        work["email_count"] = 0

    if "phones" in work.columns:
        work["phone_count"] = work["phones"].apply(count_listish)
    else:
        work["phone_count"] = 0

    if "country" not in work.columns:
        work["country"] = ""

    if "companyName" not in work.columns and "organization_name" not in work.columns:
        work["organization_name"] = ""

    if "linkedin" not in work.columns:
        work["linkedin"] = ""

    return work


def build_actor_input(
    urls: List[str],
    max_sites: int,
    max_pages_per_site: int,
    extract_social_links: bool,
    output_csv: bool,
    output_xlsx: bool,
    push_empty_record: bool,
) -> Dict[str, Any]:
    return {
        "startUrls": [{"url": u} for u in urls],
        "maxSites": int(max_sites),
        "maxPagesPerSite": int(max_pages_per_site),
        "extractSocialLinks": bool(extract_social_links),
        "outputCsv": bool(output_csv),
        "outputXlsx": bool(output_xlsx),
        "pushEmptyRecord": bool(push_empty_record),
    }


def validate_actor_id(actor_id: str) -> str:
    actor_id = actor_id.strip()

    if not actor_id:
        st.error("Actor ID is required.")
        st.stop()

    if actor_id.startswith("http://") or actor_id.startswith("https://"):
        st.error("Paste only the Actor ID, not the full URL.")
        st.stop()

    if " " in actor_id:
        st.error("Actor ID must not contain spaces.")
        st.stop()

    return actor_id


# -------------------------------------------------
# DASHBOARD HELPERS
# -------------------------------------------------
def safe_pct(num: float, den: float) -> float:
    return round((num / den) * 100, 1) if den and den > 0 else 0.0


def prepare_dashboard_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    if "company_name" not in df.columns:
        if "organization_name" in df.columns:
            df["company_name"] = df["organization_name"]
        elif "companyName" in df.columns:
            df["company_name"] = df["companyName"]
        else:
            df["company_name"] = ""

    if "website" not in df.columns:
        for col in ["finalUrl", "url", "inputUrl"]:
            if col in df.columns:
                df["website"] = df[col]
                break
        if "website" not in df.columns:
            df["website"] = ""

    if "industry" not in df.columns:
        df["industry"] = ""

    if "employee_estimate" not in df.columns:
        df["employee_estimate"] = 0

    if "has_linkedin" not in df.columns:
        if "linkedin" in df.columns:
            df["has_linkedin"] = (
                ~df["linkedin"]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.lower()
                .isin(["", "none", "nan"])
            )
        else:
            df["has_linkedin"] = False

    if "has_contact_page" not in df.columns:
        df["has_contact_page"] = False

    if "has_about_page" not in df.columns:
        df["has_about_page"] = False

    if "status" not in df.columns:
        df["status"] = ""

    expected_cols = [
        "company_name",
        "website",
        "industry",
        "country",
        "employee_estimate",
        "email_count",
        "phone_count",
        "has_linkedin",
        "has_contact_page",
        "has_about_page",
        "status",
        "opportunity_score",
    ]

    for col in expected_cols:
        if col not in df.columns:
            if col in ["email_count", "phone_count", "employee_estimate", "opportunity_score"]:
                df[col] = 0
            elif col in ["has_linkedin", "has_contact_page", "has_about_page"]:
                df[col] = False
            else:
                df[col] = ""

    for col in ["email_count", "phone_count", "employee_estimate", "opportunity_score"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    for col in ["has_linkedin", "has_contact_page", "has_about_page"]:
        df[col] = df[col].fillna(False).astype(bool)

    df["crm_ready"] = df["email_count"] > 0

    def readiness_tier(row: pd.Series) -> str:
        if row["email_count"] > 0 and row["phone_count"] > 0 and row["has_linkedin"]:
            return "High"
        elif row["email_count"] > 0:
            return "Medium"
        return "Low"

    df["readiness_tier"] = df.apply(readiness_tier, axis=1)

    df["coverage_score"] = (
        (df["email_count"] > 0).astype(int)
        + (df["phone_count"] > 0).astype(int)
        + df["has_linkedin"].astype(int)
        + df["has_contact_page"].astype(int)
        + df["has_about_page"].astype(int)
    )

    zero_mask = df["opportunity_score"].fillna(0) <= 0
    df.loc[zero_mask, "opportunity_score"] = (
        (df["email_count"] > 0).astype(int) * 40
        + (df["phone_count"] > 0).astype(int) * 20
        + df["has_linkedin"].astype(int) * 15
        + df["has_contact_page"].astype(int) * 10
        + df["has_about_page"].astype(int) * 5
        + np.clip(pd.to_numeric(df["employee_estimate"], errors="coerce").fillna(0), 0, 1000) / 1000 * 10
    ).round(1)

    return df


def render_kpis(df: pd.DataFrame) -> None:
    total = len(df)
    crm_ready_count = int(df["crm_ready"].sum())
    with_phone = int((df["phone_count"] > 0).sum())
    with_linkedin = int(df["has_linkedin"].sum())
    avg_opportunity = round(df["opportunity_score"].mean(), 1) if total else 0.0

    crm_ready_pct = safe_pct(crm_ready_count, total)
    phone_pct = safe_pct(with_phone, total)
    linkedin_pct = safe_pct(with_linkedin, total)

    c1, c2, c3 = st.columns(3)
    c4, c5, c6 = st.columns(3)

    c1.metric("Total Companies", f"{total:,}")
    c2.metric("CRM Ready", f"{crm_ready_count:,}", f"{crm_ready_pct}%")
    c3.metric("With Phone", f"{with_phone:,}", f"{phone_pct}%")
    c4.metric("Avg Opportunity Score", avg_opportunity)
    c5.metric("With LinkedIn", f"{with_linkedin:,}", f"{linkedin_pct}%")
    c6.metric("High Readiness", f"{int((df['readiness_tier'] == 'High').sum()):,}")


def render_top_opportunities(df: pd.DataFrame, top_n: int = 15) -> None:
    st.subheader("Top Opportunities")
    st.caption("Ranked by contact richness + lead quality score")

    cols_needed = [
        "company_name",
        "website",
        "industry",
        "country",
        "email_count",
        "phone_count",
        "has_linkedin",
        "readiness_tier",
        "opportunity_score",
    ]
    safe_cols = [c for c in cols_needed if c in df.columns]

    top_df = (
        df.sort_values(
            by=["opportunity_score", "email_count", "phone_count"],
            ascending=[False, False, False],
        )
        .loc[:, safe_cols]
        .head(top_n)
        .rename(columns={
            "company_name": "Company",
            "website": "Website",
            "industry": "Industry",
            "country": "Country",
            "email_count": "Emails",
            "phone_count": "Phones",
            "has_linkedin": "LinkedIn",
            "readiness_tier": "Readiness",
            "opportunity_score": "Opportunity Score",
        })
    )

    st.dataframe(top_df, use_container_width=True, hide_index=True)


def render_readiness_coverage_chart(df: pd.DataFrame) -> None:
    st.subheader("Readiness vs Data Coverage")

    chart_df = (
        df.groupby("readiness_tier", dropna=False)
        .agg(
            companies=("website", "count"),
            avg_coverage=("coverage_score", "mean"),
            avg_opportunity=("opportunity_score", "mean"),
        )
        .reset_index()
    )

    order = {"High": 0, "Medium": 1, "Low": 2}
    chart_df["sort_order"] = chart_df["readiness_tier"].map(order).fillna(99)
    chart_df = chart_df.sort_values("sort_order").drop(columns=["sort_order"])

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(chart_df["readiness_tier"], chart_df["companies"])
    ax.set_xlabel("Readiness Tier")
    ax.set_ylabel("Companies")
    ax.set_title("Companies by Readiness Tier")
    st.pyplot(fig)

    st.dataframe(
        chart_df.rename(columns={
            "readiness_tier": "Readiness Tier",
            "companies": "Companies",
            "avg_coverage": "Avg Coverage Score",
            "avg_opportunity": "Avg Opportunity Score",
        }),
        use_container_width=True,
        hide_index=True,
    )


def render_opportunity_distribution(df: pd.DataFrame) -> None:
    st.subheader("Opportunity Score Distribution")

    score_counts = df["opportunity_score"].fillna(0).round(0).astype(int).value_counts().sort_index()
    if score_counts.empty:
        st.info("No opportunity score data available.")
    else:
        st.bar_chart(score_counts, height=300)


def highlight_opportunity(val: Any) -> str:
    try:
        val = float(val)
    except Exception:
        return ""

    if val >= 70:
        return "background-color: #d4edda"
    elif val >= 40:
        return "background-color: #fff3cd"
    else:
        return "background-color: #f8d7da"


# -------------------------------------------------
# HEADER
# -------------------------------------------------
st.title("B2B Website Contact & Company Intelligence Dashboard")
st.markdown(
    """
    <div class="premium-banner">
        <b>CRM-ready lead intelligence</b><br>
        Run your Apify Actor, review extracted leads, filter results, and export clean contact datasets for outreach, sales, and research.
    </div>
    """,
    unsafe_allow_html=True,
)

# -------------------------------------------------
# ACCESS CONTROL
# -------------------------------------------------
password = st.text_input("Enter access password", type="password", key="app_password_input")

if not APP_PASSWORD:
    st.error("Missing APP_PASSWORD in .streamlit/secrets.toml or environment.")
    st.stop()

if password != APP_PASSWORD:
    st.warning("🔒 Please enter password to access the dashboard")
    st.stop()

st.caption("Secure demo environment — limited runs enabled")

# -------------------------------------------------
# SIDEBAR
# -------------------------------------------------
st.sidebar.divider()

st.sidebar.subheader("⚙️ Run Settings")

mode = st.sidebar.radio(
    "Mode",
    ["Live Run (Apify)", "Demo Mode"],
    index=0,
    key="run_mode_radio"
)

auto_save_local = st.sidebar.checkbox(
    "Auto-save CSV/XLSX locally",
    value=False,
    key="auto_save_local_checkbox"
)

show_debug = st.sidebar.checkbox(
    "Show debug panels",
    value=False,
    key="show_debug_checkbox"
)

st.sidebar.header("Apify Settings")


token = DEFAULT_TOKEN
if not token:
    st.sidebar.error("Missing APIFY_TOKEN in .streamlit/secrets.toml or environment.")

actor_id = st.sidebar.text_input(
    "Actor ID (username~actor-name or raw Actor ID)",
    value=DEFAULT_ACTOR_ID,
    help="Examples: gBBp9t5KjUcEt1ESS or adinfosys-labs~b2b-website-contact-company-intelligence-extractor-crm-ready",
).strip()

st.sidebar.divider()

st.sidebar.subheader("⚙️ Run Settings")

# --- Mode ---
mode = st.sidebar.radio(
    "Mode",
    ["Live Run (Apify)", "Demo Mode"],
    index=0
)

# --- Execution Options ---
st.sidebar.markdown("### 🔁 Execution")
auto_run = st.sidebar.checkbox("Auto-run on load", value=False)
auto_save_local = st.sidebar.checkbox("Auto-save CSV/XLSX locally", value=False)

# --- Output Options ---
st.sidebar.markdown("### 📦 Output")
export_csv = st.sidebar.checkbox("Enable CSV export", value=True)
export_xlsx = st.sidebar.checkbox("Enable Excel export", value=True)

# --- Advanced ---
with st.sidebar.expander("🛠 Advanced"):
    show_debug = st.checkbox("Show debug panels", value=False)
    max_results = st.number_input("Max results", min_value=1, max_value=1000, value=50)

st.sidebar.caption(
    "🔐 Tip: Set APP_PASSWORD, APIFY_TOKEN, and APIFY_ACTOR_ID in .streamlit/secrets.toml"
)
# -------------------------------------------------
# SESSION STATE
# -------------------------------------------------
if "last_run_id" not in st.session_state:
    st.session_state["last_run_id"] = None
if "last_dataset_id" not in st.session_state:
    st.session_state["last_dataset_id"] = None
if "last_items" not in st.session_state:
    st.session_state["last_items"] = []
if "last_saved_csv" not in st.session_state:
    st.session_state["last_saved_csv"] = None
if "last_saved_xlsx" not in st.session_state:
    st.session_state["last_saved_xlsx"] = None
if "run_count" not in st.session_state:
    st.session_state["run_count"] = 0

if st.session_state["run_count"] >= MAX_RUNS_PER_SESSION:
    st.error("Usage limit reached. Contact for full access.")
    st.stop()

# -------------------------------------------------
# INPUT AREA
# -------------------------------------------------
top_left, top_right = st.columns([2, 1], gap="large")

with top_left:
    st.subheader("Websites to scan")
    websites_text = st.text_area(
        "Enter one website per line (domain or full URL)",
        value=DEFAULT_WEBSITES,
        height=180,
        key="websites_text",
    )

with top_right:
    st.subheader("Actor options")
    max_sites = st.number_input("maxSites", min_value=1, max_value=100000, value=25, step=1)
    max_pages_per_site = st.number_input("maxPagesPerSite", min_value=1, max_value=500, value=4, step=1)
    extract_social_links = st.checkbox("extractSocialLinks", value=True)
    output_csv = st.checkbox("outputCsv", value=True)
    output_xlsx = st.checkbox("outputXlsx", value=True)
    push_empty_record = st.checkbox("pushEmptyRecord", value=False)
    timeout_minutes = st.number_input("Max wait time (minutes)", min_value=1, max_value=180, value=30, step=1)
st.divider()
st.markdown('<div class="section-card">', unsafe_allow_html=True)
quick1, quick2, quick3, quick4 = st.columns(4)
with quick1:
    st.metric("Configured maxSites", max_sites)
with quick2:
    st.metric("Pages per site", max_pages_per_site)
with quick3:
    st.metric("Social links", "On" if extract_social_links else "Off")
with quick4:
    st.metric("Auto-save", "On" if auto_save_local else "Off")
st.markdown("</div>", unsafe_allow_html=True)

# -------------------------------------------------
# RUN ACTOR
# -------------------------------------------------
st.info("Ready to extract leads from provided websites")

run_btn = st.button("🚀 Run Data Extraction", use_container_width=True, key="run_data_extraction_btn")

if run_btn:
    st.write("Running extraction...")
    st.session_state["run_count"] += 1

    urls = normalize_urls(websites_text or "")
    urls, blocked = validate_urls(urls)
    actor_id = validate_actor_id(actor_id)
    if blocked:
        st.warning(
            "These URLs look like dashboards/social platforms and were skipped:\n\n"
            + "\n".join(blocked)
        )

    if not urls:
        st.error("Please add at least one website URL.")
        st.stop()

    if not token:
        st.error("APIFY_TOKEN is required.")
        st.stop()

    actor_input = build_actor_input(
        urls=urls,
        max_sites=max_sites,
        max_pages_per_site=max_pages_per_site,
        extract_social_links=extract_social_links,
        output_csv=output_csv,
        output_xlsx=output_xlsx,
        push_empty_record=push_empty_record,
    )

    if show_debug:
        with st.expander("Parsed URLs", expanded=False):
            st.write(urls)
        with st.expander("Actor ID being used", expanded=False):
            st.code(repr(actor_id))
        with st.expander("Actor input payload", expanded=False):
            st.json(actor_input)

    client = ApifyClientLite(token=token)

    with st.spinner("Running extraction... this may take 20–60 seconds"):
        with st.status("Starting Actor run…", expanded=True) as status:
            try:
                run = client.start_actor_run(actor_id=actor_id, input_payload=actor_input)
                st.session_state["last_run_id"] = run.id
                status.write(f"Run started: **{run.id}** (status: {run.status})")

                status.update(label="Waiting for completion…", state="running")
                finished = client.wait_for_finish(
                    run_id=run.id,
                    poll_seconds=3.0,
                    max_wait_seconds=int(timeout_minutes) * 60,
                )

                status.write(f"Finished with status: **{finished.status}**")

                if finished.status != "SUCCEEDED":
                    status.update(label=f"Run finished: {finished.status}", state="error")
                    st.stop()

                dataset_id = finished.default_dataset_id
                if not dataset_id:
                    status.update(label="No default dataset returned by run.", state="error")
                    st.stop()

                st.session_state["last_dataset_id"] = dataset_id
                status.write(f"Default dataset: **{dataset_id}**")

                status.update(label="Loading dataset items…", state="running")
                items = client.list_all_dataset_items(dataset_id=dataset_id, page_size=1000)
                st.session_state["last_items"] = items

                status.update(
                    label=f"✅ Extraction completed successfully — {len(items)} leads ready",
                    state="complete",
                )
                st.success(f"Loaded {len(items)} leads. You can now filter, analyze, and export.")

            except Exception as e:
                status.update(label="Error", state="error")
                st.exception(e)
                st.stop()

# -------------------------------------------------
# RESULTS
# -------------------------------------------------
items = st.session_state.get("last_items") or []
df = pick_columns(safe_dataframe(items), preferred=PREFERRED_COLS)

if st.session_state.get("last_run_id"):
    st.subheader("Latest run")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Run ID", st.session_state.get("last_run_id") or "")
    m2.metric("Dataset ID", st.session_state.get("last_dataset_id") or "")
    m3.metric("Items", len(items))
    m4.metric("Actor ID", actor_id)

if st.session_state.get("last_dataset_id"):
    st.link_button(
        "Open dataset in Apify",
        f"https://console.apify.com/storage/datasets/{st.session_state['last_dataset_id']}",
    )

if not df.empty:
    analytics_df = prepare_analytics(df)
    analytics_df["lead_quality"] = analytics_df.apply(get_lead_quality, axis=1)

    if auto_save_local:
        csv_path, xlsx_path = save_outputs_locally(df)
        st.session_state["last_saved_csv"] = csv_path
        st.session_state["last_saved_xlsx"] = xlsx_path
        st.success(f"Saved locally:\n\nCSV: `{csv_path}`\n\nXLSX: `{xlsx_path}`")

    st.divider()
    st.markdown("## Smart Filters")

    filter1, filter2, filter3, filter4 = st.columns(4)

    countries = sorted(
        [
            c for c in analytics_df["country"].dropna().astype(str).unique()
            if c.strip() and c.strip().lower() != "none"
        ]
    )
    selected_country = filter1.selectbox("Country", ["All"] + countries)
    selected_min_emails = filter2.selectbox("Minimum emails", [0, 1, 2, 3, 5], index=1)
    selected_min_phones = filter3.selectbox("Minimum phones", [0, 1, 2, 3, 5], index=0)
    selected_quality = filter4.selectbox("Lead quality", ["All", "High", "Medium", "Low", "Very Low"])

    filtered_df = analytics_df.copy()

    if selected_country != "All":
        filtered_df = filtered_df[filtered_df["country"].astype(str) == selected_country]

    filtered_df = filtered_df[filtered_df["email_count"] >= selected_min_emails]
    filtered_df = filtered_df[filtered_df["phone_count"] >= selected_min_phones]

    if selected_quality != "All":
        filtered_df = filtered_df[filtered_df["lead_quality"] == selected_quality]

    filtered_df = filtered_df.copy()
    filtered_df["opportunity_score"] = (
        filtered_df["email_count"] * 3
        + filtered_df["phone_count"] * 1
        + filtered_df["lead_quality"].map({
            "High": 3,
            "Medium": 2,
            "Low": 1,
            "Very Low": 0,
        }).fillna(0)
    )

    dashboard_df = prepare_dashboard_df(filtered_df)

    st.divider()
    st.markdown("## Lead Intelligence")
    st.caption("AI-powered lead scoring and CRM readiness analysis")

    if len(filtered_df) < 5:
        st.info("Demo dataset — real runs typically include hundreds of leads.")

    if dashboard_df.empty:
        st.warning("No records match the selected filters.")
        st.stop()
    st.markdown("### Executive KPIs")
    render_kpis(dashboard_df)

    st.markdown("### 🤖 AI Insights")
    st.info(
        "Top companies show strong contact availability and high outreach readiness. Focus on high opportunity score targets first.")

    # paste the upgraded Recommended Targets block here

    st.divider()

    st.markdown("### 🎯 Recommended Targets")

    if not dashboard_df.empty:
        # Work on a copy
        recommendations_df = dashboard_df.copy()

        # Optional: make sure numeric columns are numeric
        for col in ["email_count", "phone_count", "opportunity_score"]:
            if col in recommendations_df.columns:
                recommendations_df[col] = pd.to_numeric(recommendations_df[col], errors="coerce").fillna(0)


        # Recommendation reason
        def build_reason(row):
            reasons = []

            if row.get("opportunity_score", 0) >= 80:
                reasons.append("very high score")
            elif row.get("opportunity_score", 0) >= 60:
                reasons.append("strong score")

            if row.get("email_count", 0) >= 2:
                reasons.append("multiple emails found")
            elif row.get("email_count", 0) >= 1:
                reasons.append("email available")

            if row.get("phone_count", 0) >= 1:
                reasons.append("phone available")

            if not reasons:
                return "good candidate based on available company data"

            return ", ".join(reasons)


        recommendations_df["recommendation_reason"] = recommendations_df.apply(build_reason, axis=1)

        top_targets = (
            recommendations_df
            .sort_values(["opportunity_score", "email_count", "phone_count"], ascending=[False, False, False])
            .head(3)
        )

        st.success("Top 3 companies recommended for review based on score and contact richness.")

        for i, (_, row) in enumerate(top_targets.iterrows(), start=1):
            company = row.get("organization_name", "Unknown company")
            country = row.get("country", "Unknown")
            emails = int(row.get("email_count", 0))
            phones = int(row.get("phone_count", 0))
            score = float(row.get("opportunity_score", 0))
            reason = row.get("recommendation_reason", "")

            with st.container():
                c1, c2, c3, c4 = st.columns([3, 1, 1, 1])

                with c1:
                    st.markdown(f"**{i}. {company}**")
                    st.caption(f"{country} • {reason}")

                with c2:
                    st.metric("Score", f"{score:.0f}")

                with c3:
                    st.metric("Emails", emails)

                with c4:
                    st.metric("Phones", phones)

                st.divider()
    else:
        st.warning("No data available yet. Run extraction to see recommendations.")

    st.divider()

    st.markdown("### Lead Quality Distribution")
    quality_order = ["High", "Medium", "Low", "Very Low"]
    quality_counts = (
        filtered_df["lead_quality"]
        .value_counts()
        .reindex(quality_order, fill_value=0)
    )
    if quality_counts.sum() > 0:
        st.bar_chart(quality_counts, height=220)
    else:
        st.info("No lead quality data available.")

    col1, col2 = st.columns(2)
    with col1:
        render_readiness_coverage_chart(dashboard_df)
    with col2:
        render_opportunity_distribution(dashboard_df)

    st.divider()
    st.markdown("### Data Coverage")

    coverage_data = pd.Series(
        {
            "Email Available": int((dashboard_df["email_count"] > 0).sum()),
            "Phone Available": int((dashboard_df["phone_count"] > 0).sum()),
            "LinkedIn Available": int(dashboard_df["has_linkedin"].sum()),
        }
    )
    if coverage_data.sum() == 0:
        st.info("No coverage data available.")
    else:
        st.bar_chart(coverage_data, height=220)

    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        domain_counts = (
            filtered_df[filtered_df["domain"].astype(str).str.strip() != ""]
            .groupby("domain")
            .size()
            .sort_values(ascending=False)
            .head(10)
        )
        st.markdown("**Top domains (by frequency)**")
        if not domain_counts.empty:
            st.bar_chart(domain_counts.sort_values(ascending=True), height=250)
        else:
            st.info("No domain data available for charting.")

    with chart_col2:
        country_counts = (
            filtered_df[filtered_df["country"].astype(str).str.strip().str.lower() != "none"]
            .groupby("country")
            .size()
            .sort_values(ascending=False)
            .head(10)
        )
        st.markdown("**Country distribution**")
        if not country_counts.empty:
            st.bar_chart(country_counts, height=250)
        else:
            st.info("No country data available for charting.")

    st.divider()
    st.markdown("## Results Preview")
    st.caption(
        f"Showing {len(filtered_df)} of {len(analytics_df)} records after filters. "
        "Clean, filtered dataset ready for export or CRM import."
    )

    preview_cols = [c for c in filtered_df.columns if c not in {"domain"}]

    preferred_preview_order = [
        "organization_name",
        "companyName",
        "lead_quality",
        "country",
        "email_count",
        "phone_count",
        "opportunity_score",
        "emails",
        "phones",
        "linkedin",
        "url",
        "finalUrl",
        "inputUrl",
    ]
    ordered_preview_cols = [c for c in preferred_preview_order if c in preview_cols]
    remaining_preview_cols = [c for c in preview_cols if c not in ordered_preview_cols]
    preview_cols = ordered_preview_cols + remaining_preview_cols

    style_subset = ["opportunity_score"] if "opportunity_score" in filtered_df.columns else []

    styled_df = (
        filtered_df[preview_cols]
        .style
        .format({
            "opportunity_score": "{:.1f}",
            "email_count": "{:.0f}",
            "phone_count": "{:.0f}",
        })
        .map(highlight_opportunity, subset=style_subset)
    )

    st.dataframe(styled_df, use_container_width=True)

    st.divider()
    st.markdown("## Downloads")
    st.caption("Export the filtered lead set in CSV or XLSX format.")

    export_df = filtered_df.copy()
    for col in export_df.columns:
        export_df[col] = export_df[col].apply(flatten_cell)

    csv_bytes = df_to_csv_bytes(export_df)
    xlsx_bytes = df_to_xlsx_bytes(export_df)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)

    d1, d2 = st.columns(2)
    with d1:
        st.download_button(
            "⬇ Download filtered CSV",
            data=csv_bytes,
            file_name="website_contact_export_filtered.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with d2:
        st.download_button(
            "⬇ Download filtered XLSX",
            data=xlsx_bytes,
            file_name="website_contact_export_filtered.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state.get("last_saved_csv") or st.session_state.get("last_saved_xlsx"):
        st.divider()
        st.markdown("## Local Saved Files")
        st.caption("Files saved locally during the latest run.")

        st.markdown('<div class="section-card">', unsafe_allow_html=True)

        if st.session_state.get("last_saved_csv"):
            st.code(st.session_state["last_saved_csv"])
        if st.session_state.get("last_saved_xlsx"):
            st.code(st.session_state["last_saved_xlsx"])

        st.markdown("</div>", unsafe_allow_html=True)

else:
    st.info("No results loaded yet. Run the Actor to fetch dataset items.")

st.caption("Built with Streamlit + Apify for contact discovery, company intelligence, and CRM-ready exports.")