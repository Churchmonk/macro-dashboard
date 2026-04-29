"""
DS MACRO JUNGLE — 실시간 데이터 수집기
======================================
EODHD API + FRED API + Scrapling 기반 크롤링으로 매크로 지표를 수집해 data.json에 저장합니다.

실행 모드:
    python fetch_data.py              # = --full (전체)
    python fetch_data.py --full
    python fetch_data.py --daily      # 일별: 시장/금리/크레딧/인플레 일별 시리즈
    python fetch_data.py --weekly     # 주간: Fed H.4.1 / Net Liquidity / RMP / 신규실업수당
    python fetch_data.py --monthly    # 월간: NFP / 실업률 / JOLTS / CPI / ISM PMI / 중국 LPR

특징:
    - 부분 모드는 자기 카테고리 키만 갱신하고 나머지는 기존 data.json 값을 보존한다.
    - 한 항목이 실패하면 그 항목의 기존 값을 유지하고 다른 항목은 계속 진행한다.
    - 스케줄러가 일/주/월 모드를 각각 호출하면 시간이 지나면서 전체 data.json이 항상 최신 상태로 유지된다.

출력:
    macro_dashboard/data.json
"""

import argparse
import json
import math
import os
import sys
import time
import re as _re
from datetime import datetime, timedelta

import requests

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API 키 / 엔드포인트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 로컬: .env.local 파일에서 자동 로드
# CI:   GitHub Secrets로 환경변수 주입
try:
    from dotenv import load_dotenv
    # 스크립트 위치 기준으로 .env.local 탐색 (작업 스케줄러가 다른 cwd에서 호출해도 OK)
    _here = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(_here, ".env.local"))
    load_dotenv(os.path.join(_here, ".env"))  # 두 번째 호출은 기존 값 덮지 않음
except ImportError:
    pass  # dotenv 미설치 — 시스템 환경변수만 사용 (GitHub Actions에서 OK)

EODHD_API_TOKEN = os.environ.get("EODHD_API_TOKEN")
FRED_API_KEY    = os.environ.get("FRED_API_KEY")

if not EODHD_API_TOKEN or not FRED_API_KEY:
    sys.exit(
        "[ERROR] 환경변수 EODHD_API_TOKEN / FRED_API_KEY 가 없습니다.\n"
        "  로컬: macro_dashboard/.env.local 파일에 키를 넣어주세요 (.env.example 참고)\n"
        "  CI:   GitHub Secrets에 EODHD_API_TOKEN, FRED_API_KEY 등록 필요"
    )

EODHD_EOD   = "https://eodhd.com/api/eod"
EODHD_MACRO = "https://eodhd.com/api/macro-indicator"
FRED_OBS    = "https://api.stlouisfed.org/fred/series/observations"

OUTPUT_PATH = "data.json"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 유틸리티
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def fetch_eodhd(ticker, limit=520, order="d"):
    """EODHD 일별 시계열 → [{'date':str, 'value':float}, ...] (오름차순)"""
    try:
        r = requests.get(f"{EODHD_EOD}/{ticker}", params={
            "api_token": EODHD_API_TOKEN, "fmt": "json",
            "limit": limit, "order": order
        }, timeout=15)
        r.raise_for_status()
        raw = r.json()
        if not isinstance(raw, list) or not raw:
            print(f"  ⚠ {ticker}: 빈 응답")
            return []
        series = [{"date": d["date"], "value": float(d["close"])} for d in raw]
        series.sort(key=lambda x: x["date"])
        print(f"  ✓ {ticker:25s} 최신: {series[-1]['date']}  {series[-1]['value']}")
        return series
    except Exception as e:
        print(f"  ✗ {ticker}: {e}")
        return []


def fetch_fred(series_id, limit=520, retries=3, delay=2):
    """FRED 경제 시계열 → [{'date':str, 'value':float}, ...] (오름차순)"""
    for attempt in range(retries):
        try:
            r = requests.get(FRED_OBS, params={
                "series_id": series_id, "api_key": FRED_API_KEY,
                "file_type": "json", "sort_order": "desc", "limit": limit
            }, timeout=20)
            r.raise_for_status()
            obs = r.json().get("observations", [])
            series = []
            for o in obs:
                v = o.get("value", ".")
                if v not in (".", "", None):
                    series.append({"date": o["date"], "value": float(v)})
            series.sort(key=lambda x: x["date"])
            if series:
                print(f"  ✓ FRED:{series_id:30s} 최신: {series[-1]['date']}  {series[-1]['value']}")
            else:
                print(f"  ⚠ FRED:{series_id}: 빈 응답")
            return series
        except Exception as e:
            if attempt < retries - 1:
                print(f"  ↺ FRED:{series_id} 재시도 {attempt+1}/{retries-1}: {e}")
                time.sleep(delay)
            else:
                print(f"  ✗ FRED:{series_id}: {e}")
                return []


def trim_monthly(series, months=24):
    """일별 시계열 → 월 대표값 (각 월의 마지막 거래일) 추출"""
    seen, result = set(), []
    for item in reversed(series):
        key = item["date"][:7]
        if key not in seen:
            seen.add(key)
            result.append(item)
        if len(result) >= months:
            break
    result.reverse()
    return result


def latest(series, default=None):
    return series[-1]["value"] if series else default


def to_label(date_str):
    parts = date_str.split("-")
    return f"{parts[0][2:]}.{parts[1]}" if len(parts) >= 2 else date_str


def compute_hv10(price_series):
    """10일 역사적 변동성(연율화) 계산"""
    if len(price_series) < 12:
        return []
    prices = [x["value"] for x in price_series]
    dates  = [x["date"]  for x in price_series]
    logs   = [math.log(prices[i] / prices[i-1]) for i in range(1, len(prices))]
    result = []
    for i in range(9, len(logs)):
        window   = logs[i-9:i+1]
        mean     = sum(window) / 10
        variance = sum((r - mean) ** 2 for r in window) / 9
        hv       = math.sqrt(variance * 252) * 100
        result.append({"date": dates[i+1], "value": round(hv, 2)})
    return result


def to_chart(series, months=24, scale=1.0, decimals=2):
    monthly = trim_monthly(series, months)
    return {
        "labels": [to_label(x["date"]) for x in monthly],
        "data":   [round(x["value"] * scale, decimals) for x in monthly]
    }


def load_existing():
    """기존 data.json 로드 — 없으면 빈 dict."""
    try:
        with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Scrapling 기반 ISM PMI 크롤링 (TradingEconomics) + RSS fallback
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _fetch_ism_pmi_rss():
    """Fallback: Google News RSS 헤드라인에서 PMI 수치 정규식 추출."""
    try:
        import xml.etree.ElementTree as ET
        rss_r = requests.get(
            "https://news.google.com/rss/search",
            params={"q": "ISM Manufacturing PMI", "hl": "en-US", "gl": "US", "ceid": "US:en"},
            headers={"User-Agent": "Mozilla/5.0 (compatible; MacroBot/1.0)"},
            timeout=15
        )
        rss_r.raise_for_status()
        root = ET.fromstring(rss_r.text)
        for item in root.findall(".//item")[:5]:
            t_el = item.find("title")
            if t_el is None:
                continue
            t = t_el.text or ""
            m = _re.search(r'Manufacturing\s+PMI[^\d]*(\d{2,3}\.?\d*)', t, _re.IGNORECASE)
            if m:
                pub = item.find("pubDate")
                return float(m.group(1)), (pub.text[:16] if pub is not None else "unknown"), "Google News RSS"
    except Exception as e:
        print(f"  ✗ ISM PMI (Google News RSS): {e}")
    return None, None, None


def fetch_ism_pmi():
    """
    1순위: TradingEconomics를 Scrapling StealthyFetcher로 (Cloudflare 우회)
    2순위: Google News RSS fallback

    Returns: (value, date_str, source) — 모두 실패 시 (None, None, None)
    """
    try:
        from scrapling.fetchers import StealthyFetcher
    except ImportError:
        print("  ⚠ scrapling 미설치 — `pip install \"scrapling[fetchers]\"` 후 `scrapling install`")
        return _fetch_ism_pmi_rss()

    url = "https://tradingeconomics.com/united-states/business-confidence"
    try:
        page = StealthyFetcher.fetch(url, headless=True, network_idle=True)
        # 1) 우선순위 셀렉터들
        for sel in [
            '#aspnetForm > #ctl00_ContentPlaceHolder1_ctl00_PanelPeers .table-heatmap td:nth-child(2)::text',
            '.te-cube-value::text',
            '.value::text',
            '#ctl00_ContentPlaceHolder1_ctl00_lblValue::text',
        ]:
            try:
                v = page.css(sel).get()
            except Exception:
                v = None
            if v:
                v = v.strip().replace(',', '')
                if _re.match(r'^\d{2,3}(\.\d+)?$', v):
                    val = float(v)
                    if 30 <= val <= 80:  # PMI 합리적 범위
                        print(f"  ✓ ISM PMI (Scrapling/TE): {val}")
                        return val, datetime.now().strftime("%Y-%m"), "Scrapling/TradingEconomics"
        # 2) 페이지 텍스트 정규식 — "Manufacturing PMI ... 50.3" 패턴 탐색
        try:
            html = page.html_content if hasattr(page, 'html_content') else str(page)
        except Exception:
            html = ""
        m = _re.search(
            r'(?:ISM\s+Manufacturing|Manufacturing\s+PMI)[^\d<]{0,200}?(\d{2}\.\d)',
            html, _re.IGNORECASE
        )
        if m:
            val = float(m.group(1))
            if 30 <= val <= 80:
                print(f"  ✓ ISM PMI (Scrapling/TE 정규식): {val}")
                return val, datetime.now().strftime("%Y-%m"), "Scrapling/TradingEconomics"
        print("  ⚠ TradingEconomics: PMI 셀렉터 못 찾음 → RSS fallback")
    except Exception as e:
        print(f"  ✗ ISM PMI (Scrapling): {e}")

    return _fetch_ism_pmi_rss()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 모드별 갱신 함수 — 각각 patch dict 반환 (실패한 키는 누락)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def update_daily():
    print("\n[DAILY 1/2] EODHD 시장 지표")
    vix    = fetch_eodhd("VIX.INDX")
    spx    = fetch_eodhd("GSPC.INDX", limit=1100)
    us10y  = fetch_eodhd("US10Y.GBOND")
    us2y   = fetch_eodhd("US2Y.GBOND")
    us30y  = fetch_eodhd("US30Y.GBOND")
    jp10y  = fetch_eodhd("JP10Y.GBOND")
    hyg    = fetch_eodhd("HYG.US")
    move   = fetch_eodhd("MOVE.INDX")
    skew   = fetch_eodhd("SKEW.INDX")
    usdjpy = fetch_eodhd("USDJPY.FOREX")
    dxy    = fetch_eodhd("DXY.INDX")
    gold   = fetch_eodhd("XAUUSD.FOREX")
    uso    = fetch_eodhd("USO.US")

    print("\n[DAILY 2/2] FRED 일별 시리즈")
    rrp    = fetch_fred("RRPONTSYD", limit=1500)
    us3m   = fetch_fred("DGS3MO",    limit=520)
    us5y   = fetch_fred("DGS5",      limit=520)
    ig_oas = fetch_fred("BAMLC0A0CM",   limit=520)
    hy_oas = fetch_fred("BAMLH0A0HYM2", limit=520)
    t10y2y = fetch_fred("T10Y2Y",    limit=520)
    bei    = fetch_fred("T10YIE",    limit=520)

    # ── 파생
    y2_map = {x["date"]: x["value"] for x in us2y}
    spread = [{"date": x["date"], "value": round(x["value"] - y2_map[x["date"]], 3)}
              for x in us10y if x["date"] in y2_map]
    spread = spread or t10y2y

    jp_map = {x["date"]: x["value"] for x in jp10y}
    us_jp = [{"date": x["date"], "value": round((x["value"] - jp_map[x["date"]]) * 100, 1)}
             for x in us10y if x["date"] in jp_map]

    hyg_hv = compute_hv10(hyg)
    ig_bp  = [{"date": x["date"], "value": round(x["value"] * 100, 1)} for x in ig_oas]
    hy_bp  = [{"date": x["date"], "value": round(x["value"] * 100, 1)} for x in hy_oas]

    out = {}
    if vix:    out["vix"]    = {"current": round(latest(vix), 2),    "chart": to_chart(vix)}
    if move:   out["move"]   = {"current": round(latest(move), 1),   "chart": to_chart(move)}
    if hyg:
        out["hyg"] = {
            "current": round(latest(hyg), 2),
            "hv10": round(latest(hyg_hv, 8), 2),
            "chart_price": to_chart(hyg),
            "chart_hv":    to_chart(hyg_hv) if hyg_hv else {"labels": [], "data": []}
        }
    if us3m:   out["us3m"]   = {"current": round(latest(us3m), 3)}
    if us2y:   out["us2y"]   = {"current": round(latest(us2y), 3),   "chart": to_chart(us2y)}
    if us5y:   out["us5y"]   = {"current": round(latest(us5y), 3)}
    if us10y:  out["us10y"]  = {"current": round(latest(us10y), 3),  "chart": to_chart(us10y)}
    if us30y:  out["us30y"]  = {"current": round(latest(us30y), 3),  "chart": to_chart(us30y)}
    if spread: out["spread_10y2y"] = {"current": round(latest(spread), 3), "chart": to_chart(spread)}
    if jp10y:  out["jp10y"]  = {"current": round(latest(jp10y), 3),  "chart": to_chart(jp10y)}
    if us_jp:
        out["us_jp_spread_bp"] = {"current": round(latest(us_jp), 1),
                                  "chart": to_chart(us_jp, decimals=1)}
    if rrp:    out["rrp"]    = {"current_B": round(latest(rrp), 1),
                                "chart": to_chart(rrp, decimals=1)}
    if ig_bp:  out["ig_oas"] = {"current_bp": round(latest(ig_bp), 1),
                                "chart": to_chart(ig_bp, decimals=1)}
    if hy_bp:  out["hy_oas"] = {"current_bp": round(latest(hy_bp), 1),
                                "chart": to_chart(hy_bp, decimals=1)}
    if bei:    out["bei_10y"] = {"current": round(latest(bei), 2),   "chart": to_chart(bei)}
    if us10y and bei:
        out["real_rate_10y"] = {"current": round(latest(us10y) - latest(bei), 2)}
    if skew:
        out["skew"] = {"current": round(latest(skew), 1),
                       "chart_skew": to_chart(skew),
                       "chart_spx":  to_chart(spx, decimals=0) if spx else {"labels": [], "data": []}}
    if spx:    out["spx"]    = {"current": round(latest(spx), 0),    "chart": to_chart(spx, decimals=0)}
    if usdjpy: out["usdjpy"] = {"current": round(latest(usdjpy), 2), "chart": to_chart(usdjpy)}
    if dxy:    out["dxy"]    = {"current": round(latest(dxy), 2),    "chart": to_chart(dxy)}
    if gold:   out["gold"]   = {"current": round(latest(gold), 0),   "chart": to_chart(gold, decimals=0)}
    if uso:    out["wti_uso"] = {"current": round(latest(uso), 2),   "chart": to_chart(uso)}
    return out


def update_weekly():
    print("\n[WEEKLY 1/2] FRED 주간 유동성 / 신규실업수당")
    walcl   = fetch_fred("WALCL",    limit=220)
    wtregen = fetch_fred("WTREGEN",  limit=220)
    rrp     = fetch_fred("RRPONTSYD", limit=1500)
    treast  = fetch_fred("TREAST",   limit=220)
    wresbal = fetch_fred("WRESBAL",  limit=220)
    icsa    = fetch_fred("ICSA",     limit=104)

    print("\n[WEEKLY 2/2] EODHD SPX (net_liq_spx 정렬용)")
    spx = fetch_eodhd("GSPC.INDX", limit=1100)

    rrp_map  = {x["date"]: x["value"] for x in rrp}
    tga_map  = {x["date"]: x["value"] for x in wtregen}
    wres_map = {x["date"]: x["value"] for x in wresbal}
    spx_map  = {x["date"]: x["value"] for x in spx}

    def nearest_spx(d_str):
        if d_str in spx_map:
            return spx_map[d_str]
        for delta in [1, -1, 2, -2, 3, -3, 4, -4, 5, -5]:
            alt = (datetime.strptime(d_str, "%Y-%m-%d") + timedelta(days=delta)).strftime("%Y-%m-%d")
            if alt in spx_map:
                return spx_map[alt]
        return None

    net_liq, wres_series, net_liq_spx = [], [], []
    for item in walcl:
        d_ = item["date"]
        tga_v  = tga_map.get(d_)
        wres_v = wres_map.get(d_)
        rrp_v  = rrp_map.get(d_)
        if rrp_v is None:
            for delta in [1, -1, 2, -2, 3, -3]:
                alt = (datetime.strptime(d_, "%Y-%m-%d") + timedelta(days=delta)).strftime("%Y-%m-%d")
                if alt in rrp_map:
                    rrp_v = rrp_map[alt]
                    break
        if tga_v is not None and rrp_v is not None:
            nl = round(item["value"] / 1000 - tga_v / 1000 - rrp_v, 1)
            net_liq.append({"date": d_, "value": nl})
            sv = nearest_spx(d_)
            if sv is not None:
                net_liq_spx.append({"date": d_, "nl": nl, "spx": round(sv, 0)})
        if wres_v is not None:
            wres_series.append({"date": d_, "value": round(wres_v / 1000, 1)})

    # RMP 누적 추정
    RMP_BASELINE_DATE = "2024-12-18"
    RMP_MONTHLY_RATE_B = 25.0
    rmp_baseline = next((x["value"] for x in treast if x["date"] == RMP_BASELINE_DATE), None)
    if rmp_baseline is None and treast:
        dec24 = [x for x in treast if "2024-12" in x["date"]]
        if dec24:
            rmp_baseline = dec24[-1]["value"]
    treast_latest = latest(treast, None)
    rmp_cumulative_B = (round((treast_latest - rmp_baseline) / 1000, 1)
                        if (treast_latest is not None and rmp_baseline is not None) else None)

    icsa_K    = [{"date": x["date"], "value": round(x["value"] / 1000, 0)} for x in icsa]
    fed_bal_T = [{"date": x["date"], "value": round(x["value"] / 1_000_000, 2)} for x in walcl]
    tga_B     = [{"date": x["date"], "value": round(x["value"] / 1_000, 1)} for x in wtregen]

    out = {}
    if walcl:   out["fed_balance"]  = {"current_T": round(latest(fed_bal_T), 2),
                                       "chart": to_chart(fed_bal_T, decimals=2)}
    if wtregen: out["tga"]          = {"current_B": round(latest(tga_B), 1),
                                       "chart": to_chart(tga_B, decimals=1)}
    if wres_series:
        out["bank_reserves"] = {"current_B": round(latest(wres_series), 1),
                                "chart": to_chart(wres_series, decimals=1)}
        out["wres_series"]   = {"chart": to_chart(wres_series, months=52, decimals=1)}
    if rmp_cumulative_B is not None:
        out["rmp"] = {
            "cumulative_B":   rmp_cumulative_B,
            "baseline_date":  RMP_BASELINE_DATE,
            "monthly_rate_B": RMP_MONTHLY_RATE_B
        }
    if net_liq:
        out["net_liq_series"] = {"chart": to_chart(net_liq, months=52, decimals=1)}
    if net_liq_spx:
        nls = net_liq_spx[-220:] if len(net_liq_spx) > 220 else net_liq_spx
        out["net_liq_spx"] = {"chart": {
            "labels": [to_label(x["date"]) for x in nls],
            "nl":     [x["nl"]  for x in nls],
            "spx":    [x["spx"] for x in nls]
        }}
    if icsa_K:
        out["jobless_claims"] = {"current_K": round(latest(icsa_K), 0),
                                 "chart": to_chart(icsa_K)}
    return out


def update_monthly():
    print("\n[MONTHLY 1/4] FRED 월간 거시")
    ffr    = fetch_fred("FEDFUNDS", limit=48)
    unrate = fetch_fred("UNRATE",   limit=48)
    payems = fetch_fred("PAYEMS",   limit=48)
    jolts  = fetch_fred("JTSJOL",   limit=36)

    print("\n[MONTHLY 2/4] EODHD CPI annual")
    cpi_series = []
    try:
        r = requests.get(EODHD_MACRO + "/USA", params={
            "indicator": "inflation_consumer_prices_annual",
            "api_token": EODHD_API_TOKEN, "fmt": "json"
        }, timeout=15)
        r.raise_for_status()
        cpi_series = sorted(
            [{"date": x["Date"], "value": float(x["Value"])} for x in r.json()],
            key=lambda x: x["date"]
        )
        print(f"  ✓ CPI (annual): 최신 {cpi_series[-1]['date']}  {cpi_series[-1]['value']:.2f}%")
    except Exception as e:
        print(f"  ✗ CPI: {e}")

    print("\n[MONTHLY 3/4] ISM PMI (Scrapling → TradingEconomics, RSS fallback)")
    ism_val, ism_date, ism_source = fetch_ism_pmi()

    print("\n[MONTHLY 4/4] 중국 LPR (CFETS)")
    china_lpr_1y = china_lpr_5y = china_lpr_date = None
    try:
        lpr_r = requests.get(
            "https://www.chinamoney.com.cn/r/cms/www/chinamoney/data/currency/bk-lpr.json",
            headers={"Referer": "https://www.chinamoney.com.cn/english/bmklpr/",
                     "User-Agent": "Mozilla/5.0 (compatible; MacroBot/1.0)"},
            timeout=15
        )
        lpr_r.raise_for_status()
        lpr_json = lpr_r.json()
        china_lpr_date = lpr_json.get("data", {}).get("showDateEN", "")
        for rec in lpr_json.get("records", []):
            if rec.get("termCode") == "1Y":
                china_lpr_1y = float(rec.get("shibor", 0))
            elif rec.get("termCode") == "5Y":
                china_lpr_5y = float(rec.get("shibor", 0))
        print(f"  ✓ 중국 LPR 1Y: {china_lpr_1y}%  5Y: {china_lpr_5y}%  ({china_lpr_date})")
    except Exception as e:
        print(f"  ✗ 중국 LPR: {e}")

    nfp_change = [{"date": payems[i]["date"],
                   "value": round(payems[i]["value"] - payems[i-1]["value"], 0)}
                  for i in range(1, len(payems))]
    jolts_M = [{"date": x["date"], "value": round(x["value"] / 1000, 2)} for x in jolts]

    out = {}
    if ffr:    out["fed_funds"]    = {"current": round(latest(ffr), 2), "chart": to_chart(ffr)}
    if unrate: out["unemployment"] = {"current": round(latest(unrate), 1), "chart": to_chart(unrate)}
    if nfp_change:
        out["nfp"] = {"current_K": round(latest(nfp_change), 0), "chart": to_chart(nfp_change)}
    if jolts_M:
        out["jolts"] = {"current_M": round(latest(jolts_M), 2), "chart": to_chart(jolts_M)}
    if cpi_series:
        out["cpi_annual"] = {"current": round(latest(cpi_series), 2), "chart": to_chart(cpi_series)}
    if ism_val is not None:
        out["ism_pmi"] = {"current": ism_val, "source": ism_source, "date": ism_date}
    if china_lpr_1y is not None:
        out["china_lpr"] = {"lpr_1y": china_lpr_1y, "lpr_5y": china_lpr_5y, "date": china_lpr_date}
    return out


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def main():
    parser = argparse.ArgumentParser(description="DS Macro Jungle — 데이터 수집기")
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument("--full",    action="store_true", help="전체 갱신 (기본)")
    grp.add_argument("--daily",   action="store_true", help="일별 시장/금리/크레딧/인플레")
    grp.add_argument("--weekly",  action="store_true", help="주간 Fed/Net Liquidity/RMP/실업수당")
    grp.add_argument("--monthly", action="store_true", help="월간 NFP/실업률/JOLTS/CPI/ISM/LPR")
    args = parser.parse_args()

    if args.daily:    mode = "daily"
    elif args.weekly: mode = "weekly"
    elif args.monthly: mode = "monthly"
    else:             mode = "full"

    print("=" * 50)
    print(f"  DS MACRO JUNGLE — {mode.upper()} MODE")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    existing = load_existing()
    patch = {}

    if mode in ("full", "daily"):
        patch.update(update_daily())
    if mode in ("full", "weekly"):
        patch.update(update_weekly())
    if mode in ("full", "monthly"):
        patch.update(update_monthly())

    # 기존 위에 patch 덮어쓰기 (실패한 키는 patch에 없으므로 기존 값 보존)
    merged = dict(existing)
    merged.update(patch)

    # 메타: 모드별 마지막 실행 시각 누적 기록
    now_iso = datetime.now().isoformat()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M KST")
    prev_meta = existing.get("meta", {}) or {}
    new_meta = {
        "updated_at":  now_iso,
        "updated_str": now_str,
        "last_mode":   mode,
        "last_full_at":    prev_meta.get("last_full_at"),
        "last_daily_at":   prev_meta.get("last_daily_at"),
        "last_weekly_at":  prev_meta.get("last_weekly_at"),
        "last_monthly_at": prev_meta.get("last_monthly_at"),
    }
    new_meta[f"last_{mode}_at"] = now_iso
    if mode == "full":
        # full 모드는 모든 카테고리를 한 번에 갱신한 셈
        new_meta["last_daily_at"]   = now_iso
        new_meta["last_weekly_at"]  = now_iso
        new_meta["last_monthly_at"] = now_iso
    merged["meta"] = new_meta

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 50)
    print(f"  ✅ data.json 저장 — {len(patch)}개 키 갱신")
    print("=" * 50)
    if "vix" in patch:           print(f"  VIX          : {merged['vix']['current']}")
    if "spx" in patch:           print(f"  SPX          : {merged['spx']['current']:,.0f}")
    if "us10y" in patch:         print(f"  US 10Y       : {merged['us10y']['current']}%")
    if "fed_balance" in patch:   print(f"  Fed Balance  : ${merged['fed_balance']['current_T']:.2f}T")
    if "bank_reserves" in patch: print(f"  은행 지준금  : ${merged['bank_reserves']['current_B']:.0f}B")
    if "rmp" in patch and merged.get('rmp', {}).get('cumulative_B') is not None:
        print(f"  RMP 누적     : ${merged['rmp']['cumulative_B']:.1f}B")
    if "fed_funds" in patch:     print(f"  Fed Funds    : {merged['fed_funds']['current']}%")
    if "unemployment" in patch:  print(f"  실업률       : {merged['unemployment']['current']}%")
    if "ism_pmi" in patch:       print(f"  ISM PMI      : {merged['ism_pmi']['current']} ({merged['ism_pmi']['source']})")
    if "china_lpr" in patch:     print(f"  중국 LPR 1Y  : {merged['china_lpr']['lpr_1y']}%")
    print(f"  업데이트     : {now_str}  /  mode={mode}")
    print("=" * 50)


if __name__ == "__main__":
    main()
