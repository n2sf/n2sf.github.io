"""Generate static N2SF security controls matrix website.

Reads n2sf_controls.json and generates a MITRE ATT&CK-style
static site into docs/ for GitHub Pages deployment.

Usage:
    python generate_site.py
"""
import json
import os
import shutil
from datetime import datetime

from jinja2 import Environment, FileSystemLoader


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, "n2sf_controls.json")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
DOCS_DIR = os.path.join(BASE_DIR, "docs")


def safe_filename(n2sf_id: str) -> str:
    """Convert N2SF ID to safe filename: N2SF-LP-4(1) -> N2SF-LP-4_1"""
    return n2sf_id.replace("(", "_").replace(")", "")


def load_data() -> dict:
    """Load the structured JSON data."""
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def build_control_lookup(data: dict) -> dict:
    """Build lookup maps for controls."""
    control_map = {}     # n2sf_id -> control dict
    group_map = {}       # n2sf_id -> group dict
    chapter_map = {}     # n2sf_id -> chapter dict
    children_map = {}    # parent_id -> [child controls]

    for chapter in data["chapters"]:
        for group in chapter["control_groups"]:
            for control in group["controls"]:
                cid = control["n2sf_id"]
                control_map[cid] = control
                group_map[cid] = group
                chapter_map[cid] = chapter

                if control.get("parent_id"):
                    pid = control["parent_id"]
                    if pid not in children_map:
                        children_map[pid] = []
                    children_map[pid].append(control)

    return control_map, group_map, chapter_map, children_map


LOGSCHEMA_DIR = os.path.join(BASE_DIR, "log_schema_mappings")


def load_logschema_mapping():
    """Load log schema mappings from per-app JSON files.

    Reads all JSON files in log_schema_mappings/ directory and merges them.

    Returns:
        logschema_apps: dict of app_code -> {name, description}
        logschema_icons: dict of n2sf_id -> [app_codes] (deduplicated)
        logschema_by_control: dict of n2sf_id -> [schema detail dicts]
    """
    if not os.path.isdir(LOGSCHEMA_DIR):
        return {}, {}, {}

    apps = {}
    all_details = {}
    all_apps_per_control = {}

    for fn in sorted(os.listdir(LOGSCHEMA_DIR)):
        if not fn.endswith(".json"):
            continue
        app_code = fn[:-5]

        with open(os.path.join(LOGSCHEMA_DIR, fn), "r", encoding="utf-8") as f:
            data = json.load(f)

        app_info = data.get("app", {})
        apps[app_code] = app_info
        schemas = data.get("schemas", {})

        for sc, controls in data.get("mappings", {}).items():
            schema_info = schemas.get(sc, {})
            for cm in controls:
                nid = cm["n2sf_id"]
                if nid not in all_details:
                    all_details[nid] = []
                    all_apps_per_control[nid] = set()
                all_apps_per_control[nid].add(app_code)
                all_details[nid].append({
                    "schema_code": sc,
                    "app_code": app_code,
                    "app_name": app_info.get("name", app_code),
                    "ko_subject": schema_info.get("ko_subject", sc),
                    "ko_summary": schema_info.get("ko_summary", ""),
                    "relevance": cm.get("relevance", ""),
                    "rationale": cm.get("rationale", ""),
                })

    logschema_icons = {
        nid: sorted(codes) for nid, codes in all_apps_per_control.items()
    }

    return apps, logschema_icons, all_details


def generate_site():
    """Main site generation function."""
    print("Loading data...")
    data = load_data()
    chapters = data["chapters"]
    metadata = data["metadata"]
    control_map, group_map, chapter_map, children_map = build_control_lookup(data)

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    site_url = "https://n2sf.logpresso.com/"

    # Load log schema mapping
    logschema_apps, logschema_icons, logschema_by_control = load_logschema_mapping()
    if logschema_apps:
        print(f"  Loaded log schema mappings: {len(logschema_by_control)} controls, {len(logschema_apps)} apps")
    else:
        print("  No log schema mapping found (logschema_mapping.json)")

    # Setup Jinja2
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=True,
    )

    # Common template context
    common_ctx = {
        "chapters": chapters,
        "metadata": metadata,
        "generated_at": generated_at,
        "children_map": children_map,
        "site_url": site_url,
    }

    # Clean and create docs directory
    if os.path.exists(DOCS_DIR):
        shutil.rmtree(DOCS_DIR)
    os.makedirs(DOCS_DIR)
    os.makedirs(os.path.join(DOCS_DIR, "groups"))
    os.makedirs(os.path.join(DOCS_DIR, "controls"))
    os.makedirs(os.path.join(DOCS_DIR, "css"))
    os.makedirs(os.path.join(DOCS_DIR, "js"))
    os.makedirs(os.path.join(DOCS_DIR, "data"))

    # Copy static assets
    shutil.copy2(
        os.path.join(STATIC_DIR, "css", "style.css"),
        os.path.join(DOCS_DIR, "css", "style.css"),
    )
    shutil.copy2(
        os.path.join(STATIC_DIR, "css", "nist_dashboard.css"),
        os.path.join(DOCS_DIR, "css", "nist_dashboard.css"),
    )
    shutil.copy2(
        os.path.join(STATIC_DIR, "js", "main.js"),
        os.path.join(DOCS_DIR, "js", "main.js"),
    )
    shutil.copy2(
        os.path.join(STATIC_DIR, "js", "nist_dashboard.js"),
        os.path.join(DOCS_DIR, "js", "nist_dashboard.js"),
    )
    shutil.copy2(
        os.path.join(STATIC_DIR, "favicon.png"),
        os.path.join(DOCS_DIR, "favicon.png"),
    )

    shutil.copy2(
        os.path.join(BASE_DIR, "og_image.png"),
        os.path.join(DOCS_DIR, "og_image.png"),
    )

    # Copy JSON data for client-side use
    shutil.copy2(DATA_PATH, os.path.join(DOCS_DIR, "data", "n2sf_controls.json"))

    # Create .nojekyll for GitHub Pages
    with open(os.path.join(DOCS_DIR, ".nojekyll"), "w") as f:
        pass

    # Generate robots.txt
    with open(os.path.join(DOCS_DIR, "robots.txt"), "w") as f:
        f.write(f"User-agent: *\nAllow: /\nSitemap: {site_url}sitemap.xml\n")

    # Collect all page paths for sitemap (generated after pages)
    sitemap_urls = []

    # ---- Generate pages ----

    # 1. Matrix main page (index.html) - no sidebar
    print("Generating matrix page...")
    tmpl = env.get_template("matrix.html")
    html = tmpl.render(
        **common_ctx,
        base_path="",
        canonical_url=site_url + "index.html",
        active_nav="matrix",
        active_group=None,
        active_chapter=None,
        active_control=None,
        no_sidebar=True,
        logschema_icons=logschema_icons,
        logschema_apps=logschema_apps,
    )
    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

    # 2. Group detail pages
    print("Generating group pages...")
    tmpl = env.get_template("group.html")
    for chapter in chapters:
        for group in chapter["control_groups"]:
            html = tmpl.render(
                **common_ctx,
                base_path="../",
                canonical_url=site_url + f"groups/{group['group_id']}.html",
                active_nav=None,
                active_group=group["group_id"],
                active_chapter=chapter["chapter_number"],
                active_control=None,
                no_sidebar=False,
                chapter=chapter,
                group=group,
            )
            path = os.path.join(
                DOCS_DIR, "groups", f"{group['group_id']}.html"
            )
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)

    # 3. Individual control pages
    print("Generating control pages...")
    tmpl = env.get_template("control.html")
    count = 0
    for chapter in chapters:
        for group in chapter["control_groups"]:
            for control in group["controls"]:
                cid = control["n2sf_id"]

                # Find parent control if exists
                parent_control = None
                if control.get("parent_id"):
                    parent_control = control_map.get(control["parent_id"])

                # Find child controls
                child_controls = children_map.get(cid, [])

                html = tmpl.render(
                    **common_ctx,
                    base_path="../",
                    canonical_url=site_url + f"controls/{safe_filename(cid)}.html",
                    active_nav=None,
                    active_group=group["group_id"],
                    active_chapter=chapter["chapter_number"],
                    active_control=cid,
                    no_sidebar=False,
                    chapter=chapter,
                    group=group,
                    control=control,
                    parent_control=parent_control,
                    child_controls=child_controls,
                    log_schemas=logschema_by_control.get(cid, []),
                )
                filename = safe_filename(cid) + ".html"
                path = os.path.join(DOCS_DIR, "controls", filename)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(html)
                count += 1

    # 4. Controls list page
    print("Generating controls list page...")
    tmpl = env.get_template("controls_list.html")

    all_controls = []
    for chapter in chapters:
        for group in chapter["control_groups"]:
            for control in group["controls"]:
                all_controls.append({
                    "control": control,
                    "group_id": group["group_id"],
                    "group_name": group["group_name"],
                    "chapter_title": chapter["chapter_title"],
                })

    html = tmpl.render(
        **common_ctx,
        base_path="../",
        canonical_url=site_url + "controls/index.html",
        active_nav="list",
        active_group=None,
        active_chapter=None,
        active_control=None,
        no_sidebar=False,
        all_controls=all_controls,
    )
    path = os.path.join(DOCS_DIR, "controls", "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    # 5. NIST Mapping Dashboard page
    nist_mapping_path = os.path.join(BASE_DIR, "nist_mapping.json")
    has_nist = os.path.exists(nist_mapping_path)
    if has_nist:
        print("Generating NIST mapping dashboard...")
        os.makedirs(os.path.join(DOCS_DIR, "nist-mapping"), exist_ok=True)
        tmpl = env.get_template("nist_dashboard.html")
        html = tmpl.render(
            **common_ctx,
            base_path="../",
            canonical_url=site_url + "nist-mapping/index.html",
            active_nav="nist",
            active_group=None,
            active_chapter=None,
            active_control=None,
            no_sidebar=True,
        )
        path = os.path.join(DOCS_DIR, "nist-mapping", "index.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)

        # Copy mapping data for client-side use
        shutil.copy2(nist_mapping_path, os.path.join(DOCS_DIR, "data", "nist_mapping.json"))
    else:
        print("Skipping NIST dashboard (nist_mapping.json not found)")

    # Copy log schema mapping data if exists
    if os.path.isdir(LOGSCHEMA_DIR):
        ls_dest = os.path.join(DOCS_DIR, "data", "log_schema_mappings")
        os.makedirs(ls_dest, exist_ok=True)
        for fn in os.listdir(LOGSCHEMA_DIR):
            if fn.endswith(".json"):
                shutil.copy2(os.path.join(LOGSCHEMA_DIR, fn), os.path.join(ls_dest, fn))

    # Generate sitemap.xml
    print("Generating sitemap...")
    sitemap_urls.append(site_url + "index.html")
    sitemap_urls.append(site_url + "controls/index.html")
    if has_nist:
        sitemap_urls.append(site_url + "nist-mapping/index.html")
    for chapter in chapters:
        for group in chapter["control_groups"]:
            sitemap_urls.append(site_url + f"groups/{group['group_id']}.html")
            for control in group["controls"]:
                sitemap_urls.append(
                    site_url + f"controls/{safe_filename(control['n2sf_id'])}.html"
                )

    today = datetime.now().strftime("%Y-%m-%d")
    sitemap_xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    sitemap_xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for url in sitemap_urls:
        sitemap_xml += f"  <url><loc>{url}</loc><lastmod>{today}</lastmod></url>\n"
    sitemap_xml += "</urlset>\n"

    with open(os.path.join(DOCS_DIR, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(sitemap_xml)

    print(f"\nDone! Generated site in docs/")
    print(f"  - 1 matrix page")
    print(f"  - {sum(len(ch['control_groups']) for ch in chapters)} group pages")
    print(f"  - {count} control pages")
    print(f"  - 1 controls list page")
    print(f"  - Total: {1 + sum(len(ch['control_groups']) for ch in chapters) + count + 1} HTML files")


if __name__ == "__main__":
    generate_site()
