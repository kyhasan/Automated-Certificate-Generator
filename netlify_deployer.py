"""
Netlify Automated Deployment Module
Deploy index.html and certificates/ directly to Netlify without external dependencies.
"""

import os
import io
import sys
import json
import zipfile
import argparse
import urllib.request
import urllib.error
from tournament_naming import MAX_SITE_NAME_LENGTH, slugify_site_name

API_BASE = "https://api.netlify.com/api/v1"

def load_dotenv(env_path=".env"):
    """
    Loads key=value pairs from a .env file into os.environ.
    Searches current working directory and the directory where this script is located.
    """
    candidates = [
        env_path,
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    ]
    for p in candidates:
        if os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" in line:
                            key, val = line.split("=", 1)
                            key = key.strip()
                            val = val.strip().strip("'\"")
                            if key and (key not in os.environ or not os.environ[key]):
                                os.environ[key] = val
                return True
            except Exception as e:
                print(f"Warning: Could not read .env at {p}: {e}")
    return False

# Automatically load .env on import
load_dotenv()

def build_zip_buffer(html_file="index.html", cert_dir="certificates"):
    """
    Creates an in-memory zip archive containing index.html at root
    and the certificates directory with all PDF files.
    """
    if not os.path.exists(html_file):
        raise FileNotFoundError(f"HTML file not found: {html_file}")
    if not os.path.isdir(cert_dir):
        raise FileNotFoundError(f"Certificates directory not found: {cert_dir}")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Add index.html at the root of the archive
        zf.write(html_file, arcname="index.html")

        # 2. Add all certificate files preserving relative path certificates/filename.pdf
        cert_folder_name = os.path.basename(os.path.normpath(cert_dir))
        for root, _, files in os.walk(cert_dir):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, cert_dir)
                arcname = f"{cert_folder_name}/{rel_path}".replace("\\", "/")
                zf.write(full_path, arcname=arcname)

    zip_buffer.seek(0)
    return zip_buffer.getvalue()

def deploy_to_netlify(site_name, token=None, html_file="index.html", cert_dir="certificates", category=None):
    """
    Deploys html_file and cert_dir to Netlify.
    If category is provided, checks if site_name ends with category (adds it if missing).
    If the site exists, updates it. If not, creates it.
    """
    load_dotenv()
    if category:
        site_name = slugify_site_name(site_name, category)

    auth_token = token or os.environ.get("NETLIFY_AUTH_TOKEN")
    if not auth_token:
        raise ValueError(
            "Netlify authentication token missing! Set NETLIFY_AUTH_TOKEN in .env or as an environment variable, "
            "or pass --netlify-token."
        )

    headers_common = {
        "Authorization": f"Bearer {auth_token}",
        "User-Agent": "Automated-Certificate-Generator"
    }

    print(f"\n================ Netlify Deployment ================")
    print(f"Target Project Name : {site_name}")

    # 1. Check if site exists
    print("Checking existing Netlify sites...")
    site_id = None
    try:
        req = urllib.request.Request(f"{API_BASE}/sites?filter=all&per_page=100", headers=headers_common)
        with urllib.request.urlopen(req, timeout=30) as resp:
            sites = json.loads(resp.read().decode("utf-8"))
            for s in sites:
                if s.get("name") == site_name:
                    site_id = s.get("id")
                    print(f"-> Found existing project on Netlify (Site ID: {site_id})")
                    break
    except urllib.error.HTTPError as e:
        err = e.read().decode('utf-8', errors='ignore')
        if e.code == 401:
            raise PermissionError("Netlify authorization failed. Please check your NETLIFY_AUTH_TOKEN.")
        raise RuntimeError(f"Failed to query Netlify sites ({e.code}): {err}")

    # 2. Create site if it doesn't exist
    if not site_id:
        print(f"-> Project '{site_name}' does not exist. Creating new Netlify site...")
        payload = json.dumps({"name": site_name}).encode("utf-8")
        create_headers = {**headers_common, "Content-Type": "application/json"}
        req = urllib.request.Request(f"{API_BASE}/sites", data=payload, headers=create_headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                new_site = json.loads(resp.read().decode("utf-8"))
                site_id = new_site.get("id")
                print(f"-> Created new Netlify site successfully (Site ID: {site_id})")
        except urllib.error.HTTPError as e:
            err = e.read().decode('utf-8', errors='ignore')
            raise RuntimeError(f"Failed to create Netlify site '{site_name}' ({e.code}): {err}")

    # 3. Create ZIP archive in memory
    print(f"Packing '{html_file}' and '{cert_dir}/' into deploy archive...")
    zip_bytes = build_zip_buffer(html_file, cert_dir)
    print(f"-> Archive packaged in-memory ({len(zip_bytes) / 1024:.1f} KB)")

    # 4. Upload deploy zip
    print("Uploading archive to Netlify...")
    deploy_headers = {
        **headers_common,
        "Content-Type": "application/zip",
        "Content-Length": str(len(zip_bytes))
    }
    deploy_req = urllib.request.Request(
        f"{API_BASE}/sites/{site_id}/deploys",
        data=zip_bytes,
        headers=deploy_headers,
        method="POST"
    )

    try:
        with urllib.request.urlopen(deploy_req, timeout=120) as resp:
            deploy_data = json.loads(resp.read().decode("utf-8"))
            site_url = deploy_data.get("ssl_url") or deploy_data.get("url") or f"https://{site_name}.netlify.app"
            deploy_id = deploy_data.get("id", "N/A")
            print(f"-> Deploy ID: {deploy_id}")
            print(f"\n[DEPLOY SUCCESS] Site is LIVE at: {site_url}")
            print(f"====================================================\n")
            return site_url
    except urllib.error.HTTPError as e:
        err = e.read().decode('utf-8', errors='ignore')
        raise RuntimeError(f"Netlify deploy failed ({e.code}): {err}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Standalone Netlify deployer for generated certificates")
    parser.add_argument("--site-name", required=True, help="Netlify site name (e.g. 4th-nca-district-level-tournament-u10)")
    parser.add_argument("--category", default=None, help="Tournament category (e.g. U10). If site-name does not end with category, it will be added.")
    parser.add_argument("--html", default="index.html", help="Path to index.html")
    parser.add_argument("--cert_dir", default="certificates", help="Path to certificates folder")
    parser.add_argument("--token", default=None, help="Netlify Personal Access Token (defaults to NETLIFY_AUTH_TOKEN from .env or env var)")

    args = parser.parse_args()
    try:
        deploy_to_netlify(
            site_name=args.site_name,
            token=args.token,
            html_file=args.html,
            cert_dir=args.cert_dir,
            category=args.category
        )
    except Exception as exc:
        print(f"[ERROR] Deployment failed: {exc}", file=sys.stderr)
        sys.exit(1)
