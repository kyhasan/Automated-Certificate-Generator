# Automated Certificate Generator

This project automates the generation of chess tournament certificates from a chess-results.com tournament page.

It scrapes the tournament ranking data, finds participant names and scores, generates QR-coded certificate PDFs, and creates a searchable HTML index page for easy download.

## Features
- Fetches participant data from a chess-results.com tournament URL
- **Auto-detects Category & Total Rounds** directly from tournament data (zero extra network calls, 0ms overhead)
- Uses a certificate template image for PDF generation
- Generates one certificate PDF per participant
- Adds a QR code linking to each player's result page
- Creates a searchable HTML index to browse/download certificates
- Supports optional manual overrides for category and round settings

## Requirements
Python 3.9+

Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

### 🚀 Graphical Web Dashboard (Recommended)

To run with a visual user interface:

- **Windows**: Double-click `run_ui.bat`
- **Or via terminal**: `python gui_server.py`

This opens a modern web dashboard in your browser (`http://localhost:5000`) where you can paste the URL, toggle deployment, customize category/rounds/site name, click **Process Certificates**, and monitor live logs in real time.

For full UI documentation and instructions on deploying this UI to Netlify, see [UI_GUIDE.md](UI_GUIDE.md) and [UI_DEPLOYMENT_PLAN.md](UI_DEPLOYMENT_PLAN.md).

---

### Command Line Usage

#### 1. Simple Usage (Category & Rounds Auto-Detected)

You only need to supply the tournament URL:

```bash
python cert_generator.py --url "https://s1.chess-results.com/tnr1425535.aspx?lan=1"
```

The script will automatically detect the category (e.g. `U10`) and total rounds (e.g. `5`) from the tournament page.

### End-to-End Generation & Netlify Deployment

To generate certificates and immediately deploy the searchable `index.html` and `certificates/` to Netlify:

```bash
python cert_generator.py --url "https://s1.chess-results.com/tnr1425535.aspx?lan=1" --deploy
```

- **Auto-detection**: Automatically detects category (`U10`) and rounds (`5`), then derives a concise page title and Netlify site name from the tournament title. Common clutter such as audience labels, extra age categories, and numeric IDs is removed (for example, `3rd NCA TN State Level Chess Tournament U08` and `3rd-nca-tn-state-level-tournament-u08`).
- **Overrides**: You can still explicitly pass `--category "U10"`, `--rounds 5`, or `--site-name <custom-name>` if desired.
- **Authentication**: Reads `NETLIFY_AUTH_TOKEN` automatically from `.env`.
- For quick step-by-step setup, see [QUICKSTART.md](QUICKSTART.md).
- For complete architecture and API specifications, see [AUTOMATED_NETLIFY_DEPLOYMENT.md](AUTOMATED_NETLIFY_DEPLOYMENT.md).

Optional speed optimization:

```bash
python cert_generator.py --url "https://s1.chess-results.com/tnr1425535.aspx?lan=1" --category "U10" --rounds 5 --no-csv
```

The `--no-csv` flag skips the intermediate CSV export when you want faster processing and do not need the extra data file.

## Files produced
- `certificates/` - generated participant PDF files
- `participants_<category>.csv` - optional intermediate participant data
- `index.html` - searchable certificate index page

## Notes
- The script expects a valid certificate template image at the path specified by `--template`.
- The script attempts to register optional custom fonts if present in the same folder.
- If specific tournament page markup changes, the HTML scraping may need adjustment.
