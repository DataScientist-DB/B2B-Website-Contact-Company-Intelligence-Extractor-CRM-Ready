from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List
from urllib.parse import urlparse

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from apify_api import ApifyClientLite
from export_utils import df_to_csv_bytes, df_to_xlsx_bytes, pick_columns, safe_dataframe

# -------------------------------------------------
# LOAD ENV / SECRETS
# -------------------------------------------------
load_dotenv()


def get_secret(name: str, default: str = "") -> str:
    try:
        return str(st.secrets[name]).strip()
    except Exception:
        return os.getenv(name, default).strip()


DEFAULT_TOKEN = get_secret("APIFY_TOKEN", "")
DEFAULT_ACTOR_ID = get_secret(
    "APIFY_ACTOR_ID",
    "gBBp9t5KjUcEt1ESS",
)

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
    if not text:
        return ""
    try:
        parsed = urlparse(text)
        host = parsed.netloc or parsed.path.split("/")[0]
        return host.lower().replace("www.", "")
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

    if "finalUrl" in work.columns:
        url_source = "finalUrl"
    elif "url" in work.columns:
        url_source = "url"
    elif "inputUrl" in work.columns:
        url_source = "inputUrl"
    else:
        url_source = None

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

    # Accept either raw actor ID like gBBp9t5KjUcEt1ESS
    # or owner~actor-name format
    return actor_id


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
            padding-top: 1.5rem;
            padding-bottom: 2rem;
        }
        .stMetric {
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(128,128,128,0.20);
            border-radius: 16px;
            padding: 14px 16px;
        }
        div[data-testid="stDataFrame"] {
            border-radius: 14px;
            overflow: hidden;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("B2B Website Contact & Company Intelligence Dashboard")
st.caption("Run your Apify Actor, review extracted leads, filter results, and export clean CRM-ready data.")

# -------------------------------------------------
# SIDEBAR
# -------------------------------------------------
st.sidebar.header("Apify Settings")

token = st.sidebar.text_input(
    "APIFY_TOKEN",
    value=DEFAULT_TOKEN,
    type="password",
).strip()

actor_id = st.sidebar.text_input(
    "Actor ID (username~actor-name or raw Actor ID)",
    value=DEFAULT_ACTOR_ID,
    help="Examples: gBBp9t5KjUcEt1ESS or adinfosys-labs~b2b-website-contact-company-intelligence-extractor-crm-ready",
).strip()

st.sidebar.divider()
st.sidebar.subheader("Run Options")
auto_save_local = st.sidebar.checkbox("Auto-save CSV/XLSX locally", value=True)
show_debug = st.sidebar.checkbox("Show debug panels", value=False)
st.sidebar.caption("Tip: Put APIFY_TOKEN and APIFY_ACTOR_ID into .env or Streamlit secrets to avoid retyping.")

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

quick1, quick2, quick3, quick4 = st.columns(4)
with quick1:
    st.metric("Configured maxSites", max_sites)
with quick2:
    st.metric("Pages per site", max_pages_per_site)
with quick3:
    st.metric("Social links", "On" if extract_social_links else "Off")
with quick4:
    st.metric("Auto-save", "On" if auto_save_local else "Off")

run_btn = st.button("▶ Run Apify Actor", type="primary", use_container_width=True)

# -------------------------------------------------
# RUN ACTOR
# -------------------------------------------------
if run_btn:
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

            status.update(label=f"Done. Loaded {len(items)} items.", state="complete")

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

    total_items = len(analytics_df)
    total_emails = int(analytics_df["email_count"].sum())
    total_phones = int(analytics_df["phone_count"].sum())
    unique_domains = int(analytics_df["domain"].replace("", pd.NA).dropna().nunique())

    st.divider()
    st.subheader("Executive summary")

    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Leads captured", total_items)
    s2.metric("Emails found", total_emails)
    s3.metric("Phones found", total_phones)
    s4.metric("Unique domains", unique_domains)

    if auto_save_local:
        csv_path, xlsx_path = save_outputs_locally(df)
        st.session_state["last_saved_csv"] = csv_path
        st.session_state["last_saved_xlsx"] = xlsx_path
        st.success(f"Saved locally:\n\nCSV: `{csv_path}`\n\nXLSX: `{xlsx_path}`")

    st.divider()
    st.subheader("Smart filters")

    filter1, filter2, filter3 = st.columns(3)

    countries = sorted(
        [
            c for c in analytics_df["country"].dropna().astype(str).unique()
            if c.strip() and c.strip().lower() != "none"
        ]
    )
    selected_country = filter1.selectbox("Country", ["All"] + countries)
    selected_min_emails = filter2.selectbox("Minimum emails", [0, 1, 2, 3, 5], index=1)
    selected_min_phones = filter3.selectbox("Minimum phones", [0, 1, 2, 3, 5], index=0)

    filtered_df = analytics_df.copy()

    if selected_country != "All":
        filtered_df = filtered_df[filtered_df["country"].astype(str) == selected_country]

    filtered_df = filtered_df[filtered_df["email_count"] >= selected_min_emails]
    filtered_df = filtered_df[filtered_df["phone_count"] >= selected_min_phones]

    st.divider()
    st.subheader("Lead intelligence")

    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        domain_counts = (
            filtered_df[filtered_df["domain"].astype(str).str.strip() != ""]
            .groupby("domain")
            .size()
            .sort_values(ascending=False)
            .head(10)
        )
        st.markdown("**Top domains**")
        if not domain_counts.empty:
            st.bar_chart(domain_counts)
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
            st.bar_chart(country_counts)
        else:
            st.info("No country data available for charting.")

    st.divider()
    st.subheader("Results preview")
    st.caption(f"Showing {len(filtered_df)} of {len(analytics_df)} records after filters.")

    preview_cols = [c for c in filtered_df.columns if c not in {"email_count", "phone_count", "domain"}]
    st.dataframe(filtered_df[preview_cols], use_container_width=True, height=420)

    st.subheader("Downloads")

    export_df = filtered_df.copy()
    for col in export_df.columns:
        export_df[col] = export_df[col].apply(flatten_cell)

    csv_bytes = df_to_csv_bytes(export_df)
    xlsx_bytes = df_to_xlsx_bytes(export_df)

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

    if st.session_state.get("last_saved_csv") or st.session_state.get("last_saved_xlsx"):
        st.subheader("Local saved files")
        if st.session_state.get("last_saved_csv"):
            st.code(st.session_state["last_saved_csv"])
        if st.session_state.get("last_saved_xlsx"):
            st.code(st.session_state["last_saved_xlsx"])
else:
    st.info("No results loaded yet. Run the Actor to fetch dataset items.")