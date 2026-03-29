"""Generate Logpresso log schema to N2SF control mappings using OpenAI API.

Fetches log schema info from Logpresso Store API and uses GPT to
generate semantic mappings between schemas and N2SF security controls.

Usage:
    pip install openai

    # PowerShell
    $env:OPENAI_API_KEY = "sk-..."

    # Single app
    python generate_logschema_mapping.py --app criminal-ip-asm

    # Multiple apps
    python generate_logschema_mapping.py --app criminal-ip-asm aws github

    # All apps (skips already processed)
    python generate_logschema_mapping.py --all

    # Re-process specific app (even if already done)
    python generate_logschema_mapping.py --app criminal-ip-asm --force

Output:
    logschema_mapping.json
"""

import argparse
import json
import os
import re
import time
import urllib.request
from datetime import datetime

from openai import OpenAI

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
N2SF_PATH = os.path.join(BASE_DIR, "n2sf_controls.json")
MAPPINGS_DIR = os.path.join(BASE_DIR, "log_schema_mappings")
PROGRESS_PATH = os.path.join(BASE_DIR, "logschema_mapping_progress.json")

STORE_API = "https://logpresso.store/api"
MODEL = "gpt-5.4"

# Cache for app list API call
_apps_cache = None


def fetch_json(url):
    """Fetch JSON from URL."""
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())


def fetch_all_apps():
    """Fetch all apps from Logpresso Store API (cached)."""
    global _apps_cache
    if _apps_cache is None:
        data = fetch_json(f"{STORE_API}/apps?locale=ko&limit=300")
        _apps_cache = data["apps"]
    return _apps_cache


def fetch_app_info(app_code):
    """Fetch app name, description, and tags from Logpresso Store API."""
    for app in fetch_all_apps():
        if app["app_code"] == app_code:
            return {
                "name": app["name"],
                "description": app.get("description", ""),
                "tags": app.get("tags", ""),
            }
    raise ValueError(f"App not found: {app_code}")


def fetch_schemas(app_code):
    """Fetch all log schemas for an app."""
    data = fetch_json(f"{STORE_API}/apps/{app_code}/log-schemas")
    schemas = []
    for s in data.get("log_schemas", []):
        schemas.append({
            "schema_code": s["schema_code"],
            "ko_subject": s.get("ko_subject", s.get("en_subject", "")),
        })
    return schemas


def fetch_schema_detail(app_code, schema_code):
    """Fetch detailed info for a single schema."""
    data = fetch_json(
        f"{STORE_API}/apps/{app_code}/log-schemas/{schema_code}"
    )
    s = data.get("log_schema", {})
    # Extract summary from ko_content (first line before the table)
    ko_content = s.get("ko_content") or s.get("en_content") or ""
    ko_summary = ""
    if ko_content:
        lines = ko_content.strip().split("\n")
        for line in lines:
            line = line.strip()
            if line and not line.startswith("|") and not line.startswith("-"):
                ko_summary = line
                break
    return {
        "ko_subject": s.get("ko_subject") or s.get("en_subject", ""),
        "ko_summary": ko_summary,
        "ko_content": ko_content,
    }


def load_n2sf_controls():
    """Load N2SF controls as flat list."""
    with open(N2SF_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    controls = []
    for chapter in data["chapters"]:
        for group in chapter["control_groups"]:
            for ctrl in group["controls"]:
                controls.append({
                    "n2sf_id": ctrl["n2sf_id"],
                    "name": ctrl["name"],
                    "description": ctrl["description"],
                    "group_id": group["group_id"],
                    "group_name": group["group_name"],
                    "chapter_number": chapter["chapter_number"],
                    "chapter_title": chapter["chapter_title"],
                })
    return controls


def build_n2sf_reference(controls):
    """Build compact reference text of all N2SF controls for prompt."""
    lines = []
    current_chapter = None
    current_group = None
    for c in controls:
        if c["chapter_number"] != current_chapter:
            current_chapter = c["chapter_number"]
            lines.append(f"\n## 제{c['chapter_number']}장 {c['chapter_title']}")
        if c["group_id"] != current_group:
            current_group = c["group_id"]
            lines.append(f"\n### {c['group_id']} - {c['group_name']}")
        lines.append(f"{c['n2sf_id']}: {c['name']} - {c['description'][:80]}")
    return "\n".join(lines)


def map_schema(schema_info, app_info, n2sf_reference, client):
    """Map a single log schema to relevant N2SF controls via GPT."""
    system = """You are a cybersecurity expert specializing in Korean national security
frameworks (N2SF) and security log analysis.

Your task: Given a Logpresso log schema (with field definitions) from a specific
security solution, identify which N2SF security controls can be verified, monitored,
or supported by collecting and analyzing this type of log data.

CRITICAL RULES:
- SOLUTION TYPE MATTERS: Consider what kind of security solution produces this log.
  A firewall (#NGFW/#FW) log about "system daemon" monitors the firewall device itself,
  NOT endpoint processes. A micro-segmentation (#ZTS) incident log relates to network
  segmentation, NOT code execution privileges.
- Only map controls where the log FROM THIS SPECIFIC SOLUTION TYPE can practically
  verify or monitor the control. Do not map based on keyword similarity alone.
- Return AT MOST 5 mappings per schema. Pick only the most directly relevant controls.
  If more than 5 seem relevant, choose the top 5 with highest practical relevance.
- Relevance: "high" = log directly verifies the control, "medium" = log partially
  supports verification, "low" = log provides indirect evidence
- Rationale must be in Korean, concise (1 sentence), and explain the practical
  relationship between this specific log type and the control
- If the schema is not relevant to any control, return an empty array
- Return valid JSON only, no markdown fences"""

    user = f"""Analyze this Logpresso log schema and find relevant N2SF security controls.

Security Solution:
- Product: {app_info['name']}
- Type: {app_info['tags']}
- Description: {app_info['description']}

Log Schema:
- Name: {schema_info['ko_subject']}
- Description: {schema_info['ko_summary']}
- Field definitions:
{schema_info['ko_content']}

N2SF Security Controls (274 total):
{n2sf_reference}

Remember: This log comes from a {app_info['tags']} solution ({app_info['name']}).
Only map controls that this type of solution can practically verify or monitor.

Return JSON array of mapped controls:
[
  {{
    "n2sf_id": "N2SF-XX-Y",
    "relevance": "high|medium|low",
    "rationale": "Brief Korean explanation of why this log helps verify the control"
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
                refusal = getattr(choice.message, "refusal", None)
                raise ValueError(
                    f"Empty response (finish_reason={reason}, refusal={refusal})"
                )
            text = choice.message.content.strip()
            if not text:
                raise ValueError("Empty response text")
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            return json.loads(text)
        except (json.JSONDecodeError, Exception) as e:
            print(f"    Attempt {attempt + 1} failed: {e}")
            if attempt < 2:
                time.sleep(10)
            else:
                raise


def load_progress():
    """Load progress for resumability."""
    if os.path.exists(PROGRESS_PATH):
        with open(PROGRESS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"completed_schemas": [], "results": {}}


def save_progress(progress):
    """Save progress for resumability."""
    with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def save_app_results(app_code, app_info, schema_details, schema_results):
    """Save one app's results as a per-app JSON file."""
    os.makedirs(MAPPINGS_DIR, exist_ok=True)

    # Build schemas dict (without app_code, since file is per-app)
    schemas = {}
    for sc, detail in schema_details.items():
        schemas[sc] = {
            "ko_subject": detail["ko_subject"],
            "ko_summary": detail["ko_summary"],
        }

    # Build mappings: schema_code -> [{n2sf_id, relevance, rationale}]
    mappings = {}
    total = 0
    for sc, results in schema_results.items():
        if results:
            mappings[sc] = [
                {
                    "n2sf_id": r["n2sf_id"],
                    "relevance": r["relevance"],
                    "rationale": r.get("rationale", ""),
                }
                for r in results
            ]
            total += len(results)

    per_app = {
        "app": app_info,
        "schemas": schemas,
        "mappings": mappings,
    }

    path = os.path.join(MAPPINGS_DIR, f"{app_code}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(per_app, f, ensure_ascii=False, indent=2)

    return total


def process_app(app_code, client, n2sf_reference):
    """Process a single app: fetch data, generate mappings, merge output.

    Returns number of new schema-control mappings, or -1 if no schemas.
    """
    # Fetch app info
    app_info = fetch_app_info(app_code)
    print(f"  App: {app_info['name']}")

    # Fetch schemas
    schemas = fetch_schemas(app_code)
    if not schemas:
        print(f"  No log schemas found, skipping")
        return -1
    print(f"  {len(schemas)} log schemas")

    # Fetch schema details
    schema_details = {}
    for s in schemas:
        detail = fetch_schema_detail(app_code, s["schema_code"])
        schema_details[s["schema_code"]] = detail

    # Load progress (for resuming interrupted runs)
    progress = load_progress()
    completed = set(progress["completed_schemas"])
    schema_results = progress["results"]

    # Generate mappings per schema
    new_count = 0
    for i, s in enumerate(schemas):
        sc = s["schema_code"]
        if sc in completed:
            print(f"    [{i+1}/{len(schemas)}] {sc} (cached)")
            new_count += len(schema_results.get(sc, []))
            continue

        detail = schema_details[sc]
        print(f"    [{i+1}/{len(schemas)}] {detail['ko_subject']}...")

        mappings = map_schema(detail, app_info, n2sf_reference, client)
        schema_results[sc] = mappings
        completed.add(sc)
        new_count += len(mappings)

        print(f"      -> {len(mappings)} controls mapped")

        progress["completed_schemas"] = list(completed)
        progress["results"] = schema_results
        save_progress(progress)

        time.sleep(1)

    # Save per-app output
    total = save_app_results(app_code, app_info, schema_details, schema_results)

    # Clean progress
    if os.path.exists(PROGRESS_PATH):
        os.remove(PROGRESS_PATH)

    print(f"  Done: {new_count} mappings for {app_code}")
    return new_count


def main():
    parser = argparse.ArgumentParser(
        description="Generate Logpresso log schema to N2SF control mappings"
    )
    parser.add_argument(
        "--app",
        nargs="*",
        help="One or more Logpresso Store app codes (e.g. criminal-ip-asm aws)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all apps from Logpresso Store (skips already processed)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-process apps even if already in output",
    )
    args = parser.parse_args()

    if not args.app and not args.all:
        parser.error("Specify --app APP_CODE or --all")

    print("=" * 60)
    print("Logpresso Log Schema -> N2SF Control Mapping Generator")
    print(f"Model: {MODEL}")
    print("=" * 60)

    # Determine app list
    if args.all:
        print("\nFetching all apps from Logpresso Store...")
        all_apps = fetch_all_apps()
        app_codes = [a["app_code"] for a in all_apps]
        print(f"  {len(app_codes)} apps found")
    else:
        app_codes = args.app

    # Check already processed (per-app files)
    done_apps = set()
    if os.path.isdir(MAPPINGS_DIR):
        for fn in os.listdir(MAPPINGS_DIR):
            if fn.endswith(".json"):
                done_apps.add(fn[:-5])

    if not args.force:
        to_skip = [a for a in app_codes if a in done_apps]
        app_codes = [a for a in app_codes if a not in done_apps]
        if to_skip:
            print(f"\nSkipping {len(to_skip)} already processed apps")
            if len(to_skip) <= 10:
                for a in to_skip:
                    print(f"  - {a}")

    if not app_codes:
        print("\nNo new apps to process.")
        return

    print(f"\nApps to process: {len(app_codes)}")

    # Load N2SF controls (once)
    print("\nLoading N2SF controls...")
    n2sf_controls = load_n2sf_controls()
    n2sf_reference = build_n2sf_reference(n2sf_controls)
    print(f"  {len(n2sf_controls)} controls, reference {len(n2sf_reference)} chars")

    # Initialize OpenAI client
    client = OpenAI()

    # Process each app
    processed = 0
    skipped = 0
    failed = 0

    for i, app_code in enumerate(app_codes):
        print(f"\n[{i+1}/{len(app_codes)}] {app_code}")
        try:
            result = process_app(app_code, client, n2sf_reference)
            if result >= 0:
                processed += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            failed += 1
            continue

    # Summary
    app_files = [f for f in os.listdir(MAPPINGS_DIR) if f.endswith(".json")]
    print("\n" + "=" * 60)
    print("Summary:")
    print(f"  Processed: {processed}, Skipped (no schemas): {skipped}, Failed: {failed}")
    print(f"  Total app files: {len(app_files)} in log_schema_mappings/")
    print("=" * 60)


if __name__ == "__main__":
    main()
