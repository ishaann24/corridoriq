"""
scoring_engine.py — CorridorIQ
Deterministic, explainable scoring. No AI here — this is the "ground truth"
that the optional LLM explainer is only allowed to describe, never override.

Opportunity Score (0-100) =
    40% * business_fit        (from corridor_archetype_scores, 0-1)
  + 30% * audience_relevance  (audience_scores 1-7, normalized to 0-1)
  + 20% * activity_match      (daypart_occasion_density for chosen period, 0-100 -> 0-1)
  + 10% * anchor_bonus        (1 if 1+ relevant special zone/anchor touches corridor, scaled)
  -      supply_penalty       (only applied where place-count data exists; DFW has none)

Any archetype tiered GATED_OUT for a corridor is excluded from ranking entirely,
per the hackathon brief ("a gated-out archetype should not be presented as a
normal positive recommendation").
"""

from data_loader import DAYPART_FIELD

WEIGHTS = {"fit": 0.40, "audience": 0.30, "activity": 0.20, "anchor": 0.10}
SUPPLY_PENALTY_WEIGHT = 0.20
SUPPLY_SATURATION_COUNT = 15  # count of existing same-category places treated as "fully saturated"


def _audience_norm(score_0_to_10) -> float:
    # NOTE: the hackathon primer describes this as a 1-7 scale, but the actual
    # exported data uses 0-10 (verified against both real files). Trust the data.
    return max(0.0, min(1.0, score_0_to_10 / 10))


def _activity_norm(daypart: dict, period: str) -> float:
    field = DAYPART_FIELD.get(period)
    val = daypart.get(field, 0) if field else 0
    return max(0.0, min(1.0, val / 100))


def _anchor_bonus(zones: list) -> float:
    if not zones:
        return 0.0
    return min(len(zones) / 3, 1.0)


def _supply_penalty(place_counts, category_id: str):
    """Returns (penalty_0_to_1, note_string). Only meaningful where place data exists."""
    if place_counts is None:
        return 0.0, "no_place_data"
    count = place_counts.get(category_id, 0)
    penalty = min(count / SUPPLY_SATURATION_COUNT, 1.0)
    return penalty, f"{count}_existing"


def score_corridor(dataset: dict, corridor_id: str, archetype_id: str, audience_segment_id: str, period: str):
    """Returns a full evidence dict for one corridor, or None if gated out / no fit data."""
    corridor = dataset["corridors"][corridor_id]
    fit = dataset["fit_scores"].get((corridor_id, archetype_id))
    if fit is None:
        return None
    if fit["tier"] == "GATED_OUT":
        return None

    audience_raw = corridor["audience_scores"].get(audience_segment_id)
    if audience_raw is None:
        return None

    zones = dataset["zones_by_corridor"].get(corridor_id, [])
    supply_penalty, supply_note = _supply_penalty(corridor["place_counts"], fit["category_id"])

    fit_norm = fit["score"]
    audience_norm = _audience_norm(audience_raw)
    activity_norm = _activity_norm(corridor["daypart"], period)
    anchor_norm = _anchor_bonus(zones)

    raw_score = (
        WEIGHTS["fit"] * fit_norm
        + WEIGHTS["audience"] * audience_norm
        + WEIGHTS["activity"] * activity_norm
        + WEIGHTS["anchor"] * anchor_norm
        - SUPPLY_PENALTY_WEIGHT * supply_penalty
    )
    opportunity_score = round(max(0.0, min(1.0, raw_score)) * 100, 1)

    strengths, concerns = [], []
    if fit["tier"] == "STRONG_FIT":
        strengths.append(f"Strong fit score for this business format ({fit['score']:.2f}).")
    elif fit["tier"] == "WEAK_FIT":
        concerns.append(f"Fit score for this business format is weak ({fit['score']:.2f}).")
    elif fit["tier"] == "INSUFFICIENT_CONTEXT":
        concerns.append("Dataset has insufficient context to confidently score this format here.")

    if audience_raw >= 7:
        strengths.append(f"High relevance for the selected audience (score {audience_raw}/10).")
    elif audience_raw <= 4:
        concerns.append(f"Audience relevance is low for this corridor (score {audience_raw}/10).")

    if activity_norm >= 0.6:
        strengths.append(f"Strong {period} activity signal ({int(activity_norm*100)}/100).")
    elif activity_norm <= 0.3:
        concerns.append(f"Activity during {period} is relatively low ({int(activity_norm*100)}/100).")

    if zones:
        strengths.append(f"{len(zones)} relevant anchor(s)/special zone(s) nearby: " +
                          ", ".join(z["name"] for z in zones[:3]) + ("..." if len(zones) > 3 else ""))
    else:
        concerns.append("No special-zone anchor data linked to this corridor in the dataset.")

    if supply_note == "no_place_data":
        concerns.append("Dataset does not include sampled place counts for this metro — existing supply is unknown.")
    else:
        count = supply_note.split("_")[0]
        if supply_penalty >= 0.5:
            concerns.append(f"The dataset shows {count} existing similar businesses, which may indicate stronger competition.")
        else:
            strengths.append(f"The dataset shows limited sampled supply of similar businesses ({count}).")

    return {
        "corridor_id": corridor_id,
        "corridor_name": corridor["name"],
        "metro_id": corridor["metro_id"],
        "district": corridor["district"],
        "character": corridor["character"],
        "business_archetype": fit["name"],
        "fit_score": round(fit["score"], 3),
        "fit_tier": fit["tier"],
        "audience_score_raw": audience_raw,
        "activity_score": round(activity_norm * 100),
        "anchors": zones,
        "supply_note": supply_note,
        "opportunity_score": opportunity_score,
        "strengths": strengths,
        "concerns": concerns,
    }


def rank_corridors(dataset: dict, metro_id: str, archetype_id: str, audience_segment_id: str, period: str, top_k: int = 5):
    results = []
    for cid, c in dataset["corridors"].items():
        if c["metro_id"] != metro_id:
            continue
        evidence = score_corridor(dataset, cid, archetype_id, audience_segment_id, period)
        if evidence:
            results.append(evidence)
    results.sort(key=lambda r: r["opportunity_score"], reverse=True)
    return results[:top_k]


def get_corridor_summary(dataset: dict, corridor_id: str, archetype_id: str, audience_segment_id: str, period: str):
    return score_corridor(dataset, corridor_id, archetype_id, audience_segment_id, period)


if __name__ == "__main__":
    from data_loader import load_all
    dataset = load_all()

    # demo: café for morning commuters, NYC
    cafe_id = "us.cafe.neighborhood_seated.v1"
    top = rank_corridors(dataset, "nyc", cafe_id, "morning_commuters", "morning", top_k=5)
    print(f"Top NYC corridors for '{cafe_id}' / morning_commuters / morning:\n")
    for r in top:
        print(f"  {r['opportunity_score']:>5} | {r['corridor_name']} ({r['fit_tier']})")
        for s in r["strengths"]:
            print(f"        + {s}")
        for c in r["concerns"]:
            print(f"        - {c}")
        print()

    # demo: DFW to confirm the no-place-data path works
    top_dfw = rank_corridors(dataset, "dallas-fort-worth", cafe_id, "morning_commuters", "morning", top_k=3)
    print(f"\nTop DFW corridors for the same query:\n")
    for r in top_dfw:
        print(f"  {r['opportunity_score']:>5} | {r['corridor_name']} ({r['fit_tier']}) | supply_note={r['supply_note']}")