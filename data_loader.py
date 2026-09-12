"""
data_loader.py — CorridorIQ
Loads NYC + DFW corridor JSON exports and flattens them into simple,
metro-agnostic Python structures the scoring engine and UI can use directly.

Real field names below were confirmed by inspecting the actual uploaded
files (NYC_CORRIDORS_full.json / DALLAS_FORT_WORTH_CORRIDORS_full.json).
Key facts baked in here:
- The 55 audience_segments are IDENTICAL across both metros (same segment_ids).
- The 31 CAFE archetypes are IDENTICAL across both metros.
- DFW additionally has 36 RESTAURANT archetypes; NYC has cafe only.
- NYC corridors have populated `places` and `anchors`. DFW corridors have
  `places = None` and `anchors = []` for every corridor — DFW has NO
  per-corridor place/anchor data. DFW anchor context must instead come
  from top-level `special_zones`, matched via `host_corridor_ids`.
- Fit scores live in the top-level `corridor_archetype_scores` array
  (not the per-corridor `cafe_archetype_matches` field, which only
  exists on NYC records) — this list is present in both files and is
  what we use so the logic is identical for both metros.
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent

FILES = {
    "nyc": "NYC_CORRIDORS.full.json",
    "dallas-fort-worth": "DALLAS_FORT_WORTH_CORRIDORS.full.json",
}

DAYPART_FIELD = {
    "morning": "weekday_am",
    "afternoon": "weekday_midday",
    "evening": "weekday_evening",
    "night": "late_night",
}


def _load_raw(metro_id: str) -> dict:
    path = DATA_DIR / FILES[metro_id]
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_all():
    """
    Returns a single dict:
    {
      "corridors": {corridor_id: corridor_dict, ...}   # both metros combined
      "archetypes": {metro_id: [archetype_dict, ...]}
      "audience_segments": [ {segment_id, label, family_id}, ... ]  # shared
      "fit_scores": {(corridor_id, archetype_id): score_dict}
      "zones_by_corridor": {corridor_id: [zone_dict, ...]}   # NYC anchors +
                                                              # DFW special_zones,
                                                              # unified shape
    }
    """
    corridors = {}
    archetypes_by_metro = {}
    fit_scores = {}
    zones_by_corridor = {}
    audience_segments = None

    for metro_id in FILES:
        raw = _load_raw(metro_id)

        # audience segments are identical across metros — just take the first
        if audience_segments is None:
            audience_segments = [
                {"segment_id": s["segment_id"], "label": s["label"], "family_id": s["family_id"]}
                for s in raw["audience_segments"]
            ]

        archetypes_by_metro[metro_id] = [
            {
                "archetype_id": a["archetype_id"],
                "category_id": a["category_id"],
                "name": a["name"],
            }
            for a in raw["archetypes"]
        ]

        for c in raw["corridors"]:
            cid = c["corridor_id"]
            places = c.get("places")
            place_counts = None
            if places and places.get("classes"):
                place_counts = {
                    cls: info.get("listing_count", 0)
                    for cls, info in places["classes"].items()
                }

            corridors[cid] = {
                "corridor_id": cid,
                "metro_id": metro_id,
                "name": c["name"],
                "district": c.get("district") or c.get("borough"),
                "character": c.get("character", ""),
                "dominant_audience": c.get("dominant_audience", []),
                "audience_scores": c.get("audience_scores", {}),
                "daypart": c.get("behavior", {}).get("daypart_occasion_density", {}),
                "whitespace": c.get("behavior", {}).get("whitespace_quality", {}),
                "place_counts": place_counts,   # None for DFW — must be handled downstream
                "anchors_raw": c.get("anchors") or [],  # populated for NYC only
                "data_quality": c.get("data_quality", {}),
            }

            # NYC anchors already live on the corridor record
            if corridors[cid]["anchors_raw"]:
                zones_by_corridor[cid] = [
                    {"name": a.get("name"), "class": a.get("class")}
                    for a in corridors[cid]["anchors_raw"]
                ]

        # fit scores: top-level corridor_archetype_scores array, present in both files
        for s in raw["corridor_archetype_scores"]:
            key = (s["corridor_id"], s["archetype_id"])
            fit_scores[key] = {
                "score": s["score"],
                "tier": s["tier"],
                "category_id": s["category_id"],
                "name": s["name"],
            }

        # DFW (and any corridor without inline anchors) gets zone context
        # from special_zones + host_corridor_ids instead
        for z in raw.get("special_zones", []):
            for cid in z.get("host_corridor_ids", []):
                zones_by_corridor.setdefault(cid, [])
                zones_by_corridor[cid].append({"name": z["name"], "class": z["zone_type"]})

    return {
        "corridors": corridors,
        "archetypes": archetypes_by_metro,
        "audience_segments": audience_segments,
        "fit_scores": fit_scores,
        "zones_by_corridor": zones_by_corridor,
    }


if __name__ == "__main__":
    data = load_all()
    print("Total corridors:", len(data["corridors"]))
    print("NYC archetypes:", len(data["archetypes"]["nyc"]))
    print("DFW archetypes:", len(data["archetypes"]["dallas-fort-worth"]))
    print("Audience segments:", len(data["audience_segments"]))
    print("Fit score pairs:", len(data["fit_scores"]))
    print("Corridors with zone context:", len(data["zones_by_corridor"]))

    # sanity: pick one NYC corridor and one DFW corridor and print a summary
    for cid, c in data["corridors"].items():
        if c["metro_id"] == "nyc":
            print("\nSample NYC corridor:", c["name"])
            print("  daypart:", c["daypart"])
            print("  place_counts present:", c["place_counts"] is not None)
            print("  zones:", data["zones_by_corridor"].get(cid))
            break

    for cid, c in data["corridors"].items():
        if c["metro_id"] == "dallas-fort-worth":
            print("\nSample DFW corridor:", c["name"])
            print("  daypart:", c["daypart"])
            print("  place_counts present:", c["place_counts"] is not None)
            print("  zones:", data["zones_by_corridor"].get(cid))
            break