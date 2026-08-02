#!/usr/bin/env python3
"""Build a compact, web-ready index from the public Ceder synthesis datasets."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import re
import base64
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT.parent / "ceder_raw"
OUT = ROOT / "data" / "database" / "ceder_methods.csv.gz"
INDEX_OUT = ROOT / "data" / "database" / "ceder_index.csv.gz"
INDEX_FIELDS = [
    "method_id", "source_dataset", "doi", "mp_id", "formula", "elements",
    "n_elements", "target_material", "morphology", "morphology_confidence",
    "route", "precursor", "solvent", "temperature_C", "time_h", "atmosphere",
    "cost_AUD_per_g", "cost_confidence", "cost_breakdown", "cost_source",
    "cost_price_date",
]

MORPHOLOGIES = [
    ("nanoflower", r"\bnano[- ]?flowers?\b"),
    ("nanorod", r"\bnano[- ]?rods?\b"),
    ("nanowire", r"\bnano[- ]?wires?\b"),
    ("nanotube", r"\bnano[- ]?tubes?\b"),
    ("nanosheet", r"\bnano[- ]?(?:sheets?|plates?)\b"),
    ("nanocube", r"\bnano[- ]?cubes?\b"),
    ("nanoparticle", r"\bnano[- ]?particles?\b|\bnanospheres?\b"),
    ("microsphere", r"\bmicro[- ]?spheres?\b"),
    ("thin film", r"\bthin films?\b|\bfilms?\b"),
    ("powder", r"\bpowders?\b"),
    ("single crystal", r"\bsingle crystals?\b"),
    ("porous", r"\b(?:meso|micro|macro)?porous\b"),
]

VALID_ELEMENTS = set("""
H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn
Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La
Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po
At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg
Cn Nh Fl Mc Lv Ts Og
""".split())

FIELDS = [
    "method_id", "source_dataset", "source_index", "doi", "mp_id", "formula",
    "elements", "n_elements", "target_material", "morphology",
    "morphology_confidence", "route", "precursor", "precursors", "solvent",
    "temperature_C", "time_h", "atmosphere", "reaction_string", "procedure",
    "cost_AUD_per_g", "cost_confidence", "cost_breakdown", "cost_source",
    "cost_price_date",
]

ATOMIC_WEIGHTS = {
    "H": 1.008, "B": 10.81, "C": 12.011, "N": 14.007, "O": 15.999,
    "F": 18.998, "P": 30.974, "S": 32.06, "Cl": 35.45, "Br": 79.904,
    "I": 126.904, "Fe": 55.845, "Co": 58.933, "Ni": 58.6934,
    "Cu": 63.546, "Zn": 65.38, "Ag": 107.8682,
}
PRICED_METALS = {"Ag", "Co", "Cu", "Fe", "Ni", "Zn"}
NONMETALS = {"H", "B", "C", "N", "O", "F", "Si", "P", "S", "Cl", "Se", "Br", "I"}


def load_prices() -> dict[str, dict]:
    with (ROOT / "data" / "database" / "precursor_prices.csv").open(encoding="utf-8", newline="") as handle:
        return {row["formula"]: row for row in csv.DictReader(handle)}


PRICES = load_prices()


def text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(text(v) for v in value if text(v))
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value).strip()


def paragraph(record: dict) -> str:
    value = record.get("paragraph_string")
    if isinstance(value, list):
        value = " ".join(text(v) for v in value)
    return re.sub(r"\s+", " ", text(value)).strip()


def target_elements(target: dict) -> list[str]:
    found = set()
    for comp in target.get("composition") or []:
        found.update((comp.get("elements") or {}).keys())
    return sorted(found & VALID_ELEMENTS)


def composition_summary(material: dict) -> Optional[tuple[float, dict[str, float]]]:
    total_mass = 0.0
    totals: dict[str, float] = {}
    try:
        for component in material.get("composition") or []:
            amount = float(component.get("amount", 1))
            for element, count_text in (component.get("elements") or {}).items():
                count = amount * float(count_text)
                if element not in ATOMIC_WEIGHTS:
                    return None
                totals[element] = totals.get(element, 0.0) + count
                total_mass += count * ATOMIC_WEIGHTS[element]
    except (TypeError, ValueError):
        return None
    return (total_mass, totals) if total_mass > 0 else None


def theoretical_cost(target: dict, precursors: list[dict]) -> tuple[str, str, str, str, str]:
    target_summary = composition_summary(target)
    if not target_summary:
        return "", "Price or stoichiometry unavailable", "", "", ""
    target_mass, target_counts = target_summary
    target_metals = set(target_counts) - NONMETALS
    if not target_metals or not target_metals.issubset(PRICED_METALS):
        return "", "Price or stoichiometry unavailable", "", "", ""

    candidates: dict[str, list[tuple[dict, dict, float, dict[str, float]]]] = {
        metal: [] for metal in target_metals
    }
    carrier_counts = {metal: 0 for metal in target_metals}
    for precursor in precursors:
        precursor_elements = {
            element
            for component in precursor.get("composition") or []
            for element in (component.get("elements") or {})
        }
        for metal in precursor_elements & target_metals:
            carrier_counts[metal] += 1
        formula = text(precursor.get("material_formula"))
        price = PRICES.get(formula)
        summary = composition_summary(precursor)
        if not price or not summary:
            continue
        precursor_mass, precursor_counts = summary
        carried_metals = set(precursor_counts) & target_metals
        if len(carried_metals) == 1:
            metal = next(iter(carried_metals))
            candidates[metal].append((precursor, price, precursor_mass, precursor_counts))

    if any(carrier_counts[metal] != 1 or len(candidates[metal]) != 1 for metal in target_metals):
        return "", "Price or stoichiometry unavailable", "", "", ""

    total_cost = 0.0
    details = []
    source_urls = []
    dates = []
    for metal in sorted(target_metals):
        precursor, price, precursor_mass, precursor_counts = candidates[metal][0]
        mole_ratio = target_counts[metal] / precursor_counts[metal]
        grams_per_g_target = mole_ratio * precursor_mass / target_mass
        line_cost = grams_per_g_target * float(price["price_AUD_per_g"])
        total_cost += line_cost
        details.append(
            f"{text(precursor.get('material_formula'))}: {grams_per_g_target:.4g} g × "
            f"A${float(price['price_AUD_per_g']):.4g}/g"
        )
        source_urls.append(price["source_url"])
        dates.append(price["price_checked_date"])
    return (
        f"{total_cost:.6f}",
        "Stoichiometric cation balance + vendor price",
        "; ".join(details),
        ";".join(dict.fromkeys(source_urls)),
        max(dates),
    )


def condition_values(value) -> list[tuple[float, str]]:
    values = []
    if value is None:
        return values
    if not isinstance(value, list):
        value = [value]
    for item in value:
        if isinstance(item, dict):
            unit = text(item.get("units") or item.get("unit"))
            candidates = [item.get("value"), item.get("max_value"), item.get("min_value")]
        else:
            unit, candidates = "", [item]
        for candidate in candidates:
            try:
                values.append((float(candidate), unit))
                break
            except (TypeError, ValueError):
                continue
    return values


def summarize_conditions(operations: list[dict]) -> tuple[str, str, str, str, str]:
    temperatures, times, atmospheres, media, steps = [], [], [], [], []
    for op in operations or []:
        phrase = text(op.get("string"))
        if phrase:
            steps.append(phrase)
        conditions = op.get("conditions") or {}
        temperatures.extend(condition_values(conditions.get("temperature") or conditions.get("heating_temperature")))
        times.extend(condition_values(conditions.get("time") or conditions.get("heating_time")))
        atmospheres.extend(text(v) for v in (conditions.get("atmosphere") or []) if text(v))
        media.extend(text(v) for v in (conditions.get("mixing_media") or []) if text(v))

    temp_c = []
    for value, unit in temperatures:
        unit_l = unit.lower()
        if "k" == unit_l or "kelvin" in unit_l:
            value -= 273.15
        elif "f" in unit_l and "°" in unit_l:
            value = (value - 32) * 5 / 9
        temp_c.append(value)

    time_h = []
    for value, unit in times:
        unit_l = unit.lower()
        if "min" in unit_l:
            value /= 60
        elif "sec" in unit_l or unit_l == "s":
            value /= 3600
        elif "day" in unit_l or unit_l == "d":
            value *= 24
        time_h.append(value)

    return (
        f"{max(temp_c):g}" if temp_c else "",
        f"{max(time_h):g}" if time_h else "",
        "; ".join(dict.fromkeys(atmospheres)),
        "; ".join(dict.fromkeys(media)),
        "; ".join(steps),
    )


def morphology(record: dict) -> tuple[str, str]:
    target = record.get("target") or {}
    material = text(target.get("material_string"))
    corpus = f"{material} {paragraph(record)}".lower()
    for label, pattern in MORPHOLOGIES:
        if re.search(pattern, corpus, flags=re.I):
            return label, "explicit text mention"
    return "Unspecified", "not reported in extracted text"


def convert(dataset: str, index: int, record: dict) -> dict:
    target = record.get("target") or {}
    formula = text(target.get("material_formula") or record.get("targets_string"))
    elements = target_elements(target)
    precursors = record.get("precursors") or []
    precursor_names = [text(p.get("material_string") or p.get("material_formula")) for p in precursors]
    precursor_names = [p for p in precursor_names if p]
    temperature, hours, atmosphere, solvent, steps = summarize_conditions(record.get("operations") or [])
    morph, morph_conf = morphology(record)
    route = "solid-state" if dataset == "Ceder solid-state" else text(record.get("type")) or "solution-based"
    cost, cost_confidence, cost_breakdown, cost_source, cost_price_date = theoretical_cost(target, precursors)
    signature = "|".join([dataset, text(record.get("doi")), formula, text(record.get("reaction_string")), route, steps])
    method_id = "ceder_" + hashlib.sha1(signature.encode()).hexdigest()[:16]
    procedure = paragraph(record) or steps
    return {
        "method_id": method_id,
        "source_dataset": dataset,
        "source_index": index,
        "doi": text(record.get("doi")),
        "mp_id": text(target.get("mp_id")),
        "formula": formula,
        "elements": ";".join(elements),
        "n_elements": len(elements),
        "target_material": text(target.get("material_string")) or formula,
        "morphology": morph,
        "morphology_confidence": morph_conf,
        "route": route,
        "precursor": "; ".join(precursor_names),
        "precursors": json.dumps([
            {"name": text(p.get("material_string")), "formula": text(p.get("material_formula")), "amount": ""}
            for p in precursors
        ], ensure_ascii=False, separators=(",", ":")),
        "solvent": solvent,
        "temperature_C": temperature,
        "time_h": hours,
        "atmosphere": atmosphere,
        "reaction_string": text(record.get("reaction_string")),
        "procedure": procedure[:4000],
        "cost_AUD_per_g": cost,
        "cost_confidence": cost_confidence,
        "cost_breakdown": cost_breakdown,
        "cost_source": cost_source,
        "cost_price_date": cost_price_date,
    }


def main() -> None:
    sources = [
        ("Ceder solid-state", RAW / "solid-state_dataset.json"),
        ("Ceder solution-based", RAW / "solution-synthesis_dataset.json"),
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    written = 0
    with gzip.open(OUT, "wt", encoding="utf-8", newline="", compresslevel=6) as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for dataset, path in sources:
            with path.open(encoding="utf-8") as source:
                records = json.load(source)
            for index, record in enumerate(records):
                row = convert(dataset, index, record)
                if not row["formula"] or row["method_id"] in seen:
                    continue
                seen.add(row["method_id"])
                writer.writerow(row)
                written += 1
    with gzip.open(OUT, "rt", encoding="utf-8", newline="") as source, gzip.open(
        INDEX_OUT, "wt", encoding="utf-8", newline="", compresslevel=9
    ) as target:
        reader = csv.DictReader(source)
        writer = csv.DictWriter(target, fieldnames=INDEX_FIELDS)
        writer.writeheader()
        for row in reader:
            writer.writerow({field: row.get(field, "") for field in INDEX_FIELDS})

    for old_part in INDEX_OUT.parent.glob("ceder_index.b64.*"):
        old_part.unlink()
    encoded = base64.b64encode(INDEX_OUT.read_bytes()).decode("ascii")
    part_size = 600_000
    for part_number, offset in enumerate(range(0, len(encoded), part_size)):
        (INDEX_OUT.parent / f"ceder_index.b64.{part_number:02d}").write_text(
            encoded[offset : offset + part_size], encoding="ascii"
        )
    print(f"Wrote {written:,} unique methods to {OUT} ({OUT.stat().st_size / 1_000_000:.1f} MB)")
    print(f"Web index: {INDEX_OUT.stat().st_size / 1_000_000:.1f} MB in {part_number + 1} text parts")


if __name__ == "__main__":
    main()
