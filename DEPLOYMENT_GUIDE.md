# Deploy Your Live Stock Scanner — Step by Step (No Coding Required)

You'll create 3 free accounts and click through a few forms. Total time: ~30–40 minutes.
At the end you'll have one URL (like `https://your-scanner.onrender.com`) that shows
your app with real NSE data.

---

## Before you start — what you're building

```
Your Browser  →  Your Render URL  →  Upstox (real NSE data)
```
One single web address hosts BOTH your app screen and the secure backend that
talks to Upstox. You never touch your API key/secret after step 2 — the server
holds them privately.

---

## STEP 1 — Open a free Upstox account

1. Go to **upstox.com** → click **Sign Up**.
2. Complete KYC (PAN, Aadhaar, bank details, a short video verification). This is
   the same process as opening any demat/trading account — takes 15–30 minutes,
   sometimes activated same day.
3. You do **not** need to fund the account or place any trade. It only needs to be
   **active** for the API to work.

*Cost: free to open. A small ~₹150/year demat maintenance charge applies after year
one, regardless of whether you trade — that's a brokerage-account fee, not an API fee.*

---

## STEP 2 — Create your free Upstox API app (get API Key + Secret)

1. Log in at **account.upstox.com**, go to **Apps** (or visit
   `account.upstox.com/developer/apps`).
2. Click **New App** (or **Create New App**).
3. Fill the form:
   - **App Name**: anything, e.g. `MyStockScanner`
   - **Redirect URL**: leave a placeholder for now, e.g. `https://example.com/api/auth/callback`
     (you'll come back and fix this exact value in Step 5, once you know your real
     Render URL — this is important, don't skip the update later)
   - **App type / Postback URL**: leave defaults / optional fields blank
4. Click **Create**. You'll now see two values:
   - **API Key** (also called Client ID)
   - **API Secret** (also called Client Secret)
5. **Copy both somewhere safe** (a notes app). You'll paste them into Render in Step 4.
   Never paste these into the app's HTML file or share them publicly.

---

## STEP 3 — Put the code on GitHub (no coding, just uploading files)

1. Go to **github.com** → **Sign up** (free).
2. Click the **+** icon (top right) → **New repository**.
3. Name it `stock-scanner-live`, keep it **Public** or **Private** (either works),
   click **Create repository**.
4. On the new empty repo page, click **uploading an existing file**.
5. Drag in these files/folders exactly as given to you:
   - `main.py`
   - `requirements.txt`
   - `.env.example` (optional, just for your reference — not required to upload)
   - the whole `static` folder (containing `index.html`)
6. Scroll down, click **Commit changes**. Done — no terminal, no git commands.

Your repo should now show `main.py`, `requirements.txt`, and a `static/` folder
containing `index.html`.

---

## STEP 4 — Deploy on Render (free tier)

1. Go to **render.com** → **Sign Up** (you can sign up directly with your GitHub
   account — this also makes connecting the repo automatic).
2. Click **New +** → **Web Service**.
3. Choose **Build and deploy from a Git repository** → connect your GitHub account
   if asked → select the `stock-scanner-live` repo.
4. Fill the settings:
   - **Name**: anything, e.g. `my-stock-scanner`
   - **Region**: closest to India if offered (e.g. Singapore)
   - **Branch**: `main`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: Free
5. Scroll to **Environment Variables** → click **Add Environment Variable** three
   times and enter:

   | Key | Value |
   |---|---|
   | `UPSTOX_API_KEY` | (paste the API Key from Step 2) |
   | `UPSTOX_API_SECRET` | (paste the API Secret from Step 2) |
   | `UPSTOX_REDIRECT_URI` | leave blank for now — you'll fill this in Step 5 |

6. Click **Create Web Service**. Render will build and deploy — takes 2–5 minutes.
   When it's done, you'll see a URL at the top like:
   `https://my-stock-scanner.onrender.com`

**This is your app's URL. Save it.**

*Cost: Render's free tier is ₹0. Trade-off: a free-tier server "sleeps" after 15
minutes of no visits and takes ~30–60 seconds to wake up on your next visit — normal
for free hosting, not a bug.*

---

## STEP 5 — Connect the Redirect URL (both places must match exactly)

Your login flow only works if Upstox and your server agree on the same address.

1. Take your Render URL from Step 4 and add `/api/auth/callback` to the end:
   ```
   https://my-stock-scanner.onrender.com/api/auth/callback
   ```
2. **In Upstox**: go back to `account.upstox.com/developer/apps` → open your app →
   edit **Redirect URL** → paste the exact address above → Save.
3. **In Render**: go to your Web Service → **Environment** tab → edit
   `UPSTOX_REDIRECT_URI` → paste the **exact same address** → Save. Render will
   automatically redeploy.

If these two don't match character-for-character (including `https://`, no trailing
slash), login will fail with a redirect-mismatch error.

---

## STEP 6 — Test it

1. Open your Render URL in a browser.
2. You'll see **"Upstox शी Login करा"** — click it.
3. You'll land on Upstox's own login page (their domain, their password field — the
   app never sees your password). Log in with your Upstox mobile number/PIN/OTP as usual.
4. You'll be redirected back to your app, and it should start loading real NSE data.
5. Check the top status bar: it should show **Live** (during market hours,
   9:15 AM–3:30 PM IST, Mon–Fri) or **Market Closed** (outside those hours) with a
   "Last Updated" timestamp.
6. Try the timeframe dropdown (5 min / 15 min / 1 hour / Daily) and the Refresh button.
7. Open a stock → check that Entry/SL/Target/score reflect real numbers, not the old
   demo pattern.

**You'll need to click "Login to Upstox" once every day** — this is an Upstox
platform limitation (every broker API works this way), not something this app can
remove without storing your password, which it deliberately does not do.

---

## Troubleshooting (Marathi messages you might see)

| Message | What it means | Fix |
|---|---|---|
| "Backend server सापडला नाही" | Render service is asleep/down or URL wrong | Wait 60s and refresh; check Render dashboard shows "Live" |
| "Upstox login आवश्यक आहे" | Token expired or first visit today | Click Login to Upstox again |
| "Upstox session संपली आहे" | 24-hour token expired mid-session | Click Login to Upstox again |
| "खूप requests झाल्या आहेत" | Hit Upstox's rate limit | Wait a minute, avoid setting auto-refresh below 30s for many stocks |
| Login redirects but shows error | Redirect URL mismatch | Recheck Step 5 — both values must be identical |
| A specific stock shows "Live data मिळाला नाही" | That symbol's request failed (temporary) | Hit Refresh; if it persists, check Render logs |

To see backend diagnostics any time, visit:
`https://your-app.onrender.com/api/admin/status` — it shows how many instrument
keys loaded and whether your API key/secret are recognized as configured.

---

## Known limitations (please read)

- **Daily login required** — by design, for security (see above).
- **Market holiday detection**: the app checks NSE's normal Monday–Friday,
  9:15–15:30 IST hours, but does not know the NSE holiday calendar. On a trading
  holiday it may still say "Live" during those hours even though the market is shut.
- **This is a single-user tool**: the access token is stored in the server's memory,
  shared by anyone who opens the URL. Fine for your personal use; don't share the
  link publicly as-is.
- **Free Render tier sleeps** when idle — first load after inactivity is slow.
- **16-stock universe**: the scanner currently tracks the same 16 large-cap stocks
  as before (RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK, SBIN, ITC, HINDUNILVR,
  BAJFINANCE, MARUTI, SUNPHARMA, TATASTEEL, LT, KOTAKBANK, ADANIENT, ASIANPAINT) +
  NIFTY 50 / BANK NIFTY. Expanding to NIFTY 100/500 is possible later — just tell me
  and I'll extend the `UNIVERSE` list in `main.py`.
- **Intraday history depth**: Upstox limits how far back 5-min/15-min candles can be
  fetched (~1 month) and 1-hour candles (~3 months) — this is an Upstox platform
  limit, already handled automatically in the backend.

---

## Cost summary

| Item | Cost |
|---|---|
| Upstox account | Free (₹150/year demat AMC after year 1) |
| Upstox API (market data, historical, WebSocket) | Free |
| GitHub | Free |
| Render free tier | Free (with sleep/wake trade-off above) |
| **Total to run this app** | **₹0/month** |

If you later want the server to never sleep, Render's paid tier starts around
$7/month — optional, not required.
