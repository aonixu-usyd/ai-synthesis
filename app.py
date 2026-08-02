from __future__ import annotations

import ast
import html
import json
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="Synthesis Compass",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Newsreader:opsz,wght@6..72,600&display=swap');

    :root {
        --ink: #17211c;
        --muted: #66736c;
        --line: #dfe7e2;
        --paper: #f6f8f5;
        --card: #ffffff;
        --green: #176b52;
        --green-soft: #e4f3ec;
        --amber: #a96819;
    }
    .stApp { background: var(--paper); color: var(--ink); }
    html, body, [class*="css"] { font-family: "DM Sans", sans-serif; }
    .block-container { max-width: 1180px; padding-top: 2.1rem; padding-bottom: 5rem; }
    h1, h2, h3 { color: var(--ink); letter-spacing: -0.025em; }
    .hero {
        padding: 2.6rem 2.8rem;
        border-radius: 26px;
        color: white;
        background:
          radial-gradient(circle at 88% 12%, rgba(171,220,194,.28), transparent 29%),
          linear-gradient(135deg, #143d31 0%, #176b52 100%);
        box-shadow: 0 18px 50px rgba(20,61,49,.16);
        margin-bottom: 1.5rem;
    }
    .eyebrow { font-size: .77rem; letter-spacing: .14em; text-transform: uppercase; opacity: .72; font-weight: 700; }
    .hero h1 { font-family: "Newsreader", serif; color: white; font-size: clamp(2.15rem, 4vw, 3.55rem); margin: .35rem 0 .55rem; }
    .hero p { max-width: 720px; font-size: 1.05rem; line-height: 1.65; margin: 0; color: rgba(255,255,255,.82); }
    .step-label { margin: 1.7rem 0 .65rem; color: var(--green); font-size: .78rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }
    div[data-testid="stSelectbox"], div[data-testid="stMultiSelect"] { background: white; border-radius: 14px; }
    div[data-testid="stMetric"] { background: white; border: 1px solid var(--line); padding: 1rem 1.15rem; border-radius: 16px; }
    .result-card {
        background: var(--card); border: 1px solid var(--line); border-radius: 20px;
        padding: 1.45rem 1.55rem; margin: .8rem 0; box-shadow: 0 8px 26px rgba(30,55,43,.045);
    }
    .card-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; }
    .route-pill { display: inline-block; padding: .28rem .62rem; border-radius: 999px; background: var(--green-soft); color: var(--green); font-size: .73rem; font-weight: 700; }
    .result-card h3 { margin: .55rem 0 .2rem; font-size: 1.26rem; }
    .card-sub { color: var(--muted); font-size: .88rem; line-height: 1.45; }
    .cost { color: var(--green); font-size: 1.45rem; font-weight: 700; text-align: right; white-space: nowrap; }
    .cost-label { color: var(--muted); font-size: .72rem; font-weight: 600; text-align: right; }
    .facts { display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: .75rem; margin-top: 1.15rem; }
    .fact { background: #f7faf8; border-radius: 12px; padding: .7rem .8rem; min-height: 62px; }
    .fact b { display: block; color: var(--muted); font-size: .68rem; text-transform: uppercase; letter-spacing: .07em; margin-bottom: .25rem; }
    .fact span { color: var(--ink); font-size: .86rem; line-height: 1.35; }
    .empty-state { padding: 3rem 1.5rem; text-align: center; color: var(--muted); background: white; border: 1px dashed #c8d5ce; border-radius: 20px; }
    .method-note { color: var(--muted); font-size: .82rem; line-height: 1.55; }
    div[data-testid="stExpander"] { border: 1px solid var(--line); border-radius: 14px; background: white; }
    .stButton > button[kind="primary"] { background: var(--green); border-radius: 12px; border: 0; min-height: 45px; font-weight: 700; }
    @media (max-width: 720px) {
        .block-container { padding: 1rem .85rem 3rem; }
        .hero { padding: 1.8rem 1.3rem; border-radius: 20px; }
        .facts { grid-template-columns: repeat(2, minmax(0,1fr)); }
        .card-top { display: block; }
        .cost, .cost-label { text-align: left; }
        .cost { margin-top: .8rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


DATABASE_DIR = Path("data/database")


@st.cache_data
def load_database() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    materials = pd.read_csv(DATABASE_DIR / "materials.csv")
    methods = pd.read_csv(DATABASE_DIR / "methods.csv")
    evidence = pd.read_csv(DATABASE_DIR / "evidence.csv")
    ceder_path = DATABASE_DIR / "ceder_methods.csv.gz"
    if ceder_path.exists():
        ceder = pd.read_csv(ceder_path, compression="gzip", low_memory=False)
        ceder_methods = ceder.rename(columns={"cost_AUD_per_g": "precursor_cost_AUD_per_g"}).copy()
        ceder_methods["cost_unit"] = "AUD/g target"
        ceder_methods["cost_match_quality"] = "unmatched"
        ceder_methods["entry_id"] = ceder_methods["method_id"]
        ceder_methods["protocol_number"] = 1
        ceder_methods["time_min"] = pd.NA
        ceder_methods["material_group"] = "Ceder literature corpus"
        ceder_methods["protocol_source"] = ceder_methods["source_dataset"]
        methods = pd.concat([methods, ceder_methods], ignore_index=True, sort=False)

        ceder_evidence = pd.DataFrame({
            "method_id": ceder["method_id"],
            "doi": ceder["doi"],
            "precursors": ceder["precursors"],
            "full_synthesis_procedure": ceder["procedure"],
            "pH": pd.NA,
            "particle_size_nm": pd.NA,
            "diameter_nm": pd.NA,
            "washing": pd.NA,
            "post_treatment": ceder["reaction_string"],
        })
        evidence = pd.concat([evidence, ceder_evidence], ignore_index=True, sort=False)
    return materials, methods, evidence


materials_df, methods_df, evidence_df = load_database()
methods_df["precursor_cost_AUD_per_g"] = pd.to_numeric(
    methods_df["precursor_cost_AUD_per_g"], errors="coerce"
)

NULLS = {"", "nan", "none", "null", "<na>", "not reported", "not available"}
VALID_ELEMENTS = set("""
H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn
Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La
Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po
At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg
Cn Nh Fl Mc Lv Ts Og
""".split())


def clean(value: Any, default: str = "Not reported") -> str:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return default if text.lower() in NULLS else text


def esc(value: Any, default: str = "Not reported") -> str:
    return html.escape(clean(value, default))


def elements_of(value: Any) -> set[str]:
    return {item.strip() for item in clean(value, "").split(";") if item.strip()}


def parse_nested(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return value
    if not isinstance(value, str) or not value.strip():
        return value
    for parser in (json.loads, ast.literal_eval):
        try:
            return parser(value)
        except Exception:
            continue
    return value


def title_label(value: Any) -> str:
    text = clean(value)
    return text.replace("_", " ").title() if text != "Not reported" else text


def reaction_time(row: pd.Series) -> str:
    parts: list[str] = []
    hours = clean(row.get("time_h"), "")
    minutes = clean(row.get("time_min"), "")
    if hours:
        parts.append(hours if any(c.isalpha() for c in hours) else f"{hours} h")
    if minutes:
        parts.append(minutes if any(c.isalpha() for c in minutes) else f"{minutes} min")
    return " / ".join(parts) or "Not reported"


def temperature_text(value: Any) -> str:
    text = clean(value)
    if text == "Not reported" or "°" in text or any(char.isalpha() for char in text):
        return text
    return f"{text} °C"


def cost_confidence(row: pd.Series) -> tuple[str, str]:
    quality = clean(row.get("cost_match_quality"), "").lower()
    if "formula" in quality:
        return "High confidence", "Matched by target formula and synthesis route"
    if "morphology+route" in quality:
        return "Medium confidence", "Matched by literature record, morphology and route"
    if quality and quality != "unmatched":
        return "Indicative estimate", "Cost uses a broader precursor match"
    return "Insufficient data", "The record is insufficient for a reliable estimate"


def reagent_rows(value: Any) -> pd.DataFrame:
    parsed = parse_nested(value)
    if not isinstance(parsed, list):
        return pd.DataFrame()
    rows = []
    for item in parsed:
        if isinstance(item, dict):
            rows.append(
                {
                    "Reagent": clean(item.get("name"), ""),
                    "Formula": clean(item.get("formula"), ""),
                    "Reported amount": clean(item.get("amount"), ""),
                }
            )
    return pd.DataFrame(rows).replace("", pd.NA).dropna(axis=1, how="all")


st.markdown(
    """
    <section class="hero">
      <div class="eyebrow">Literature-derived synthesis intelligence</div>
      <h1>Synthesis Compass</h1>
      <p>Start with elemental composition and target morphology, then compare traceable synthesis routes and their theoretical metal-precursor cost for 1 g of target material.</p>
    </section>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="step-label">01 · Define the target</div>', unsafe_allow_html=True)

all_elements = sorted(
    {element for value in methods_df["elements"].dropna() for element in elements_of(value)}
    & VALID_ELEMENTS
)
all_morphologies = sorted(methods_df["morphology"].dropna().astype(str).unique(), key=str.lower)
reported_morphologies = [m for m in all_morphologies if m.lower() != "unspecified"]

selector_1, selector_2 = st.columns(2)
with selector_1:
    selected_elements = st.multiselect(
        "Target elements",
        all_elements,
        placeholder="For example: Cu, O",
        help="Select every element contained in the target material.",
    )
with selector_2:
    selected_morphology = st.selectbox(
        "Target morphology",
        ["Any morphology"] + reported_morphologies,
        format_func=title_label,
        help="Choose a morphology when it matters. Records whose source text did not state morphology can remain visible.",
    )

candidate = methods_df.copy()

match_col, _ = st.columns([1, 2])
with match_col:
    exact_elements = st.toggle(
        "Exact element set only",
        value=False,
        help="Off: include materials containing all selected elements. On: exclude materials with any additional elements.",
    )

if selected_elements:
    wanted = set(selected_elements)
    if exact_elements:
        candidate = candidate[candidate["elements"].apply(lambda x: elements_of(x) == wanted)]
    else:
        candidate = candidate[candidate["elements"].apply(lambda x: wanted.issubset(elements_of(x)))]

formula_options = sorted(candidate["formula"].dropna().astype(str).unique(), key=str.lower)
advanced_1, advanced_2, advanced_3 = st.columns([1.2, 1.2, .8])
with advanced_1:
    selected_formula = st.selectbox(
        "Target formula (optional)", ["All matching formulas"] + formula_options,
        help="Use the formula to distinguish materials with the same elements but different stoichiometry.",
    )
with advanced_2:
    sort_by = st.selectbox("Sort results", ["Lowest cost", "Lowest temperature", "Route name"])
with advanced_3:
    show_reference_estimates = st.toggle("Show indicative estimates", value=True)

include_unspecified = st.toggle(
    "Include literature routes with morphology not reported",
    value=True,
    help="Many synthesis papers report composition and procedure but do not state a standard morphology label.",
)

ready = bool(selected_elements)

if not ready:
    st.markdown(
        '<div class="empty-state"><strong>Select one or more target elements to begin</strong><br><br>You can then narrow the results by formula and morphology.</div>',
        unsafe_allow_html=True,
    )
    st.stop()

if selected_morphology == "Any morphology":
    filtered = candidate.copy()
    if not include_unspecified:
        filtered = filtered[filtered["morphology"].astype(str).str.lower() != "unspecified"]
else:
    allowed_morphologies = {selected_morphology}
    if include_unspecified:
        allowed_morphologies.add("Unspecified")
    filtered = candidate[candidate["morphology"].astype(str).isin(allowed_morphologies)].copy()
if selected_formula != "All matching formulas":
    filtered = filtered[filtered["formula"].astype(str) == selected_formula]
if not show_reference_estimates:
    filtered = filtered[
        filtered["precursor_cost_AUD_per_g"].notna()
        & filtered["cost_match_quality"].astype(str).str.contains("formula", case=False, na=False)
    ]

# Remove mechanically duplicated cards while preserving distinct literature protocols.
dedupe_columns = [
    "entry_id", "protocol_number", "formula", "morphology", "route",
    "precursor", "temperature_C", "time_h", "time_min",
]
filtered = filtered.drop_duplicates(subset=dedupe_columns)

filtered["_temperature"] = pd.to_numeric(
    filtered["temperature_C"].astype(str).str.extract(r"([-+]?\d*\.?\d+)")[0], errors="coerce"
)
filtered["_morph_rank"] = (
    filtered["morphology"].astype(str).str.lower() == "unspecified"
).astype(int)
if sort_by == "Lowest cost":
    filtered = filtered.sort_values(["_morph_rank", "precursor_cost_AUD_per_g", "route"], na_position="last")
elif sort_by == "Lowest temperature":
    filtered = filtered.sort_values(["_morph_rank", "_temperature", "route"], na_position="last")
else:
    filtered = filtered.sort_values(["_morph_rank", "route", "precursor_cost_AUD_per_g"], na_position="last")

total_results = len(filtered)
displayed = filtered.head(100)

st.markdown('<div class="step-label">02 · Matching routes</div>', unsafe_allow_html=True)

metric_1, metric_2, metric_3, metric_4 = st.columns(4)
metric_1.metric("Matching routes", total_results)
metric_2.metric("Target formulas", filtered["formula"].nunique() if not filtered.empty else 0)
metric_3.metric("Lowest theoretical cost", f"A${filtered['precursor_cost_AUD_per_g'].min():.2f}" if filtered["precursor_cost_AUD_per_g"].notna().any() else "—")
metric_4.metric("Literature records", filtered["entry_id"].nunique() if not filtered.empty else 0)

st.caption(
    "Cost basis: theoretical procurement cost (AUD) of the metal precursor required for 1 g of target phase. Yield losses, solvents, additives, energy, labour, equipment, purification and waste treatment are excluded."
)

if filtered.empty:
    st.warning("No route matches these filters. Try ‘Any morphology’, include records with morphology not reported, or turn off exact element matching.")
    st.stop()

if total_results > len(displayed):
    st.info(f"Showing the first {len(displayed):,} of {total_results:,} routes. Select a target formula to narrow the list.")

for rank, (_, method) in enumerate(displayed.iterrows(), start=1):
    cost = method.get("precursor_cost_AUD_per_g")
    confidence, confidence_note = cost_confidence(method)
    cost_text = f"A${cost:,.2f}" if pd.notna(cost) else "Pending"
    formula = esc(method.get("formula"))
    route = esc(title_label(method.get("route")))
    morphology = esc(title_label(method.get("morphology")))
    target = esc(method.get("target_material"), "")

    st.markdown(
        f"""
        <section class="result-card">
          <div class="card-top">
            <div>
              <span class="route-pill">Route {rank:02d} · {route}</span>
              <h3>{formula} · {morphology}</h3>
              <div class="card-sub">{target}</div>
            </div>
            <div>
              <div class="cost">{cost_text}</div>
              <div class="cost-label">per 1 g target · {esc(confidence)}</div>
            </div>
          </div>
          <div class="facts">
            <div class="fact"><b>Primary precursor</b><span>{esc(method.get('precursor'))}</span></div>
            <div class="fact"><b>Temperature</b><span>{html.escape(temperature_text(method.get('temperature_C')))}</span></div>
            <div class="fact"><b>Reaction time</b><span>{html.escape(reaction_time(method))}</span></div>
            <div class="fact"><b>Solvent system</b><span>{esc(method.get('solvent'))}</span></div>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    evidence = evidence_df[evidence_df["method_id"] == method["method_id"]]
    with st.expander(f"View route {rank:02d}: full procedure and cost basis"):
        st.markdown(f"**Cost note:** {confidence_note}. The source unit is `{clean(method.get('cost_unit'))}`.")
        if evidence.empty:
            st.info("No structured literature procedure is currently available for this route.")
            continue

        record = evidence.iloc[0]
        detail_1, detail_2, detail_3 = st.columns(3)
        detail_1.metric("DOI", clean(record.get("doi")))
        detail_2.metric("pH", clean(record.get("pH")))
        detail_3.metric("Particle size", clean(record.get("particle_size_nm"), clean(record.get("diameter_nm"))))

        st.markdown("#### Reported reagents and quantities")
        reagents = reagent_rows(record.get("precursors"))
        if reagents.empty:
            st.write(clean(record.get("precursors")))
        else:
            st.dataframe(reagents, width="stretch", hide_index=True)

        st.markdown("#### Experimental procedure")
        procedure = clean(record.get("full_synthesis_procedure"))
        st.info(procedure)

        workup = clean(record.get("washing"), "")
        post = clean(record.get("post_treatment"), "")
        if workup or post:
            st.markdown("#### Isolation and post-treatment")
            if workup:
                st.write(f"**Washing / separation:** {workup}")
            if post:
                st.write(f"**Post-treatment:** {post}")

        doi = clean(record.get("doi"), "")
        if doi:
            st.link_button("Open source publication", f"https://doi.org/{doi}")

st.divider()
st.markdown(
    '<p class="method-note">Data are derived from structured literature records. Theoretical costs support early route comparison and are not laboratory budgets. For composites, unreported yields or incomplete stoichiometry, use the confidence label when interpreting the estimate.</p>',
    unsafe_allow_html=True,
)
