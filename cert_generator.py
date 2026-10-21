"""
Chess Tournament Certificate & Web Page Automation Tool
Automates scraping chess-results.com data, generating customized PDF certificates with QR codes,
and generating a searchable HTML index page.
"""

import os
import sys
import re
import io
import csv
import html
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

# Ensure UTF-8 output encoding for Windows command line
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
from PIL import Image
import qrcode
from reportlab.lib.pagesizes import landscape, A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
from reportlab import rl_config
from tournament_naming import format_tournament_title

# ASCII85 wrapping uses a Python fallback here and adds substantial work to each PDF.
rl_config.useA85 = 0

# Register Fonts
FONT_NAME = "Helvetica"
try:
    if os.path.exists("LibreBaskerville-Italic.ttf"):
        pdfmetrics.registerFont(TTFont("Libre", "LibreBaskerville-Italic.ttf"))
        FONT_NAME = "Libre"
except Exception as e:
    print(f"Warning: Could not register Libre font: {e}. Using Helvetica.")

try:
    if os.path.exists("AlexBrush-Regular.ttf"):
        pdfmetrics.registerFont(TTFont("MyCursive", "AlexBrush-Regular.ttf"))
except Exception:
    pass

WIDTH, HEIGHT = landscape(A4)
FILL_COLOR = HexColor("#0d3b66")

def fetch_url(url):
    """Fetch URL with User-Agent header"""
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode('utf-8', errors='ignore')

def clean_filename(name):
    """Sanitize name for safe filesystem usage"""
    cleaned = re.sub(r'[\\/*?:"<>|]', "", name)
    cleaned = re.sub(r'\s+', " ", cleaned).strip()
    return cleaned

def fetch_tournament_pages(input_url):
    """Fetch art=1 and art=4 pages concurrently to reduce network latency."""
    parsed = urllib.parse.urlparse(input_url)
    base_path = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    q_params = dict(urllib.parse.parse_qsl(parsed.query))
    lan = q_params.get('lan', '1')
    fed = q_params.get('fed', 'IND')
    snode = q_params.get('SNode', 'S0')

    url_art1 = f"{base_path}?lan={lan}&art=1&fed={fed}&turdet=YES&SNode={snode}"
    url_art4 = f"{base_path}?lan={lan}&art=4&fed={fed}&turdet=YES&SNode={snode}"

    print(f"Fetching ranking list from: {url_art1}")
    print(f"Fetching crosstable names from: {url_art4}")

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_art1 = executor.submit(fetch_url, url_art1)
        future_art4 = executor.submit(fetch_url, url_art4)
        html_art1 = future_art1.result()
        html_art4 = future_art4.result()

    return html_art1, html_art4


def parse_tournament_data(input_url):
    """
    Extracts base URL, tournament title, total rounds, and participant list
    by fetching art=1 (ranking list with SNo) and art=4 (clean crosstable names).
    """
    parsed = urllib.parse.urlparse(input_url)
    base_path = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    
    # Extract query params
    q_params = dict(urllib.parse.parse_qsl(parsed.query))
    lan = q_params.get('lan', '1')
    fed = q_params.get('fed', 'IND')
    snode = q_params.get('SNode', 'S0')

    # Construct URLs for art=1 and art=4
    url_art1 = f"{base_path}?lan={lan}&art=1&fed={fed}&turdet=YES&SNode={snode}"
    url_art4 = f"{base_path}?lan={lan}&art=4&fed={fed}&turdet=YES&SNode={snode}"

    html_art1, html_art4 = fetch_tournament_pages(input_url)

    # Scrape tournament title
    tournament_title = "Chess Tournament"
    # First check <h2> headings which chess-results uses for the tournament heading
    h2_matches = [re.sub(r'<[^>]+>', '', h).strip() for h in re.findall(r'<h2[^>]*>(.*?)</h2>', html_art1, re.IGNORECASE | re.DOTALL)]
    if h2_matches and h2_matches[0]:
        tournament_title = h2_matches[0]
    else:
        title_match = re.search(r'<title>(.*?)</title>', html_art1, re.IGNORECASE | re.DOTALL)
        if title_match:
            t_raw = title_match.group(1).strip()
            t_raw = re.sub(r'^Chess-Results Server Chess-results\.com\s*-\s*', '', t_raw)
            tournament_title = t_raw

    # Check query params for explicit category or rounds in the URL
    url_cat = q_params.get('cat') or q_params.get('category')
    url_rd = q_params.get('rd') or q_params.get('rounds')

    # Extract detected category from URL query or tournament title / page
    detected_category = None
    if url_cat:
        detected_category = url_cat
    else:
        cat_match = re.search(r'\b(U\s*-?\s*\d{1,2}|Under\s*-?\s*\d{1,2}|Open|Girls)\b', tournament_title, re.IGNORECASE)
        if not cat_match and html_art1:
            cat_match = re.search(r'\b(U\s*-?\s*\d{1,2}|Under\s*-?\s*\d{1,2})\b', html_art1, re.IGNORECASE)
        if cat_match:
            raw_cat = cat_match.group(1).strip()
            num_match = re.search(r'\d+', raw_cat)
            if num_match:
                # Retain zero-padding if present in the raw text (e.g. U08 -> U08, U8 -> U8, Under 10 -> U10)
                detected_category = f"U{num_match.group(0)}"
            else:
                detected_category = raw_cat.capitalize()

    # Extract detected rounds from URL query, ranking heading, or crosstable headers
    detected_rounds = None
    if url_rd and url_rd.isdigit():
        detected_rounds = int(url_rd)
    else:
        rounds_match = re.search(r'after\s+(\d+)\s+Rounds?', html_art1, re.IGNORECASE)
        if rounds_match:
            detected_rounds = int(rounds_match.group(1))
        elif html_art4:
            # Fallback to checking round columns in art=4 (e.g. '1.Rd', '2.Rd')
            rd_cols = [int(x) for x in re.findall(r'(\d+)\.Rd', html_art4, re.IGNORECASE)]
            if rd_cols:
                detected_rounds = max(rd_cols)

    # Parse art=4 for clean participant names & points indexed by Rank
    # In art=4: Rank is cells[0], Name is cells[2], Points is cells[10] (or 5th from end)
    crosstable_names = {}
    table_match4 = re.search(r'<table class=[\'"]CRs1?[\'"][^>]*>(.*?)</table>', html_art4, re.DOTALL)
    if table_match4:
        rows4 = re.findall(r'<tr[^>]*>(.*?)</tr>', table_match4.group(1), re.DOTALL)
        for r in rows4:
            cells = [re.sub(r'<[^>]+>', '', c).strip() for c in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', r, re.DOTALL)]
            if cells and cells[0].isdigit():
                rk = int(cells[0])
                name = cells[2]
                crosstable_names[rk] = name

    # Parse art=1 for Rank, SNo, Points, and fallback name
    participants = []
    table_match1 = re.search(r'<table class=[\'"]CRs1?[\'"][^>]*>(.*?)</table>', html_art1, re.DOTALL)
    if not table_match1:
        raise ValueError("Could not find ranking table in chess-results page.")

    rows1 = re.findall(r'<tr[^>]*>(.*?)</tr>', table_match1.group(1), re.DOTALL)
    points_column = None
    for row in rows1:
        header_cells = [
            html.unescape(re.sub(r'<[^>]+>', '', cell)).replace('\xa0', ' ').strip()
            for cell in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.DOTALL)
        ]
        if header_cells and not header_cells[0].isdigit():
            points_column = next(
                (
                    index for index, cell in enumerate(header_cells)
                    if re.fullmatch(r'pts?\.?|points?', cell, re.IGNORECASE)
                ),
                None
            )
            if points_column is not None:
                break

    if points_column is None:
        raise ValueError("Could not identify the points column in the ranking table.")

    for r in rows1:
        cells = [
            html.unescape(re.sub(r'<[^>]+>', '', cell)).replace('\xa0', ' ').strip()
            for cell in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', r, re.DOTALL)
        ]
        if not cells or not cells[0].isdigit():
            continue

        rk = int(cells[0])
        sno = cells[1]
        raw_name = cells[3] if len(cells) > 3 and cells[2] == '' else cells[2]
        raw_name = raw_name.rstrip(',')

        # Use clean name from art=4 if available, otherwise raw_name
        name = crosstable_names.get(rk, raw_name)

        if points_column >= len(cells):
            raise ValueError(f"Ranking row {rk} does not contain the identified points column.")
        pts_raw = cells[points_column]
        pts = pts_raw.replace(',', '.')

        # Player URL for QR Code
        player_url = f"{base_path}?lan={lan}&art=9&fed={fed}&snr={sno}&SNode={snode}"

        participants.append({
            "rank": str(rk),
            "sno": str(sno),
            "name": name,
            "points": pts,
            "url": player_url
        })

    return {
        "tournament_title": tournament_title,
        "detected_category": detected_category,
        "detected_rounds": detected_rounds,
        "participants": participants
    }

def generate_single_certificate(p, category, total_rounds, template_file, output_dir):
    """Generate a single participant certificate PDF using in-memory QR code"""
    rank = p["rank"]
    name = p["name"]
    points = p["points"]
    url = p["url"]

    safe_name = clean_filename(name)
    pdf_filename = f"{safe_name}.pdf"
    pdf_path = os.path.join(output_dir, pdf_filename)

    # In-memory QR code generation
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=1,
    )
    qr.add_data(url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    
    qr_buffer = io.BytesIO()
    qr_img.save(qr_buffer, format="PNG")
    qr_buffer.seek(0)
    qr_reader = ImageReader(qr_buffer)

    # Create ReportLab canvas
    c = canvas.Canvas(pdf_path, pagesize=landscape(A4))
    
    # Draw background template
    c.drawImage(ImageReader(template_file), 0, 0, width=WIDTH, height=HEIGHT)
    c.setFillColor(FILL_COLOR)

    # Add participant name (with dynamic font sizing for long names)
    font_size = 20
    name_width = c.stringWidth(name, FONT_NAME, font_size)
    max_name_width = 320
    if name_width > max_name_width:
        font_size = max(12, int(font_size * (max_name_width / name_width)))
    c.setFont(FONT_NAME, font_size)
    c.drawCentredString(400, 281, name)

    # Add points
    c.setFont("Helvetica-Bold", 15)
    c.drawCentredString(417, 250, points)

    # Add total rounds
    c.setFont("Helvetica-Bold", 15)
    c.drawCentredString(507, 250, f"{total_rounds}")

    # Add rank
    c.setFont("Helvetica-Bold", 24)
    c.drawCentredString(512, 90, rank)

    # Add category
    c.drawCentredString(350, 90, category)

    # Add QR code
    c.drawImage(qr_reader, 40, HEIGHT/2 - 50, width=100, height=100)

    c.save()
    return pdf_filename

def generate_html_page(tournament_title, category, participants, output_html_file):
    """Generate modern, searchable HTML index page with highlight support"""
    display_title = html.escape(format_tournament_title(tournament_title, category))
    html_rows = []
    for p in participants:
        pdf_link = urllib.parse.quote(p["pdf_file"])
        html_rows.append(
            f"    <tr>"
            f"<td class='rank-col'>{p['rank']}</td>"
            f"<td class='name-col' data-name='{p['name']}'>{p['name']}</td>"
            f"<td class='points-col'>{p['points']}</td>"
            f"<td>{category}</td>"
            f"<td><a href='certificates/{pdf_link}' target='_blank'>Download</a></td>"
            f"</tr>"
        )

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{display_title}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
      background: #f8f9fa;
      color: #333;
      margin: 0;
      padding: 20px;
      text-align: center;
    }}
    .header-box {{
      max-width: 900px;
      margin: 0 auto 20px auto;
      background: #ffffff;
      padding: 20px;
      border-radius: 8px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }}
    h1 {{
      color: #1a202c;
      margin: 0 0 8px 0;
      font-size: 22px;
      line-height: 1.3;
    }}
    h2 {{
      color: #2b6cb0;
      margin: 0;
      font-size: 18px;
      font-weight: 600;
    }}
    #searchInput {{
      margin: 20px auto;
      padding: 10px 14px;
      font-size: 16px;
      width: 90%;
      max-width: 500px;
      border: 1.5px solid #cbd5e0;
      border-radius: 6px;
      box-sizing: border-box;
      outline: none;
      display: block;
    }}
    #searchInput:focus {{
      border-color: #3182ce;
      box-shadow: 0 0 0 3px rgba(66,153,225,0.25);
    }}
    .table-container {{
      max-width: 950px;
      margin: 0 auto;
      overflow-x: auto;
      background: white;
      border-radius: 8px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      text-align: center;
    }}
    th, td {{
      padding: 12px 14px;
      border: 1px solid #e2e8f0;
      font-size: 15px;
    }}
    th {{
      background: #f5cd72;
      color: #2d3748;
      font-weight: 700;
      position: sticky;
      top: 0;
    }}
    tr:nth-child(even) {{
      background-color: #fafbfc;
    }}
    tr:hover {{
      background-color: #edf2f7;
    }}
    a {{
      color: #007bff;
      text-decoration: none;
      font-weight: bold;
    }}
    a:hover {{
      text-decoration: underline;
    }}
    .rank-col {{ color: #d32f2f; font-weight: bold; }}
    .name-col {{ color: #1976d2; font-weight: bold; }}
    .points-col {{ color: #f57c00; font-weight: bold; }}
    .highlight {{ background-color: #fff59d; font-weight: bold; padding: 1px 3px; border-radius: 2px; }}
  </style>
</head>
<body>
  <div class="header-box">
    <h1>{display_title}</h1>
    <h2>Appreciation Certificates</h2>
  </div>

  <input type="text" id="searchInput" onkeyup="searchTable()" placeholder="Search for participant name...">

  <div class="table-container">
    <table id="certTable">
      <thead>
        <tr>
          <th>Rank</th>
          <th>Participant Name</th>
          <th>Points</th>
          <th>Category</th>
          <th>Certificate Download</th>
        </tr>
      </thead>
      <tbody>
{chr(10).join(html_rows)}
      </tbody>
    </table>
  </div>

  <script>
    function searchTable() {{
      const input = document.getElementById("searchInput");
      const filter = input.value.trim().toUpperCase();
      const table = document.getElementById("certTable");
      const rows = table.getElementsByTagName("tbody")[0].getElementsByTagName("tr");

      for (let i = 0; i < rows.length; i++) {{
        const td = rows[i].getElementsByTagName("td")[1];
        if (td) {{
          const originalName = td.getAttribute("data-name") || td.textContent;
          if (filter === "") {{
            rows[i].style.display = "";
            td.innerHTML = originalName;
          }} else if (originalName.toUpperCase().includes(filter)) {{
            rows[i].style.display = "";
            const escapedFilter = filter.replace(/[-\\^$*+?.()|[\\]{{}}]/g, '\\\\$&');
            const regex = new RegExp(`(${{escapedFilter}})`, "gi");
            td.innerHTML = originalName.replace(regex, "<span class='highlight'>$1</span>");
          }} else {{
            rows[i].style.display = "none";
          }}
        }}
      }}
    }}
  </script>
</body>
</html>"""

    with open(output_html_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"[OK] HTML page generated: {output_html_file}")

def run_automation(tournament_url, category=None, total_rounds=None, template_file="cert.png", output_dir="certificates", html_file="index.html", save_csv=False, deploy=False, site_name=None, netlify_token=None):
    """End-to-end automation pipeline"""
    if not os.path.exists(template_file):
        raise FileNotFoundError(f"Certificate template file not found: {template_file}")

    os.makedirs(output_dir, exist_ok=True)

    # Step 1: Scrape tournament data
    print(f"\n--- Scraping Chess Results from {tournament_url} ---")
    scraped_info = parse_tournament_data(tournament_url)
    participants = scraped_info["participants"]
    tournament_title = scraped_info["tournament_title"]

    # Resolve category: user argument > auto-detected > fallback
    if category is None:
        if scraped_info.get("detected_category"):
            category = scraped_info["detected_category"]
            print(f"Auto-detected category: {category}")
        else:
            category = "Open"
            print(f"Category not specified or detected, defaulting to '{category}'")
    else:
        print(f"Using specified category: {category}")

    tournament_title = format_tournament_title(tournament_title, category)

    # Resolve total rounds: user argument > auto-detected > fallback
    if total_rounds is None:
        if scraped_info.get("detected_rounds"):
            total_rounds = scraped_info["detected_rounds"]
            print(f"Auto-detected total rounds: {total_rounds}")
        else:
            total_rounds = 5
            print(f"Total rounds not specified or detected, defaulting to {total_rounds}")
    else:
        print(f"Using specified total rounds: {total_rounds}")

    print(f"Found {len(participants)} participants in {category} category.")

    # Save CSV copy for records when requested; this is optional and can be disabled for speed.
    if save_csv:
        csv_file = f"participants_{category}.csv"
        with open(csv_file, "w", newline="", encoding="utf-8-sig") as cf:
            writer = csv.writer(cf)
            writer.writerow(["Rank", "Name", "Points", "Link"])
            for p in participants:
                writer.writerow([p["rank"], p["name"], p["points"], p["url"]])
        print(f"Saved intermediate data to {csv_file}")

    # Step 2: Generate PDF certificates. Parallel generation reduces wall-clock time for large fields.
    print(f"\n--- Generating {len(participants)} Certificates in '{output_dir}/' ---")
    max_workers = min(32, max(1, len(participants)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_participant = {
            executor.submit(generate_single_certificate, p, category, total_rounds, template_file, output_dir): p
            for p in participants
        }

        for idx, future in enumerate(as_completed(future_to_participant), 1):
            participant = future_to_participant[future]
            pdf_file = future.result()
            participant["pdf_file"] = pdf_file
            print(f"  [{idx}/{len(participants)}] Generated: {pdf_file} (Rank {participant['rank']}, Pts {participant['points']})")

    # Step 3: Generate HTML index
    print(f"\n--- Generating HTML index: {html_file} ---")
    generate_html_page(tournament_title, category, participants, html_file)
    print(f"\n[DONE] Successfully generated {len(participants)} certificates and {html_file}")

    # Step 4: Optional Automated Netlify Deployment
    if deploy:
        from netlify_deployer import deploy_to_netlify, slugify_site_name, load_dotenv
        load_dotenv()
        target_input = site_name if site_name else tournament_title
        target_site = slugify_site_name(target_input, category)
        deploy_to_netlify(
            site_name=target_site,
            token=netlify_token,
            html_file=html_file,
            cert_dir=output_dir
        )

if __name__ == "__main__":
    import argparse
    from netlify_deployer import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(description="Automate chess certificates from chess-results.com")
    parser.add_argument("--url", default="https://s1.chess-results.com/tnr1425535.aspx?lan=1", help="chess-results.com tournament URL")
    parser.add_argument("--category", default=None, help="Category name (e.g. U10, U18). Auto-detected from URL/page if omitted.")
    parser.add_argument("--rounds", type=int, default=None, help="Total tournament rounds. Auto-detected from URL/page if omitted.")
    parser.add_argument("--template", default="cert.png", help="Certificate template image path")
    parser.add_argument("--output_dir", default="certificates", help="Certificates folder")
    parser.add_argument("--html", default="index.html", help="Output HTML file path")
    parser.add_argument("--no-csv", action="store_true", help="Skip writing the intermediate participants CSV")
    parser.add_argument("--deploy", action="store_true", help="Automatically deploy to Netlify once output is generated")
    parser.add_argument("--site-name", default=None, help="Explicit Netlify site name override (e.g. 4th-nca-district-level-tournament-u10)")
    parser.add_argument("--netlify-token", default=None, help="Netlify Personal Access Token (defaults to NETLIFY_AUTH_TOKEN from .env or env var)")

    args = parser.parse_args()
    run_automation(
        tournament_url=args.url,
        category=args.category,
        total_rounds=args.rounds,
        template_file=args.template,
        output_dir=args.output_dir,
        html_file=args.html,
        save_csv=not args.no_csv,
        deploy=args.deploy,
        site_name=args.site_name,
        netlify_token=args.netlify_token
    )