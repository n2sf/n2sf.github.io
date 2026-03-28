"""Generate NIST SP 800-53 Rev 5 mapping for N2SF controls using OpenAI API.

Downloads the NIST OSCAL catalog and uses GPT to generate
semantic mappings between 274 N2SF controls and NIST controls.

Usage:
    pip install openai

    # PowerShell
    $env:OPENAI_API_KEY = "sk-..."
    python generate_nist_mapping.py

    # cmd
    set OPENAI_API_KEY=sk-...
    python generate_nist_mapping.py

Output:
    nist_mapping.json
"""

import json
import os
import re
import time
import urllib.request
from datetime import datetime

from openai import OpenAI

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
N2SF_PATH = os.path.join(BASE_DIR, "n2sf_controls.json")
OUTPUT_PATH = os.path.join(BASE_DIR, "nist_mapping.json")
PROGRESS_PATH = os.path.join(BASE_DIR, "nist_mapping_progress.json")

NIST_CATALOG_URL = (
    "https://raw.githubusercontent.com/usnistgov/oscal-content/"
    "main/nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json"
)
NIST_CACHE_PATH = os.path.join(BASE_DIR, "nist_oscal_cache", "catalog.json")

MODEL = "gpt-5.4"
MAX_NIST_PER_CONTROL = 5


def download_nist_catalog():
    """Download and parse the NIST OSCAL catalog, with local caching."""
    if os.path.exists(NIST_CACHE_PATH):
        print("  Using cached NIST catalog...")
        with open(NIST_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    print("  Downloading NIST SP 800-53 Rev 5 catalog...")
    data = json.loads(urllib.request.urlopen(NIST_CATALOG_URL).read())
    catalog = data["catalog"]

    os.makedirs(os.path.dirname(NIST_CACHE_PATH), exist_ok=True)
    with open(NIST_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(catalog, f)

    return catalog


def extract_prose(parts, name="statement"):
    """Extract prose text from OSCAL parts by name."""
    if not parts:
        return ""
    for part in parts:
        if part.get("name") == name:
            prose = part.get("prose", "")
            for sub in part.get("parts", []):
                sub_prose = sub.get("prose", "")
                if sub_prose:
                    prose += " " + sub_prose
            return prose.strip()
    return ""


def parse_nist_catalog(catalog):
    """Parse OSCAL catalog into flat structures."""
    families = []
    controls = {}

    for group in catalog["groups"]:
        family_id = group["id"].upper()
        family_title = group["title"]
        family_controls = []

        for ctrl in group.get("controls", []):
            ctrl_id = ctrl["id"].upper().replace(".", "-")
            ctrl_title = ctrl["title"]
            ctrl_prose = extract_prose(ctrl.get("parts"))

            controls[ctrl_id] = {
                "title": ctrl_title,
                "family_id": family_id,
                "prose": ctrl_prose[:300] if ctrl_prose else "",
            }
            family_controls.append(ctrl_id)

            # Parse enhancements (sub-controls)
            for enh in ctrl.get("controls", []):
                enh_id = enh["id"].upper().replace(".", "-")
                enh_title = enh["title"]
                enh_prose = extract_prose(enh.get("parts"))

                controls[enh_id] = {
                    "title": enh_title,
                    "family_id": family_id,
                    "prose": enh_prose[:300] if enh_prose else "",
                    "parent_id": ctrl_id,
                }
                family_controls.append(enh_id)

        families.append({
            "family_id": family_id,
            "family_title": family_title,
            "control_count": len(family_controls),
        })

    return families, controls


def build_nist_reference(families, controls):
    """Build a compact reference text of NIST controls for the prompt."""
    lines = []
    for fam in families:
        fid = fam["family_id"]
        fam_ctrls = [
            (cid, c) for cid, c in controls.items()
            if c["family_id"] == fid and "parent_id" not in c
        ]
        fam_ctrls.sort(key=lambda x: x[0])

        ctrl_strs = []
        for cid, c in fam_ctrls:
            ctrl_strs.append(f"{cid}: {c['title']}")

        lines.append(f"\n## {fid} - {fam['family_title']}")
        lines.append("\n".join(ctrl_strs))

    return "\n".join(lines)


def load_n2sf_controls():
    """Load N2SF controls grouped by control group."""
    with open(N2SF_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    groups = []
    for chapter in data["chapters"]:
        for group in chapter["control_groups"]:
            controls = []
            for ctrl in group["controls"]:
                controls.append({
                    "n2sf_id": ctrl["n2sf_id"],
                    "name": ctrl["name"],
                    "description": ctrl["description"],
                    "classification": ctrl["classification"],
                })
            groups.append({
                "group_id": group["group_id"],
                "group_name": group["group_name"],
                "group_name_en": group["group_name_en"],
                "chapter_number": chapter["chapter_number"],
                "chapter_title": chapter["chapter_title"],
                "controls": controls,
            })
    return groups


def load_progress():
    """Load progress from previous interrupted run."""
    if os.path.exists(PROGRESS_PATH):
        with open(PROGRESS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"completed_groups": [], "results": []}


def save_progress(progress):
    """Save progress for resumability."""
    with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def map_control_batch(group, nist_reference, client):
    """Send a group of N2SF controls to GPT for mapping."""
    controls_text = json.dumps(group["controls"], ensure_ascii=False, indent=2)

    system = """You are a cybersecurity standards mapping expert specializing in both
Korean national security frameworks (N2SF) and NIST SP 800-53 Rev 5.

Your task: Map Korean N2SF security controls to the most relevant NIST SP 800-53 Rev 5
controls. Consider semantic meaning, security objectives, and implementation scope.

Rules:
- Map each N2SF control to 1-5 most relevant NIST base controls (not enhancements)
- Relevance: "high" = directly equivalent, "medium" = partially overlapping, "low" = loosely related
- Rationale must be in Korean, concise (1 sentence)
- Return valid JSON only, no markdown fences"""

    user = f"""Map each N2SF control below to relevant NIST SP 800-53 Rev 5 controls.

N2SF Control Group: {group['group_id']} - {group['group_name']} ({group['group_name_en']})
Chapter: {group['chapter_number']}. {group['chapter_title']}

Controls to map:
{controls_text}

NIST SP 800-53 Rev 5 Controls Reference:
{nist_reference}

Return JSON array:
[
  {{
    "n2sf_id": "N2SF-XX-Y",
    "nist_mappings": [
      {{
        "nist_id": "XX-Y",
        "relevance": "high|medium|low",
        "rationale": "Brief explanation of the mapping relationship."
      }}
    ]
  }}
]"""

    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                max_completion_tokens=8192,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.2,
            )
            choice = response.choices[0]
            if choice.message.content is None:
                reason = choice.finish_reason
                refusal = getattr(choice.message, 'refusal', None)
                raise ValueError(f"Empty response (finish_reason={reason}, refusal={refusal})")
            text = choice.message.content.strip()
            if not text:
                raise ValueError("Empty response text")
            # Strip markdown code fences if present
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            return json.loads(text)
        except (json.JSONDecodeError, Exception) as e:
            print(f"    Attempt {attempt + 1} failed: {e}")
            if attempt < 2:
                time.sleep(10)
            else:
                raise


def generate_all_mappings():
    """Orchestrate the full mapping process."""
    print("Step 1: Loading NIST catalog...")
    catalog = download_nist_catalog()
    families, nist_controls = parse_nist_catalog(catalog)
    print(f"  Parsed {len(families)} families, {len(nist_controls)} controls")

    print("\nStep 2: Building NIST reference text...")
    nist_reference = build_nist_reference(families, nist_controls)
    print(f"  Reference text: {len(nist_reference)} chars")

    print("\nStep 3: Loading N2SF controls...")
    n2sf_groups = load_n2sf_controls()
    total_controls = sum(len(g["controls"]) for g in n2sf_groups)
    print(f"  Loaded {len(n2sf_groups)} groups, {total_controls} controls")

    print(f"\nStep 4: Generating mappings via OpenAI API ({MODEL})...")
    client = OpenAI()
    progress = load_progress()

    all_mappings = progress["results"]
    completed = set(progress["completed_groups"])

    for i, group in enumerate(n2sf_groups):
        gid = group["group_id"]
        if gid in completed:
            print(f"  [{i+1}/{len(n2sf_groups)}] {gid} - {group['group_name']} (cached)")
            continue

        print(f"  [{i+1}/{len(n2sf_groups)}] {gid} - {group['group_name']} ({len(group['controls'])} controls)...")
        batch_results = map_control_batch(group, nist_reference, client)

        # Enrich results with group/chapter info
        for result in batch_results:
            ctrl = next(
                (c for c in group["controls"] if c["n2sf_id"] == result["n2sf_id"]),
                None,
            )
            if ctrl:
                result["n2sf_name"] = ctrl["name"]
                result["n2sf_group"] = gid
                result["n2sf_chapter"] = group["chapter_number"]

        all_mappings.extend(batch_results)
        completed.add(gid)

        # Save progress
        progress["completed_groups"] = list(completed)
        progress["results"] = all_mappings
        save_progress(progress)

        # Rate limiting
        if i < len(n2sf_groups) - 1:
            time.sleep(1)

    return families, nist_controls, all_mappings


def compute_statistics(all_mappings, nist_controls):
    """Compute coverage and gap statistics."""
    total_mappings = sum(len(m.get("nist_mappings", [])) for m in all_mappings)
    nist_ids_referenced = set()
    nist_families_referenced = set()

    for m in all_mappings:
        for nm in m.get("nist_mappings", []):
            nid = nm["nist_id"]
            nist_ids_referenced.add(nid)
            if nid in nist_controls:
                nist_families_referenced.add(nist_controls[nid]["family_id"])

    unmapped = [m["n2sf_id"] for m in all_mappings if not m.get("nist_mappings")]

    return {
        "total_mappings": total_mappings,
        "nist_controls_referenced": len(nist_ids_referenced),
        "nist_families_referenced": len(nist_families_referenced),
        "n2sf_unmapped": unmapped,
        "n2sf_unmapped_count": len(unmapped),
    }


def main():
    print("=" * 60)
    print("N2SF - NIST SP 800-53 Rev 5 Mapping Generator")
    print(f"Model: {MODEL}")
    print("=" * 60)

    families, nist_controls, all_mappings = generate_all_mappings()

    print(f"\nStep 5: Computing statistics...")
    stats = compute_statistics(all_mappings, nist_controls)
    print(f"  Total mappings: {stats['total_mappings']}")
    print(f"  NIST controls referenced: {stats['nist_controls_referenced']}")
    print(f"  NIST families covered: {stats['nist_families_referenced']}/20")
    if stats["n2sf_unmapped"]:
        print(f"  Unmapped N2SF controls: {stats['n2sf_unmapped_count']}")

    # Build output - include prose for display in dashboard
    nist_controls_compact = {}
    for cid, c in nist_controls.items():
        if "parent_id" not in c:  # Only base controls
            entry = {
                "title": c["title"],
                "family_id": c["family_id"],
            }
            if c.get("prose"):
                entry["prose"] = c["prose"]
            nist_controls_compact[cid] = entry

    output = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "nist_source": "NIST SP 800-53 Rev 5 (OSCAL)",
            "model": MODEL,
            "n2sf_controls_count": len(all_mappings),
            **stats,
        },
        "nist_families": families,
        "nist_controls": nist_controls_compact,
        "mappings": all_mappings,
    }

    print(f"\nStep 6: Writing {OUTPUT_PATH}...")
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Clean up progress file
    if os.path.exists(PROGRESS_PATH):
        os.remove(PROGRESS_PATH)

    file_size = os.path.getsize(OUTPUT_PATH) / 1024
    print(f"  Output size: {file_size:.1f} KB")
    print("\nDone!")


if __name__ == "__main__":
    main()
