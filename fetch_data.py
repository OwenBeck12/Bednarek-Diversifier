#!/usr/bin/env python3
"""
Stock Correlation Data Fetcher
================================
Run this script ONCE to generate data/stocks.json for the website.

Requirements:
    pip install yfinance pandas numpy lxml

Expected runtime: 20-40 minutes (5 years of data for ~900 stocks)
"""

import yfinance as yf
import pandas as pd
import numpy as np
import json
import os
import time
from datetime import datetime, timedelta


# ─────────────────────────────────────────────────────────────────────────────
#  Step 1: Get tickers
# ─────────────────────────────────────────────────────────────────────────────

def get_tickers():
    """
    Pulls the S&P 500, S&P 400, and S&P 600 constituent lists from Wikipedia.
    Returns: (sorted list of tickers, {ticker: name}, {ticker: sector})
    """
    names   = {}
    sectors = {}
    tickers = []

    sources = [
        {
            "label":      "S&P 500",
            "url":        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            "table":      0,
            "ticker_col": "Symbol",
            "name_col":   "Security",
            "sector_col": "GICS Sector",
        },
        {
            "label":      "S&P 400",
            "url":        "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
            "table":      0,
            "ticker_col": None,   # auto-detect
            "name_col":   None,
            "sector_col": None,
        },
        {
            "label":      "S&P 600",
            "url":        "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies",
            "table":      0,
            "ticker_col": None,
            "name_col":   None,
            "sector_col": None,
        },
    ]

    import requests as _requests
    _headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}

    for src in sources:
        try:
            print(f"  Fetching {src['label']} from Wikipedia...")
            from io import StringIO as _StringIO
            html = _requests.get(src["url"], headers=_headers, timeout=15).text
            tables = pd.read_html(_StringIO(html))
            df = tables[src["table"]]

            # Auto-detect column names
            def find_col(df, keywords):
                for col in df.columns:
                    if any(k in col.lower() for k in keywords):
                        return col
                return None

            tcol = src["ticker_col"] or find_col(df, ["ticker", "symbol"])
            ncol = src["name_col"]   or find_col(df, ["company", "security", "name"])
            scol = src["sector_col"] or find_col(df, ["sector"])

            if tcol is None:
                print(f"    Could not find ticker column. Columns: {list(df.columns)}")
                continue

            df[tcol] = df[tcol].astype(str).str.strip().str.replace(".", "-", regex=False)

            added = 0
            for _, row in df.iterrows():
                t = row[tcol]
                if t and t not in names:
                    tickers.append(t)
                    names[t]   = str(row[ncol]).strip()   if ncol   else t
                    sectors[t] = str(row[scol]).strip()   if scol   else "Unknown"
                    added += 1

            print(f"    Added {added} tickers  (running total: {len(tickers)})")

        except Exception as e:
            print(f"    Error fetching {src['label']}: {e}")

    # Preserve insertion order (S&P 500 first, then 400, then 600).
    # De-duplicate while keeping order so alphabetical slicing doesn't cut off T-Z.
    seen = set()
    ordered = []
    for t in tickers:
        if t not in seen:
            seen.add(t)
            ordered.append(t)
    return ordered, names, sectors


# ─────────────────────────────────────────────────────────────────────────────
#  Step 2: Download closing prices
# ─────────────────────────────────────────────────────────────────────────────

def download_prices(tickers, start_date, end_date):
    """
    Downloads adjusted closing prices for all tickers in batches of 100.
    Returns a DataFrame: rows = dates, columns = tickers.
    """
    CHUNK = 100
    frames = {}

    for i in range(0, len(tickers), CHUNK):
        chunk = tickers[i : i + CHUNK]
        pct   = min(100, (i + len(chunk)) / len(tickers) * 100)
        print(f"  [{pct:5.1f}%] Tickers {i+1}-{i+len(chunk)} of {len(tickers)}  ({len(chunk)} at a time)...")

        try:
            raw = yf.download(
                chunk,
                start=start_date,
                end=end_date,
                auto_adjust=True,
                progress=False,
                threads=True,
            )

            if raw.empty:
                continue

            # yfinance returns MultiIndex columns for multiple tickers,
            # flat columns for a single ticker.
            if len(chunk) == 1:
                if "Close" in raw.columns:
                    frames[chunk[0]] = raw["Close"]
            else:
                try:
                    close_df = raw["Close"]
                    for t in chunk:
                        if t in close_df.columns:
                            frames[t] = close_df[t]
                except Exception:
                    # Fallback for older yfinance
                    for t in chunk:
                        try:
                            frames[t] = raw.xs("Close", axis=1, level=0)[t]
                        except Exception:
                            pass

        except Exception as e:
            print(f"    Batch error: {e}")

        time.sleep(0.4)   # be polite to Yahoo's servers

    if not frames:
        return pd.DataFrame()

    return pd.DataFrame(frames)


# ─────────────────────────────────────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print()
    print("=" * 62)
    print("  PortfolioCorr - Stock Correlation Data Fetcher")
    print("=" * 62)
    print()

    # ── 1. Tickers ──────────────────────────────────────────────────────────
    print("STEP 1 - Fetching ticker lists from Wikipedia")
    all_tickers, names, sectors = get_tickers()
    # Keep ALL S&P 500 + S&P 400 (~903 stocks), then fill up to 1,000 from S&P 600.
    # Do NOT use alphabetical slicing — that wrongly cuts off T-Z stocks like TSLA, XOM, ORCL.
    tickers = all_tickers[:1000]
    print(f"  Using {len(tickers)} tickers\n")

    # ── 2. Prices ───────────────────────────────────────────────────────────
    end_dt    = datetime.now()
    start_dt  = end_dt - timedelta(days=5 * 365 + 30)
    end_str   = end_dt.strftime("%Y-%m-%d")
    start_str = start_dt.strftime("%Y-%m-%d")

    CACHE = "data/prices_cache.pkl"
    print(f"STEP 2 - Downloading 5 years of closing prices")

    if os.path.exists(CACHE):
        print(f"  Loading cached prices from {CACHE}...")
        cached = pd.read_pickle(CACHE)
        cached_set = set(cached.columns)
        missing = [t for t in tickers if t not in cached_set]

        if missing:
            print(f"  Cache missing {len(missing)} tickers (e.g. {missing[:5]}) — downloading now...")
            extra = download_prices(missing, start_str, end_str)
            if not extra.empty:
                prices = pd.concat([cached, extra], axis=1)
            else:
                prices = cached
            prices.to_pickle(CACHE)
            print(f"  Cache updated: {prices.shape[1]} tickers total")
        else:
            prices = cached
            print(f"  Loaded: {prices.shape[1]} tickers x {prices.shape[0]} days")
        print()
    else:
        print(f"  Period: {start_str}  ->  {end_str}")
        prices = download_prices(tickers, start_str, end_str)

        if prices.empty:
            print("\nERROR: No price data returned. Check internet connection.")
            return

        print(f"\n  Raw shape: {prices.shape[1]} tickers x {prices.shape[0]} trading days")
        prices.to_pickle(CACHE)
        print(f"  Saved price cache to {CACHE}\n")

    # ── 3. Clean ────────────────────────────────────────────────────────────
    print("STEP 3 - Cleaning data")
    min_days = int(0.75 * prices.shape[0])
    prices = prices.dropna(thresh=min_days, axis=1)
    prices = prices.ffill().dropna()
    print(f"  After cleaning: {prices.shape[1]} tickers x {prices.shape[0]} days\n")

    # ── 3b. Rank by market cap, keep top 1,000 ──────────────────────────────
    MCAP_CACHE = "data/marketcap_cache.json"
    all_clean = list(prices.columns)

    if os.path.exists(MCAP_CACHE):
        with open(MCAP_CACHE) as f:
            mcaps = json.load(f)
        missing_mc = [t for t in all_clean if t not in mcaps]
    else:
        mcaps = {}
        missing_mc = all_clean

    if missing_mc:
        print(f"STEP 3b - Fetching market caps for {len(missing_mc)} stocks (this takes ~2 min)...")
        for i, t in enumerate(missing_mc):
            try:
                mc = yf.Ticker(t).fast_info.market_cap
                mcaps[t] = float(mc) if mc else 0.0
            except Exception:
                mcaps[t] = 0.0
            if (i + 1) % 100 == 0:
                pct = (i + 1) / len(missing_mc) * 100
                print(f"  [{pct:5.1f}%] {i+1}/{len(missing_mc)}...")
            time.sleep(0.05)
        with open(MCAP_CACHE, "w") as f:
            json.dump(mcaps, f)
        print(f"  Market cap cache saved.\n")
    else:
        print(f"STEP 3b - Market caps loaded from cache.\n")

    ranked = sorted(all_clean, key=lambda t: mcaps.get(t, 0), reverse=True)
    top_1000 = ranked[:1000]
    prices = prices[top_1000]
    smallest_kept   = mcaps.get(top_1000[-1], 0)
    smallest_cut    = mcaps.get(ranked[1000], 0) if len(ranked) > 1000 else 0
    print(f"  Kept top 1,000 by market cap.")
    print(f"  Smallest kept:  {top_1000[-1]}  (${smallest_kept/1e9:.1f}B)")
    print(f"  Largest cut:    {ranked[1000] if len(ranked)>1000 else 'n/a'}  (${smallest_cut/1e9:.1f}B)\n")

    # ── 4. Returns & correlation ────────────────────────────────────────────
    print("STEP 4 - Computing returns and correlation matrix")
    returns = np.log(prices / prices.shift(1)).dropna()

    valid_tickers = sorted(returns.columns.tolist())
    returns = returns[valid_tickers]
    n = len(valid_tickers)

    print(f"  Computing {n}x{n} correlation matrix (this may take a moment)...")
    corr_np = np.nan_to_num(returns.corr().to_numpy(), nan=0.0)

    annual_ret = returns.mean() * 252
    annual_vol = returns.std() * np.sqrt(252)
    print(f"  Done. {n} stocks in final dataset.\n")

    # ── 5. Metadata ─────────────────────────────────────────────────────────
    print("STEP 5 - Assembling stock metadata")
    stocks = []
    for t in valid_tickers:
        stocks.append({
            "ticker":        t,
            "name":          names.get(t, t),
            "sector":        sectors.get(t, "Unknown"),
            "annual_return": round(float(annual_ret.get(t, 0.0)), 4),
            "volatility":    round(float(annual_vol.get(t, 0.0)), 4),
        })
    print(f"  {len(stocks)} stocks assembled.\n")

    # ── 6. Serialize ────────────────────────────────────────────────────────
    print("STEP 6 - Serializing to JSON")
    corr_flat = [round(float(v), 3) for v in corr_np.flatten()]

    output = {
        "generated_at": datetime.now().isoformat(),
        "period":       "5 years",
        "n":            n,
        "tickers":      valid_tickers,
        "stocks":       stocks,
        "correlations": corr_flat,     # flat row-major nxn matrix
    }

    os.makedirs("data", exist_ok=True)
    out_path = "data/stocks.json"

    with open(out_path, "w") as f:
        json.dump(output, f, separators=(",", ":"))

    size_mb = os.path.getsize(out_path) / 1024 / 1024

    print()
    print("=" * 62)
    print(f"  Done!  {n} stocks -> {out_path}  ({size_mb:.1f} MB)")
    print()
    print("  To view the website, serve this folder via HTTP:")
    print()
    print("      python -m http.server 8080")
    print()
    print("  Then open:  http://localhost:8080")
    print("=" * 62)
    print()


if __name__ == "__main__":
    main()
