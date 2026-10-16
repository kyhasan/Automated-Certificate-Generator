# Quick Start Guide: Automated Netlify Deployment

This guide walks you through setting up and running automated deployments for your chess tournament certificates directly to **Netlify** with a single command.

---

## 1. Prerequisites

- Python 3.9+ installed
- Required dependencies installed:
  ```bash
  pip install -r requirements.txt
  ```
- A free or paid [Netlify](https://app.netlify.com) account

---

## 2. Step 1: Get Your Netlify Personal Access Token (One-Time Setup)

To allow the script to create and update sites on your Netlify account, generate a Personal Access Token:

1. Log in to your [Netlify Dashboard](https://app.netlify.com).
2. Click your profile avatar in the top-right corner and select **User settings**.
3. In the left navigation menu, click **Applications**.
4. Under the **Personal access tokens** section, click **New access token**.
5. Give the token a name (e.g. `Cert-Automation`) and click **Generate token**.
6. **Copy the token** immediately (it will only be shown once).

---

## 3. Step 2: Configure Your Token

You can provide your token in any of the following ways:

### Option A: `.env` File (Easiest & Recommended)

Create or open a `.env` file in the project root directory and add:

```env
NETLIFY_AUTH_TOKEN=your_personal_access_token_here
```

Both `cert_generator.py` and `netlify_deployer.py` automatically load this file with zero extra setup. (Note: `.env` is already added to `.gitignore` so your secret is never committed).

### Option B: Set Environment Variable in PowerShell

To set it permanently for your Windows user account:

```powershell
[System.Environment]::SetEnvironmentVariable('NETLIFY_AUTH_TOKEN', 'your_personal_access_token_here', 'User')
```

Or for the current terminal session only:
```powershell
$env:NETLIFY_AUTH_TOKEN="your_personal_access_token_here"
```

### Option C: Pass via Command Line Flag

You can also pass it explicitly with each run:
```bash
--netlify-token "your_personal_access_token_here"
```

---

## 4. Step 3: Generate and Deploy

### Simplest End-to-End Command (Fully Automated)

Both **Category** and **Total Rounds** are auto-detected directly from the tournament data with **zero extra network requests (0ms overhead)**!

Run `cert_generator.py` with just the URL and `--deploy`:

```powershell
python cert_generator.py `
  --url "https://s1.chess-results.com/tnr1425535.aspx?lan=1" `
  --deploy
```

**What happens automatically:**
1. Scrapes participant data from chess-results.com.
2. **Auto-detects Category** (e.g. `U10`) from the tournament title.
3. **Auto-detects Total Rounds** (e.g. `5`) from the ranking/crosstable data.
4. Generates all certificate PDFs inside `certificates/`.
5. Creates the searchable `index.html`.
6. Checks and auto-names the Netlify project:
   `4th-nca-district-level-tournament-u10` (ignores duplicate category if title already has it).
7. Packs `index.html` and `certificates/` into memory and deploys to Netlify.
8. Prints your live URL:
   `https://4th-nca-district-level-tournament-u10.netlify.app`

---

## 5. Examples for Different Categories & Naming

The naming logic preserves your exact category casing and formatting:

### Category U10
```powershell
python cert_generator.py --url "<CHESS_RESULTS_URL>" --category "U10" --rounds 5 --deploy
```
$\rightarrow$ Deploys to: `https://4th-nca-district-level-tournament-u10.netlify.app`

### Category U08 (2-digit with zero padding)
```powershell
python cert_generator.py --url "<CHESS_RESULTS_URL>" --category "U08" --rounds 5 --deploy
```
$\rightarrow$ Deploys to: `https://4th-nca-district-level-tournament-u08.netlify.app`

### Category U8 (Single digit)
```powershell
python cert_generator.py --url "<CHESS_RESULTS_URL>" --category "U8" --rounds 5 --deploy
```
$\rightarrow$ Deploys to: `https://4th-nca-district-level-tournament-u8.netlify.app`

### Category U15
```powershell
python cert_generator.py --url "<CHESS_RESULTS_URL>" --category "U15" --rounds 5 --deploy
```
$\rightarrow$ Deploys to: `https://4th-nca-district-level-tournament-u15.netlify.app`

### Custom Site Name Override
If you want to explicitly name the site rather than using the auto-derived name:

```powershell
python cert_generator.py `
  --url "<CHESS_RESULTS_URL>" `
  --category "U10" `
  --rounds 5 `
  --deploy `
  --site-name "my-custom-tournament-u10"
```

---

## 6. Standalone Deployment (Existing Certificates)

If you already have `index.html` and `certificates/` generated and only want to deploy them without re-generating certificates:

```powershell
python netlify_deployer.py --site-name "4th-nca-district-level-tournament-u10"
```

You can specify custom paths if your files are in another folder:

```powershell
python netlify_deployer.py `
  --site-name "4th-nca-district-level-tournament-u10" `
  --html "index.html" `
  --cert_dir "certificates"
```

---

## 7. Troubleshooting

| Error | Cause | Solution |
| :--- | :--- | :--- |
| `Netlify authorization failed (401)` | Missing or invalid auth token | Ensure `NETLIFY_AUTH_TOKEN` is set or pass `--netlify-token`. Verify the token in Netlify settings. |
| `Site name is already taken (422)` | Site name is taken by another Netlify user | Netlify subdomains are globally unique. Use `--site-name` to specify a unique name or check team ownership. |
| `Certificate template file not found` | Missing `cert.png` | Ensure `cert.png` is placed in the project folder or specify path with `--template`. |

