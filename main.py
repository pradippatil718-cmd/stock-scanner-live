"""
Stock Scanner — Live Data Backend
==================================
This server is the ONLY place that ever sees your Upstox API key/secret/access
token. The browser (frontend) never sees them — it only talks to this server.

Responsibilities:
- OAuth login with Upstox (daily access-token refresh, one click by the user)
- Fetch real NSE candles (historical + near-real-time) from Upstox
- Resolve stock symbols (RELIANCE, TCS, ...) to Upstox instrument keys
- Report NSE market status (open/closed) using IST market hours
- Return clean, Marathi-friendly error codes instead of raw API errors
- Serve the frontend app (static/index.html) so this ONE server = ONE URL
"""

import os
import io
import gzip
import json
import time
import httpx
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Query
from fastapi.responses import RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# ------------------------------------------------------------------------
# Configuration (from environment variables — set these on your hosting
# platform's "Environment" tab, never hard-code them here)
# ------------------------------------------------------------------------
UPSTOX_API_KEY = os.environ.get("UPSTOX_API_KEY", "")
UPSTOX_API_SECRET = os.environ.get("UPSTOX_API_SECRET", "")
# Must exactly match the Redirect URL you register in the Upstox developer
# console, e.g. https://your-app.onrender.com/api/auth/callback
UPSTOX_REDIRECT_URI = os.environ.get("UPSTOX_REDIRECT_URI", "http://127.0.0.1:8000/api/auth/callback")

UPSTOX_BASE = "https://api.upstox.com"
UPSTOX_AUTH_DIALOG = "https://api.upstox.com/v2/login/authorization/dialog"
UPSTOX_TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"
INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"

IST = timezone(timedelta(hours=5, minutes=30))

app = FastAPI(title="Indian Stock Scanner — Live Data Backend")

# ------------------------------------------------------------------------
# In-memory token store. Simple by design (single-user personal tool).
# Token is lost on server restart -> user just logs in again (one click).
# ------------------------------------------------------------------------
TOKEN_STORE = {"access_token": None, "obtained_at": None}

# ------------------------------------------------------------------------
# Universe of tracked stocks (edit this list to change what the scanner
# scans — kept identical to the Phase 1/2 demo universe)
# ------------------------------------------------------------------------
UNIVERSE = [
    {"sym": "RELIANCE", "name": "Reliance Industries", "sector": "ENERGY"},
    {"sym": "TCS", "name": "Tata Consultancy Services", "sector": "IT"},
    {"sym": "INFY", "name": "Infosys", "sector": "IT"},
    {"sym": "HDFCBANK", "name": "HDFC Bank", "sector": "BANKING"},
    {"sym": "ICICIBANK", "name": "ICICI Bank", "sector": "BANKING"},
    {"sym": "SBIN", "name": "State Bank of India", "sector": "BANKING"},
    {"sym": "ITC", "name": "ITC Ltd", "sector": "FMCG"},
    {"sym": "HINDUNILVR", "name": "Hindustan Unilever", "sector": "FMCG"},
    {"sym": "BAJFINANCE", "name": "Bajaj Finance", "sector": "FINANCIAL SERVICES"},
    {"sym": "MARUTI", "name": "Maruti Suzuki", "sector": "AUTO"},
    {"sym": "SUNPHARMA", "name": "Sun Pharma", "sector": "PHARMA"},
    {"sym": "TATASTEEL", "name": "Tata Steel", "sector": "METAL"},
    {"sym": "LT", "name": "Larsen & Toubro", "sector": "INFRA"},
    {"sym": "KOTAKBANK", "name": "Kotak Mahindra Bank", "sector": "BANKING"},
    {"sym": "ADANIENT", "name": "Adani Enterprises", "sector": "ENERGY"},
    {"sym": "ASIANPAINT", "name": "Asian Paints", "sector": "FMCG"},
]
INDEX_SYMBOLS = [
    {"sym": "NIFTY50", "upstox_key": "NSE_INDEX|Nifty 50", "name": "NIFTY 50"},
    {"sym": "BANKNIFTY", "upstox_key": "NSE_INDEX|Nifty Bank", "name": "BANK NIFTY"},
]

INSTRUMENT_CACHE_FILE = os.path.join(os.path.dirname(__file__), "instruments_cache.json")
SYMBOL_TO_KEY = {idx["sym"]: idx["upstox_key"] for idx in INDEX_SYMBOLS}  # indices always available
_instruments_loaded_at = None


# ------------------------------------------------------------------------
# Instrument master (maps trading symbol -> Upstox instrument_key)
# ------------------------------------------------------------------------
async def load_instrument_master(force=False):
    global _instruments_loaded_at
    if not force and os.path.exists(INSTRUMENT_CACHE_FILE):
        age = time.time() - os.path.getmtime(INSTRUMENT_CACHE_FILE)
        if age < 24 * 3600:
            with open(INSTRUMENT_CACHE_FILE) as f:
                SYMBOL_TO_KEY.update(json.load(f))
            _instruments_loaded_at = time.time()
            return True
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(INSTRUMENTS_URL, headers={
                "User-Agent": "Mozilla/5.0 (compatible; StockScannerBot/1.0)",
                "Accept": "application/json, */*",
            })
            resp.raise_for_status()
            raw = gzip.decompress(resp.content)
            data = json.loads(raw)
    except Exception as e:
        print("Instrument master download failed:", e)
        return False

    wanted = {u["sym"] for u in UNIVERSE}
    mapping = {}
    for row in data:
        if row.get("exchange") == "NSE" and row.get("instrument_type") == "EQ":
            ts = row.get("trading_symbol")
            if ts in wanted:
                mapping[ts] = row.get("instrument_key")
    for idx in INDEX_SYMBOLS:
        mapping[idx["sym"]] = idx["upstox_key"]

    SYMBOL_TO_KEY.update(mapping)
    with open(INSTRUMENT_CACHE_FILE, "w") as f:
        json.dump(mapping, f)
    _instruments_loaded_at = time.time()
    return True


@app.on_event("startup")
async def on_startup():
    await load_instrument_master()


# ------------------------------------------------------------------------
# Auth: Upstox OAuth (daily login — one click by the user)
# ------------------------------------------------------------------------
@app.get("/login")
def login():
    if not UPSTOX_API_KEY:
        return JSONResponse({"error": "config_missing",
                              "message_mr": "UPSTOX_API_KEY environment variable सेट केलेली नाही."}, status_code=500)
    url = (f"{UPSTOX_AUTH_DIALOG}?response_type=code&client_id={UPSTOX_API_KEY}"
           f"&redirect_uri={UPSTOX_REDIRECT_URI}")
    return RedirectResponse(url)


@app.get("/api/auth/callback")
async def auth_callback(code: str = Query(None), error: str = Query(None)):
    if error or not code:
        return RedirectResponse("/?auth=failed")
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            UPSTOX_TOKEN_URL,
            data={
                "code": code,
                "client_id": UPSTOX_API_KEY,
                "client_secret": UPSTOX_API_SECRET,
                "redirect_uri": UPSTOX_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        )
    if resp.status_code != 200:
        return RedirectResponse("/?auth=failed")
    payload = resp.json()
    token = payload.get("access_token")
    if not token:
        return RedirectResponse("/?auth=failed")
    TOKEN_STORE["access_token"] = token
    TOKEN_STORE["obtained_at"] = datetime.now(IST).isoformat()
    return RedirectResponse("/?auth=success")


@app.get("/api/auth/status")
def auth_status():
    return {
        "authenticated": TOKEN_STORE["access_token"] is not None,
        "obtained_at": TOKEN_STORE["obtained_at"],
    }


@app.post("/api/auth/logout")
def logout():
    TOKEN_STORE["access_token"] = None
    TOKEN_STORE["obtained_at"] = None
    return {"ok": True}


def _auth_headers():
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {TOKEN_STORE['access_token']}",
    }


# ------------------------------------------------------------------------
# Market status (IST, NSE regular equity hours: 09:15–15:30, Mon–Fri)
# NOTE: this does not know about NSE trading holidays — a holiday will
# still show as "closed by time-of-day" logic only if outside 9:15-15:30;
# on a holiday during those hours it would incorrectly show "Live". This
# is a known limitation — see the message returned by this endpoint.
# ------------------------------------------------------------------------
@app.get("/api/market/status")
def market_status():
    now = datetime.now(IST)
    is_weekday = now.weekday() < 5
    minutes = now.hour * 60 + now.minute
    open_min, close_min = 9 * 60 + 15, 15 * 60 + 30
    is_open = is_weekday and open_min <= minutes <= close_min
    return {
        "is_open": is_open,
        "label": "Live" if is_open else "Market Closed",
        "server_time_ist": now.strftime("%d-%m-%Y %H:%M:%S"),
        "note_mr": "ही तपासणी वेळेवर आधारित आहे; NSE सुट्टीचा दिवस असल्यास अचूक असेलच असे नाही."
    }


@app.get("/api/admin/status")
def admin_status():
    return {
        "instruments_loaded": len(SYMBOL_TO_KEY),
        "instruments_loaded_at": _instruments_loaded_at,
        "upstox_api_key_configured": bool(UPSTOX_API_KEY),
        "upstox_api_secret_configured": bool(UPSTOX_API_SECRET),
        "redirect_uri": UPSTOX_REDIRECT_URI,
    }


@app.get("/api/market/universe")
def universe():
    return {"stocks": UNIVERSE, "indices": INDEX_SYMBOLS}


# ------------------------------------------------------------------------
# Timeframe mapping: frontend sends a simple code, we map to Upstox V3
# historical-candle unit/interval.
# ------------------------------------------------------------------------
TIMEFRAME_MAP = {
    # code: (unit, interval, default_days_back, max_days_back)
    "5m": ("minutes", "5", 25, 29),     # Upstox: 1-15 min interval -> max ~1 month
    "15m": ("minutes", "15", 25, 29),
    "1h": ("hours", "1", 80, 89),        # Upstox: hours -> max ~1 quarter
    "1d": ("days", "1", 400, 3650),      # Upstox: days -> up to a decade
}


def _error(code, message_mr, status=502):
    return JSONResponse({"ok": False, "error_code": code, "message_mr": message_mr}, status_code=status)


@app.get("/api/market/historical/{symbol}")
async def historical(symbol: str, timeframe: str = "1d", days_back: int = 0):
    if not TOKEN_STORE["access_token"]:
        return _error("auth_required", "Upstox login आवश्यक आहे. कृपया आधी Login करा.", 401)
    if symbol not in SYMBOL_TO_KEY:
        ok = await load_instrument_master(force=True)
        if not ok or symbol not in SYMBOL_TO_KEY:
            return _error("invalid_symbol", f"{symbol} साठी instrument सापडला नाही.", 404)
    if timeframe not in TIMEFRAME_MAP:
        return _error("invalid_timeframe", "अवैध timeframe.", 400)

    unit, interval, default_days, max_days = TIMEFRAME_MAP[timeframe]
    if days_back <= 0:
        days_back = default_days
    days_back = min(days_back, max_days)

    instrument_key = SYMBOL_TO_KEY[symbol]
    to_date = datetime.now(IST).strftime("%Y-%m-%d")
    from_date = (datetime.now(IST) - timedelta(days=days_back)).strftime("%Y-%m-%d")
    url = f"{UPSTOX_BASE}/v3/historical-candle/{instrument_key}/{unit}/{interval}/{to_date}/{from_date}"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=_auth_headers())
    except httpx.TimeoutException:
        return _error("timeout", "Live market data मिळत नाही (timeout). कृपया काही वेळाने पुन्हा प्रयत्न करा.", 504)
    except httpx.RequestError:
        return _error("network_error", "Upstox शी connection होत नाही. Internet तपासा.", 502)

    if resp.status_code == 401:
        TOKEN_STORE["access_token"] = None
        return _error("auth_expired", "Upstox session संपली आहे. कृपया पुन्हा Login करा.", 401)
    if resp.status_code == 429:
        return _error("rate_limited", "खूप requests झाल्या आहेत. कृपया थोडा वेळ थांबा.", 429)
    if resp.status_code != 200:
        return _error("upstream_error", "Live market data मिळत नाही. कृपया काही वेळाने पुन्हा प्रयत्न करा.", 502)

    try:
        data = resp.json()
        candles = data.get("data", {}).get("candles", [])
    except Exception:
        return _error("bad_response", "Data समजण्यात अडचण आली.", 502)

    if not candles:
        return _error("no_data", f"{symbol} साठी candle data उपलब्ध नाही.", 404)

    # Upstox returns newest-first; we want oldest-first for indicator calc
    candles = list(reversed(candles))
    bars = [{
        "timestamp": c[0], "open": c[1], "high": c[2], "low": c[3],
        "close": c[4], "volume": c[5],
    } for c in candles]

    return {"ok": True, "symbol": symbol, "timeframe": timeframe, "bars": bars}


@app.get("/api/market/quote/{symbol}")
async def quote(symbol: str):
    if not TOKEN_STORE["access_token"]:
        return _error("auth_required", "Upstox login आवश्यक आहे.", 401)
    if symbol not in SYMBOL_TO_KEY:
        return _error("invalid_symbol", f"{symbol} सापडला नाही.", 404)
    instrument_key = SYMBOL_TO_KEY[symbol]
    url = f"{UPSTOX_BASE}/v2/market-quote/ltp?instrument_key={instrument_key}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=_auth_headers())
    except httpx.TimeoutException:
        return _error("timeout", "Live price मिळत नाही (timeout).", 504)
    except httpx.RequestError:
        return _error("network_error", "Upstox शी connection होत नाही.", 502)

    if resp.status_code == 401:
        TOKEN_STORE["access_token"] = None
        return _error("auth_expired", "Upstox session संपली आहे. कृपया पुन्हा Login करा.", 401)
    if resp.status_code != 200:
        return _error("upstream_error", "Live price मिळत नाही.", 502)

    try:
        data = resp.json()["data"]
        key = list(data.keys())[0]
        ltp = data[key]["last_price"]
    except Exception:
        return _error("bad_response", "Price data समजण्यात अडचण आली.", 502)

    return {"ok": True, "symbol": symbol, "last_price": ltp}


# ------------------------------------------------------------------------
# Serve the frontend (same origin -> no CORS headaches for a beginner)
# ------------------------------------------------------------------------
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/app", StaticFiles(directory=STATIC_DIR, html=True), name="static")


@app.get("/")
def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))
