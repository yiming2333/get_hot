"""
数据采集层 - 新浪数据源 + 磁盘缓存
"""
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import time
import random
import os
import hashlib
import warnings
warnings.filterwarnings("ignore")

CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache")
os.makedirs(CACHE_DIR, exist_ok=True)

REQUEST_DELAY = 0.6


def _throttle():
    time.sleep(REQUEST_DELAY + random.uniform(0, 0.15))


def _cache_path(prefix: str, key: str, date_str: str) -> str:
    h = hashlib.md5(f"{prefix}_{key}_{date_str}".encode()).hexdigest()[:12]
    return os.path.join(CACHE_DIR, f"{prefix}_{date_str}_{h}.pkl")


def _load_cache(path: str, max_age_hours: int = 12):
    if not os.path.exists(path):
        return None
    if time.time() - os.path.getmtime(path) > max_age_hours * 3600:
        return None
    try:
        return pd.read_pickle(path)
    except Exception:
        return None


def _save_cache(path: str, df: pd.DataFrame):
    try:
        df.to_pickle(path)
    except Exception:
        pass


# ============================================================
# 涨停池（东方财富，这个接口本身没问题）
# ============================================================
def get_limit_up_stocks(date_str: str) -> pd.DataFrame:
    cache = _load_cache(_cache_path("zt", "pool", date_str), max_age_hours=24)
    if cache is not None:
        return cache
    try:
        df = ak.stock_zt_pool_em(date=date_str)
        if df is None or df.empty:
            return pd.DataFrame()
        col_map = {
            "代码": "code", "名称": "name", "最新价": "close",
            "涨跌幅": "pct_chg", "成交额": "amount",
            "流通市值": "circ_mv", "总市值": "total_mv",
            "换手率": "turnover", "首次封板时间": "first_seal_time",
            "最后封板时间": "last_seal_time", "炸板次数": "open_count",
            "连板数": "ban_count", "涨停统计": "zt_stats",
            "所属行业": "industry", "封板资金": "seal_money",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        # 兼容：合并封板时间
        if "seal_time" not in df.columns:
            df["seal_time"] = df.get("first_seal_time", "")
        _save_cache(_cache_path("zt", "pool", date_str), df)
        return df
    except Exception as e:
        print(f" ❌ {e}")
        return pd.DataFrame()


# ============================================================
# 个股历史K线（新浪接口，从这台服务器可用）
# ============================================================
def _code_to_sina(code: str) -> str:
    """000553 -> sz000553, 600379 -> sh600379"""
    if code.startswith(("0", "3")):
        return f"sz{code}"
    elif code.startswith(("6", "9")):
        return f"sh{code}"
    return f"sz{code}"


def _fetch_one_history(code: str, days: int = 250) -> tuple:
    """单只股票历史（新浪源）"""
    try:
        sina_code = _code_to_sina(code)
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days * 2)).strftime("%Y%m%d")
        _throttle()
        df = ak.stock_zh_a_daily(
            symbol=sina_code, start_date=start, end_date=end, adjust="qfq"
        )
        if df is None or df.empty:
            return (code, pd.DataFrame())
        # 新浪返回的列: date, open, high, low, close, volume, amount, outstanding_share, turnover
        # 统一列名（已经基本一致）
        df = df.sort_values("date").reset_index(drop=True)
        # 确保有 pct_chg 列
        if "pct_chg" not in df.columns and len(df) > 1:
            df["pct_chg"] = df["close"].astype(float).pct_change() * 100
        return (code, df)
    except Exception:
        return (code, pd.DataFrame())


def batch_get_history(codes: list, days: int = 250, date_str: str = "") -> dict:
    """批量获取历史数据（串行+缓存）"""
    result = {}
    to_fetch = []

    for code in codes:
        cache = _load_cache(_cache_path("hist", code, date_str or "latest"), max_age_hours=12)
        if cache is not None and len(cache) > 20:
            result[code] = cache
        else:
            to_fetch.append(code)

    if not to_fetch:
        return result

    print(f"  缓存命中 {len(result)}/{len(codes)}，需拉取 {len(to_fetch)} 只...")

    done = 0
    for code in to_fetch:
        done += 1
        print(f"\r  拉取 [{done}/{len(to_fetch)}] {code}...", end="", flush=True)
        _, df = _fetch_one_history(code, days)
        if not df.empty and len(df) > 20:
            result[code] = df
            _save_cache(_cache_path("hist", code, date_str or "latest"), df)

    print()
    return result


def get_stock_history(code: str, days: int = 250) -> pd.DataFrame:
    """单只股票历史（兼容接口）"""
    date_str = datetime.now().strftime("%Y%m%d")
    cache = _load_cache(_cache_path("hist", code, date_str), max_age_hours=12)
    if cache is not None:
        return cache
    _, df = _fetch_one_history(code, days)
    if not df.empty:
        _save_cache(_cache_path("hist", code, date_str), df)
    return df


def get_sector_flow() -> pd.DataFrame:
    cache = _load_cache(_cache_path("flow", "sector", "today"), max_age_hours=4)
    if cache is not None:
        return cache
    try:
        df = ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流")
        if df is not None and not df.empty:
            _save_cache(_cache_path("flow", "sector", "today"), df)
            return df
    except Exception:
        pass
    return pd.DataFrame()


def get_individual_fund_flow() -> pd.DataFrame:
    return pd.DataFrame()
