# Web Dashboard UI Guide

This guide explains how to use and deploy the Graphical User Interface (UI) for the **Automated Certificate Generator**.

---

## 1. Quick Start: Running the UI Locally (Recommended)

The local dashboard runs directly on your computer with **zero external dependencies** and real-time execution feedback.

### How to Launch:
1. **Option A (One-click on Windows)**:
   Double-click `run_ui.bat` in the project root directory.

2. **Option B (From terminal)**:
   ```powershell
   python gui_server.py
   ```

3. Your default web browser will automatically open to:
   ```text
   http://localhost:5000
   ```

---

## 2. Using the Dashboard

Once opened in your browser, the dashboard provides an intuitive control panel:

```text
┌─────────────────────────────────────────────────────────────┐
│             Chess Certificate Generator                     │
│      ● Local Server Mode (Zero-Config)                      │
│                                                             │
│  Tournament URL *                                           │
│  [ https://s1.chess-results.com/tnr1425535.aspx?lan=1     ] │
│                                                             │
│  Category (Auto if blank)      Total Rounds (Auto if blank) │
│  [ e.g. U10, U08, U8       ]   [ e.g. 5                   ] │
│                                                             │
│  Netlify Site Name (Optional override)                      │
│  [ e.g. 4th-nca-district-level-tournament-u10             ] │
│                                                             │
│  [✔] Deploy automatically to Netlify                        │
│                                                             │
│  [                PROCESS CERTIFICATES                    ] │
│                                                             │
│  Execution Logs                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ Scraping Chess Results...                             │  │
│  │ Auto-detected category: U10                           │  │
│  │ Auto-detected total rounds: 5                         │  │
│  │ Generated 23 certificates...                          │  │
│  │ Published to: https://4th-nca-...netlify.app          │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Form Controls:
- **Tournament URL** *(Required)*: Paste any `chess-results.com` tournament URL.
- **Category** *(Optional)*: Auto-detected from tournament data if left blank.
- **Total Rounds** *(Optional)*: Auto-detected from tournament data if left blank.
- **Netlify Site Name** *(Optional)*: Auto-formatted according to tournament title & category. Ignores duplicate category if already in the name.
- **Deploy automatically to Netlify** *(Checkbox)*: Enabled by default. Uses the `NETLIFY_AUTH_TOKEN` from your `.env` file.
- **Process Button**: Initiates the background pipeline and live streams the logs into the terminal window.
- **Live Link Card (Success)**: When deployment finishes successfully, a green banner appears displaying the live Netlify site URL (e.g. `https://4th-nca-district-level-tournament-u10.netlify.app`) along with a one-click **"Open Live Site ↗"** button.
- **Error Card (Failure)**: If deployment or processing fails, a prominent red alert card appears showing the exact error message (e.g., Netlify authentication error, subdomain already taken, or network timeout) and instructing you to inspect the log console.

---

## 3. Deploying the UI to Netlify (Cloud Mode)

The UI has **Dual-Mode support**. Netlify hosts the static frontend and a small Netlify Function securely dispatches work to GitHub Actions. The function keeps the GitHub token out of the browser; certificate generation still runs in GitHub Actions.

### Why a Cloud Runner is Used:
Netlify hosts static frontends and serverless functions, but serverless functions have a strict 10–26 second timeout. Generating dozens or hundreds of PDF certificates with ReportLab can take 30–60 seconds. Therefore, when hosted on Netlify, the web UI uses **GitHub Actions** as the free, background processing engine.

### Deploying the UI and Function

The previous drag-and-drop instructions deployed only static files and could not publish the function. Deploy the project through the Netlify CLI or connect the repository to Netlify so the function in `web/netlify/functions/` is included.

For a CLI deployment:
1. Install and authenticate the [Netlify CLI](https://docs.netlify.com/cli/get-started/).
2. Open a terminal in the `web/` directory.
3. Link the local project to your Netlify UI site with `netlify link`.
4. Deploy the site and function with `netlify deploy --prod`.

The [`web/netlify.toml`](web/netlify.toml) file sets the publish directory and function directory. If connecting the repository in Netlify instead, set the base directory to `web`; use the `dev` branch if that is where you keep the UI and function.

### Configure GitHub Credentials

In the Netlify dashboard, open the UI site's **Site configuration → Environment variables** and add the following variables. Keep them private; do not put the GitHub token in the frontend, `netlify.toml`, or a committed `.env` file.

| Variable | Value |
| --- | --- |
| `CERT_GENERATOR_GITHUB_REPOSITORY` | Repository in `owner/repo` format |
| `CERT_GENERATOR_GITHUB_TOKEN` | Fine-grained token with access to this repository and **Actions: Read and write** |
| `CERT_GENERATOR_WORKFLOW_REF` | Branch to dispatch, currently `dev` |
| `CERT_GENERATOR_UI_ACCESS_KEY` | A long, randomly generated access key for the dashboard |

Make these variables available to Netlify Functions and redeploy after changing them. The dashboard asks for the access key once per browser tab and keeps it only in that tab's `sessionStorage`; it no longer asks for or stores the GitHub token.

The workflow also needs the `NETLIFY_AUTH_TOKEN` secret in the **GitHub repository** under **Settings → Secrets and variables → Actions**. This is separate from the GitHub token above: it lets the GitHub Actions workflow deploy the generated certificate site to Netlify.

The GitHub workflow file (`.github/workflows/generate_and_deploy.yml`) must exist on the repository's default branch for manual dispatches. The dispatch itself uses the branch configured by `CERT_GENERATOR_WORKFLOW_REF`.

Treat the dashboard access key as a password: anyone who has it can trigger the workflow. Use a long random value, restrict access to the Netlify UI site where possible, and rotate the key if it is exposed.
