from __future__ import annotations

import ast
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st


# ============================================================
# PAGE SETTINGS
# ============================================================

st.set_page_config(
    page_title="Materials Synthesis Explorer",
    page_icon="⚗️",
    layout="wide",
)

st.title("Materials Synthesis Explorer")

st.caption(
    "Search literature-derived synthesis routes by elemental composition, "
    "material formula, morphology, synthesis route and reported conditions."
)


# ============================================================
# PATHS
# ============================================================

DATABASE_DIR = Path("data/database")

MATERIALS_PATH = DATABASE_DIR / "materials.csv"
METHODS_PATH = DATABASE_DIR / "methods.csv"
EVIDENCE_PATH = DATABASE_DIR / "evidence.csv"


# ============================================================
# LOAD DATA
# ============================================================

@st.cache_data
def load_database():
    required_files = [
        MATERIALS_PATH,
        METHODS_PATH,
        EVIDENCE_PATH,
    ]

    missing = [
        str(path)
        for path in required_files
        if not path.exists()
    ]

    if missing:
        raise FileNotFoundError(
            "Missing database files:\n"
            + "\n".join(missing)
        )

    materials = pd.read_csv(MATERIALS_PATH)
    methods = pd.read_csv(METHODS_PATH)
    evidence = pd.read_csv(EVIDENCE_PATH)

    return materials, methods, evidence


try:
    materials_df, methods_df, evidence_df = load_database()

except Exception as exc:
    st.error(str(exc))
    st.stop()


# ============================================================
# HELPERS
# ============================================================

NULL_VALUES = {
    "",
    "nan",
    "none",
    "null",
    "<na>",
    "not reported",
    "not available",
}


def clean_text(
    value: Any,
    default: str = "Not reported",
) -> str:
    if value is None:
        return default

    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass

    text = str(value).strip()

    if text.lower() in NULL_VALUES:
        return default

    return text


def has_value(value: Any) -> bool:
    return clean_text(value, default="") != ""


def parse_nested(value: Any):
    if isinstance(value, (list, dict)):
        return value

    if not isinstance(value, str):
        return value

    text = value.strip()

    if not text:
        return value

    try:
        return json.loads(text)
    except Exception:
        pass

    try:
        return ast.literal_eval(text)
    except Exception:
        return value


def parse_elements(value: Any) -> list[str]:
    if not has_value(value):
        return []

    return [
        element.strip()
        for element in str(value).split(";")
        if element.strip()
    ]


def parse_numeric(value: Any) -> float | None:
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()

    if not text:
        return None

    import re

    numbers = re.findall(
        r"[-+]?\d*\.?\d+",
        text,
    )

    if not numbers:
        return None

    try:
        return float(numbers[0])
    except ValueError:
        return None


def title_case_label(value: Any) -> str:
    text = clean_text(value)

    if text == "Not reported":
        return text

    return text.replace("_", " ").title()


def show_inline_field(
    label: str,
    value: Any,
) -> None:
    if has_value(value):
        st.markdown(
            f"**{label}:** {clean_text(value)}"
        )


def morphology_icon(morphology: str) -> str:
    mapping = {
        "nanoparticle": "●",
        "nanosphere": "◉",
        "nanowire": "│",
        "nanorod": "▬",
        "nanoplate": "▰",
        "nanosheet": "▱",
        "nanocube": "■",
        "nanotriangle": "▲",
        "nanoprism": "△",
        "nanoflower": "✿",
        "nanopetal": "❧",
        "dendrite": "⌁",
        "porous": "◌",
        "hollow": "◎",
        "film": "▭",
    }

    return mapping.get(
        str(morphology).lower(),
        "◆",
    )


def display_reagent_table(value: Any) -> None:
    if not has_value(value):
        st.write("Not reported")
        return

    parsed = parse_nested(value)

    if not isinstance(parsed, list):
        st.write(clean_text(value))
        return

    rows = []

    for item in parsed:
        if isinstance(item, dict):
            rows.append(
                {
                    "Reagent": clean_text(
                        item.get("name"),
                        default="",
                    ),
                    "Formula": clean_text(
                        item.get("formula"),
                        default="",
                    ),
                    "Amount": clean_text(
                        item.get("amount"),
                        default="",
                    ),
                    "Role / notes": clean_text(
                        item.get("role")
                        or item.get("molecular_weight"),
                        default="",
                    ),
                }
            )
        else:
            rows.append(
                {
                    "Reagent": str(item),
                    "Formula": "",
                    "Amount": "",
                    "Role / notes": "",
                }
            )

    reagent_df = pd.DataFrame(rows)

    empty_columns = [
        column
        for column in reagent_df.columns
        if reagent_df[column]
        .astype(str)
        .str.strip()
        .eq("")
        .all()
    ]

    reagent_df = reagent_df.drop(
        columns=empty_columns,
        errors="ignore",
    )

    st.dataframe(
        reagent_df,
        use_container_width=True,
        hide_index=True,
    )


def display_additives(value: Any) -> None:
    if not has_value(value):
        st.write("Not reported")
        return

    parsed = parse_nested(value)

    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict):
                label = (
                    item.get("name")
                    or item.get("formula")
                    or str(item)
                )
                st.write(f"• {label}")
            else:
                st.write(f"• {item}")
    else:
        st.write(clean_text(value))


# ============================================================
# PREPARE NUMERIC COLUMNS
# ============================================================

methods_df["precursor_cost_AUD_per_g"] = pd.to_numeric(
    methods_df["precursor_cost_AUD_per_g"],
    errors="coerce",
)

methods_df["_temperature_numeric"] = (
    methods_df["temperature_C"]
    .apply(parse_numeric)
)

methods_df["_time_h_numeric"] = (
    methods_df["time_h"]
    .apply(parse_numeric)
)

methods_df["_time_min_numeric"] = (
    methods_df["time_min"]
    .apply(parse_numeric)
)


# ============================================================
# SIDEBAR FILTERS
# ============================================================

st.sidebar.header("Search synthesis database")


# ------------------------------------------------------------
# ELEMENT SELECTION
# ------------------------------------------------------------

all_elements = sorted(
    {
        element
        for value in methods_df["elements"].dropna()
        for element in parse_elements(value)
    }
)

selected_elements = st.sidebar.multiselect(
    "Elements",
    options=all_elements,
    placeholder="Select one or more elements",
)

element_match_mode = st.sidebar.radio(
    "Element matching",
    options=[
        "Contains all selected elements",
        "Contains any selected element",
        "Exact element set",
    ],
    index=0,
)


# ------------------------------------------------------------
# FORMULA
# ------------------------------------------------------------

formula_options = sorted(
    methods_df["formula"]
    .dropna()
    .astype(str)
    .unique(),
    key=str.lower,
)

selected_formula = st.sidebar.selectbox(
    "Formula",
    options=["All"] + formula_options,
)


# ------------------------------------------------------------
# MORPHOLOGY
# ------------------------------------------------------------

morphology_options = sorted(
    methods_df["morphology"]
    .dropna()
    .astype(str)
    .unique(),
    key=str.lower,
)

selected_morphologies = st.sidebar.multiselect(
    "Morphology",
    options=morphology_options,
    placeholder="All morphologies",
)


# ------------------------------------------------------------
# SYNTHESIS ROUTE
# ------------------------------------------------------------

route_options = sorted(
    methods_df["route"]
    .dropna()
    .astype(str)
    .unique(),
    key=str.lower,
)

selected_routes = st.sidebar.multiselect(
    "Synthesis route",
    options=route_options,
    placeholder="All synthesis routes",
)


# ------------------------------------------------------------
# MATERIAL GROUP
# ------------------------------------------------------------

material_group_options = sorted(
    methods_df["material_group"]
    .dropna()
    .astype(str)
    .unique(),
)

selected_material_groups = st.sidebar.multiselect(
    "Material group",
    options=material_group_options,
    default=material_group_options,
)


# ------------------------------------------------------------
# COST
# ------------------------------------------------------------

known_costs = (
    methods_df["precursor_cost_AUD_per_g"]
    .dropna()
)

if not known_costs.empty:
    min_cost = float(known_costs.min())
    max_cost = float(known_costs.max())

    selected_cost_range = st.sidebar.slider(
        "Theoretical precursor cost range",
        min_value=float(math.floor(min_cost)),
        max_value=float(math.ceil(max_cost)),
        value=(
            float(math.floor(min_cost)),
            float(math.ceil(max_cost)),
        ),
        step=0.1,
    )
else:
    selected_cost_range = None


include_unknown_cost = st.sidebar.checkbox(
    "Include methods without cost",
    value=True,
)


# ------------------------------------------------------------
# SORT
# ------------------------------------------------------------

sort_option = st.sidebar.selectbox(
    "Sort results by",
    options=[
        "Lowest precursor cost",
        "Lowest temperature",
        "Shortest reaction time",
        "Formula",
        "Morphology",
    ],
)


max_results = st.sidebar.slider(
    "Maximum results",
    min_value=10,
    max_value=100,
    value=50,
    step=10,
)


# ============================================================
# FILTER METHODS
# ============================================================

filtered = methods_df.copy()


# ------------------------------------------------------------
# ELEMENT FILTER
# ------------------------------------------------------------

if selected_elements:
    selected_set = set(selected_elements)

    def element_match(value):
        method_elements = set(
            parse_elements(value)
        )

        if (
            element_match_mode
            == "Contains all selected elements"
        ):
            return selected_set.issubset(
                method_elements
            )

        if (
            element_match_mode
            == "Contains any selected element"
        ):
            return bool(
                selected_set.intersection(
                    method_elements
                )
            )

        return method_elements == selected_set

    filtered = filtered[
        filtered["elements"].apply(
            element_match
        )
    ]


# ------------------------------------------------------------
# FORMULA FILTER
# ------------------------------------------------------------

if selected_formula != "All":
    filtered = filtered[
        filtered["formula"].astype(str)
        == selected_formula
    ]


# ------------------------------------------------------------
# MORPHOLOGY FILTER
# ------------------------------------------------------------

if selected_morphologies:
    filtered = filtered[
        filtered["morphology"].isin(
            selected_morphologies
        )
    ]


# ------------------------------------------------------------
# ROUTE FILTER
# ------------------------------------------------------------

if selected_routes:
    filtered = filtered[
        filtered["route"].isin(
            selected_routes
        )
    ]


# ------------------------------------------------------------
# MATERIAL GROUP FILTER
# ------------------------------------------------------------

if selected_material_groups:
    filtered = filtered[
        filtered["material_group"].isin(
            selected_material_groups
        )
    ]


# ------------------------------------------------------------
# COST FILTER
# ------------------------------------------------------------

if selected_cost_range is not None:
    low_cost, high_cost = selected_cost_range

    known_cost_mask = (
        filtered["precursor_cost_AUD_per_g"]
        .between(
            low_cost,
            high_cost,
            inclusive="both",
        )
    )

    if include_unknown_cost:
        cost_mask = (
            known_cost_mask
            | filtered[
                "precursor_cost_AUD_per_g"
            ].isna()
        )
    else:
        cost_mask = known_cost_mask

    filtered = filtered[cost_mask]


# ============================================================
# SORT RESULTS
# ============================================================

if sort_option == "Lowest precursor cost":
    filtered = filtered.sort_values(
        by=[
            "precursor_cost_AUD_per_g",
            "formula",
            "morphology",
        ],
        ascending=[
            True,
            True,
            True,
        ],
        na_position="last",
    )

elif sort_option == "Lowest temperature":
    filtered = filtered.sort_values(
        by=[
            "_temperature_numeric",
            "formula",
        ],
        ascending=True,
        na_position="last",
    )

elif sort_option == "Shortest reaction time":
    filtered["_combined_time_min"] = (
        filtered["_time_h_numeric"]
        .fillna(0)
        * 60
        + filtered["_time_min_numeric"]
        .fillna(0)
    )

    no_time_mask = (
        filtered["_time_h_numeric"].isna()
        & filtered["_time_min_numeric"].isna()
    )

    filtered.loc[
        no_time_mask,
        "_combined_time_min",
    ] = pd.NA

    filtered = filtered.sort_values(
        by=[
            "_combined_time_min",
            "formula",
        ],
        ascending=True,
        na_position="last",
    )

elif sort_option == "Formula":
    filtered = filtered.sort_values(
        by=[
            "formula",
            "morphology",
        ],
    )

elif sort_option == "Morphology":
    filtered = filtered.sort_values(
        by=[
            "morphology",
            "formula",
        ],
    )


filtered = (
    filtered
    .head(max_results)
    .reset_index(drop=True)
)


# ============================================================
# DATABASE SUMMARY
# ============================================================

summary_col1, summary_col2, summary_col3, summary_col4 = (
    st.columns(4)
)

summary_col1.metric(
    "Matching methods",
    len(filtered),
)

summary_col2.metric(
    "Unique formulas",
    filtered["formula"].nunique(),
)

summary_col3.metric(
    "Morphologies",
    filtered["morphology"].nunique(),
)

summary_col4.metric(
    "Supporting records",
    filtered["entry_id"].nunique(),
)


# ============================================================
# ACTIVE FILTER SUMMARY
# ============================================================

active_filters = []

if selected_elements:
    active_filters.append(
        "Elements: "
        + ", ".join(selected_elements)
    )

if selected_formula != "All":
    active_filters.append(
        f"Formula: {selected_formula}"
    )

if selected_morphologies:
    active_filters.append(
        "Morphology: "
        + ", ".join(selected_morphologies)
    )

if selected_routes:
    active_filters.append(
        "Routes: "
        + ", ".join(selected_routes)
    )


if active_filters:
    st.info(
        " · ".join(active_filters)
    )


# ============================================================
# NO RESULTS
# ============================================================

if filtered.empty:
    st.warning(
        "No synthesis routes match the selected filters."
    )
    st.stop()


# ============================================================
# COMPACT RESULTS TABLE
# ============================================================

st.subheader("Matching synthesis methods")


table_df = filtered[
    [
        "formula",
        "elements",
        "morphology",
        "route",
        "precursor",
        "temperature_C",
        "time_h",
        "time_min",
        "precursor_cost_AUD_per_g",
        "cost_unit",
        "entry_id",
    ]
].copy()


table_df.insert(
    0,
    "Rank",
    range(1, len(table_df) + 1),
)


table_df = table_df.rename(
    columns={
        "formula": "Formula",
        "elements": "Elements",
        "morphology": "Morphology",
        "route": "Route",
        "precursor": "Precursor",
        "temperature_C": "Temperature",
        "time_h": "Time (h)",
        "time_min": "Time (min)",
        "precursor_cost_AUD_per_g": "Cost",
        "cost_unit": "Cost unit",
        "entry_id": "Entry ID",
    }
)


st.dataframe(
    table_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Cost": st.column_config.NumberColumn(
            format="A$ %.4f",
        ),
    },
)


# ============================================================
# METHOD CARDS
# ============================================================

st.subheader("Method cards")


for result_index, method in filtered.iterrows():

    formula = clean_text(
        method.get("formula")
    )

    morphology = clean_text(
        method.get("morphology")
    )

    route = clean_text(
        method.get("route")
    )

    precursor = clean_text(
        method.get("precursor")
    )

    icon = morphology_icon(
        morphology
    )

    cost = method.get(
        "precursor_cost_AUD_per_g"
    )

    if pd.notna(cost):
        cost_text = (
            f"A${cost:,.4f} "
            f"{clean_text(method.get('cost_unit'))}"
        )
    else:
        cost_text = "Cost unavailable"

    title = (
        f"{icon} {formula} · "
        f"{title_case_label(morphology)} · "
        f"{title_case_label(route)}"
    )

    with st.container(border=True):

        header_col1, header_col2 = (
            st.columns(
                [4, 1]
            )
        )

        with header_col1:
            st.markdown(
                f"### {title}"
            )

            target_material = clean_text(
                method.get(
                    "target_material"
                ),
                default="",
            )

            if target_material:
                st.caption(target_material)

        with header_col2:
            st.metric(
                "Precursor cost",
                cost_text,
            )

        info_col1, info_col2, info_col3, info_col4 = (
            st.columns(4)
        )

        info_col1.markdown(
            f"**Elements**  \n"
            f"{clean_text(method.get('elements'))}"
        )

        info_col2.markdown(
            f"**Precursor**  \n"
            f"{precursor}"
        )

        info_col3.markdown(
            f"**Temperature**  \n"
            f"{clean_text(method.get('temperature_C'))}"
        )

        time_text = []

        if has_value(method.get("time_h")):
            time_text.append(
                f"{clean_text(method.get('time_h'))} h"
            )

        if has_value(method.get("time_min")):
            time_text.append(
                f"{clean_text(method.get('time_min'))} min"
            )

        info_col4.markdown(
            f"**Reaction time**  \n"
            f"{' / '.join(time_text) if time_text else 'Not reported'}"
        )

        show_inline_field(
            "Solvent",
            method.get("solvent"),
        )

        show_inline_field(
            "Cost matching",
            method.get(
                "cost_match_quality"
            ),
        )

        method_id = method[
            "method_id"
        ]

        matched_evidence = evidence_df[
            evidence_df["method_id"]
            == method_id
        ].copy()

        with st.expander(
            "View synthesis details",
            expanded=False,
        ):

            if matched_evidence.empty:
                st.warning(
                    "No supporting evidence record was found."
                )

            for _, evidence in matched_evidence.iterrows():

                entry_id = clean_text(
                    evidence.get("entry_id")
                )

                doi = clean_text(
                    evidence.get("doi"),
                    default="",
                )

                st.markdown(
                    f"#### Literature record {entry_id}"
                )

                if doi:
                    st.caption(
                        f"DOI: {doi}"
                    )

                overview_col1, overview_col2, overview_col3 = (
                    st.columns(3)
                )

                overview_col1.metric(
                    "Morphology",
                    title_case_label(
                        evidence.get(
                            "morphology"
                        )
                    ),
                )

                overview_col2.metric(
                    "Route",
                    title_case_label(
                        evidence.get(
                            "route"
                        )
                    ),
                )

                overview_col3.metric(
                    "Reported size",
                    clean_text(
                        evidence.get(
                            "particle_size_nm"
                        )
                        or evidence.get(
                            "diameter_nm"
                        )
                    ),
                )

                st.markdown("##### Reagents")

                display_reagent_table(
                    evidence.get("precursors")
                )

                reagent_col1, reagent_col2 = (
                    st.columns(2)
                )

                with reagent_col1:
                    st.markdown(
                        "**Additives / stabilisers**"
                    )
                    display_additives(
                        evidence.get(
                            "additives"
                        )
                    )

                with reagent_col2:
                    st.markdown(
                        "**Solvent**"
                    )
                    st.write(
                        clean_text(
                            evidence.get(
                                "solvent"
                            )
                        )
                    )

                st.markdown(
                    "##### Reaction conditions"
                )

                condition_col1, condition_col2, condition_col3 = (
                    st.columns(3)
                )

                condition_col1.metric(
                    "Temperature",
                    clean_text(
                        evidence.get(
                            "temperature_C"
                        )
                    ),
                )

                reaction_time = []

                if has_value(
                    evidence.get("time_h")
                ):
                    reaction_time.append(
                        f"{clean_text(evidence.get('time_h'))} h"
                    )

                if has_value(
                    evidence.get("time_min")
                ):
                    reaction_time.append(
                        f"{clean_text(evidence.get('time_min'))} min"
                    )

                condition_col2.metric(
                    "Time",
                    " / ".join(
                        reaction_time
                    )
                    if reaction_time
                    else "Not reported",
                )

                condition_col3.metric(
                    "pH",
                    clean_text(
                        evidence.get("pH")
                    ),
                )

                show_inline_field(
                    "Vessel / pressure",
                    evidence.get(
                        "pressure_or_vessel"
                    ),
                )

                show_inline_field(
                    "Atmosphere",
                    evidence.get(
                        "atmosphere"
                    ),
                )

                mixing_sequence = (
                    evidence.get(
                        "mixing_or_addition_sequence"
                    )
                )

                if has_value(mixing_sequence):
                    st.markdown(
                        "##### Addition and mixing sequence"
                    )
                    st.write(
                        clean_text(
                            mixing_sequence
                        )
                    )

                workup_present = any(
                    has_value(
                        evidence.get(column)
                    )
                    for column in [
                        "washing",
                        "drying_temperature_C",
                        "calcination_temperature_C",
                        "post_treatment",
                    ]
                )

                if workup_present:
                    st.markdown(
                        "##### Isolation and post-treatment"
                    )

                    show_inline_field(
                        "Washing / separation",
                        evidence.get(
                            "washing"
                        ),
                    )

                    show_inline_field(
                        "Drying temperature",
                        evidence.get(
                            "drying_temperature_C"
                        ),
                    )

                    show_inline_field(
                        "Calcination temperature",
                        evidence.get(
                            "calcination_temperature_C"
                        ),
                    )

                    show_inline_field(
                        "Post-treatment",
                        evidence.get(
                            "post_treatment"
                        ),
                    )

                full_procedure = (
                    evidence.get(
                        "full_synthesis_procedure"
                    )
                )

                st.markdown(
                    "##### Consolidated synthesis procedure"
                )

                if has_value(full_procedure):
                    st.info(
                        clean_text(
                            full_procedure
                        )
                    )
                else:
                    st.warning(
                        "No consolidated synthesis procedure "
                        "is available for this record."
                    )

                notes = evidence.get("notes")

                if has_value(notes):
                    st.markdown(
                        "##### Additional notes"
                    )
                    st.write(
                        clean_text(notes)
                    )

                confidence = evidence.get(
                    "confidence"
                )

                if has_value(confidence):
                    with st.expander(
                        "Extraction confidence",
                        expanded=False,
                    ):
                        parsed_confidence = (
                            parse_nested(confidence)
                        )

                        if isinstance(
                            parsed_confidence,
                            dict,
                        ):
                            st.json(
                                parsed_confidence
                            )
                        else:
                            st.write(
                                clean_text(
                                    confidence
                                )
                            )


# ============================================================
# FOOTNOTE
# ============================================================

st.divider()

st.caption(
    "Costs represent theoretical metal-precursor procurement costs, "
    "not complete synthesis costs. They exclude yield losses, solvents, "
    "additives, energy, labour, purification, equipment and waste treatment."
)