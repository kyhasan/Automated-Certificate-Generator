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

The UI has been built with **Dual-Mode support** so that the frontend can be deployed statically on Netlify.

### Why a Cloud Runner is Used:
Netlify hosts static frontends and serverless functions, but serverless functions have a strict 10–26 second timeout. Generating dozens or hundreds of PDF certificates with ReportLab can take 30–60 seconds. Therefore, when hosted on Netlify, the web UI uses **GitHub Actions** as the free, background processing engine.

### How to Deploy the UI to Netlify:
1. Log in to your [Netlify Dashboard](https://app.netlify.com).
2. Click **Add new project** $\rightarrow$ **Deploy manually**.
3. Drag and drop the `web/` folder from this project into Netlify Drop.
4. Netlify will assign a live URL (e.g. `https://my-cert-ui.netlify.app`).

### Connecting Cloud Mode to GitHub Actions:
1. When you open your deployed Netlify UI, it automatically detects it is running in **Netlify Cloud Mode**.
2. An expandable **Cloud Settings** box will appear:
   - **GitHub Repository**: Enter `your-username/Automated-Certificate-Generator`.
   - **GitHub Token**: Enter a GitHub Personal Access Token (with `workflow` or `repo` permission).
3. In your GitHub repository settings:
   - Go to **Settings** $\rightarrow$ **Secrets and variables** $\rightarrow$ **Actions**.
   - Add a repository secret named `NETLIFY_AUTH_TOKEN` containing your Netlify Personal Access Token.
4. When you click **Process Certificates** on your Netlify UI, it dispatches the included workflow (`.github/workflows/generate_and_deploy.yml`), runs the generation pipeline on GitHub's cloud runners, and automatically publishes the certificates to your tournament Netlify site!

