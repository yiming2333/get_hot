"""
数据采集层 - 东方财富 + 新浪财经 + 磁盘缓存
"""
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import time
import random
import os
import hashlib
import logging
import warnings
from typing import Dict, Optional

from config import CFG
from utils import safe_float

warnings.filterwarnings("ignore")
logger = logging.getLogger("data")

CACHE_DIR = os.path.join(os.path.dirname(__file__), CFG.cache_dir)
os.makedirs(CACHE_DIR, exist_ok=True)


def _throttle():
    time.sleep(CFG.request_delay + random.uniform(0, 0.15))


def _cache_path(prefix: str, key: str, date_str: str) -> str:
    h = hashlib.md5(f"{prefix}_{key}_{date_str}".encode()).hexdigest()[:12]
    return os.path.join(CACHE_DIR, f"{prefix}_{date_str}_{h}.pkl")


def _load_cache(path: str, max_age_hours: int = 12) -> Optional[pd.DataFrame]:
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
    except Exception as e:
        logger.warning(f"缓存写入失败: {e}")


# ============================================================
# 涨停池（东方财富）
# ============================================================
def get_limit_up_stocks(date_str: str) -> pd.DataFrame:
    """获取当日涨停股池"""
    cache = _load_cache(_cache_path("zt", "pool", date_str), max_age_hours=24)
    if cache is not None:
        logger.info(f"涨停池缓存命中: {len(cache)} 只")
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
        if "seal_time" not in df.columns:
            df["seal_time"] = df.get("first_seal_time", "")
        _save_cache(_cache_path("zt", "pool", date_str), df)
        logger.info(f"涨停池获取成功: {len(df)} 只")
        return df
    except Exception as e:
        logger.error(f"涨停池获取失败: {e}")
        return pd.DataFrame()


# ============================================================
# 个股历史K线（新浪财经）
# ============================================================
def _code_to_sina(code: str) -> str:
    """股票代码转新浪格式: 000553 -> sz000553"""
    if code.startswith(("0", "3")):
        return f"sz{code}"
    elif code.startswith(("6", "9")):
        return f"sh{code}"
    return f"sz{code}"


def _fetch_one_history(code: str, days: int = 250) -> tuple:
    """单只股票历史K线"""
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
        df = df.sort_values("date").reset_index(drop=True)
        if "pct_chg" not in df.columns and len(df) > 1:
            df["pct_chg"] = df["close"].astype(float).pct_change() * 100
        return (code, df)
    except Exception as e:
        logger.warning(f"历史数据获取失败 {code}: {e}")
        return (code, pd.DataFrame())


def batch_get_history(codes: list, days: int = 250, date_str: str = "") -> Dict[str, pd.DataFrame]:
    """批量获取历史数据（串行 + 缓存）"""
    result: Dict[str, pd.DataFrame] = {}
    to_fetch = []

    for code in codes:
        cache = _load_cache(_cache_path("hist", code, date_str or "latest"), max_age_hours=12)
        if cache is not None and len(cache) > 20:
            result[code] = cache
        else:
            to_fetch.append(code)

    if not to_fetch:
        logger.info(f"历史数据全部缓存命中: {len(result)} 只")
        return result

    logger.info(f"缓存命中 {len(result)}/{len(codes)}，需拉取 {len(to_fetch)} 只")

    done = 0
    for code in to_fetch:
        done += 1
        print(f"\r  拉取 [{done}/{len(to_fetch)}] {code}...", end="", flush=True)
        _, df = _fetch_one_history(code, days)
        if not df.empty and len(df) > 20:
            result[code] = df
            _save_cache(_cache_path("hist", code, date_str or "latest"), df)

    print()
    logger.info(f"历史数据获取完成: {len(result)}/{len(codes)} 只")
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


# ============================================================
# 板块资金流（东方财富）
# ============================================================
def get_sector_flow() -> pd.DataFrame:
    """获取行业板块资金流排名"""
    cache = _load_cache(_cache_path("flow", "sector", "today"), max_age_hours=4)
    if cache is not None:
        logger.info("板块资金流缓存命中")
        return cache
    try:
        df = ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流")
        if df is not None and not df.empty:
            _save_cache(_cache_path("flow", "sector", "today"), df)
            logger.info(f"板块资金流获取成功: {len(df)} 个板块")
            return df
    except Exception as e:
        logger.warning(f"板块资金流获取失败: {e}")
    return pd.DataFrame()


# ============================================================
# 个股资金流（东方财富）
# ============================================================
def get_individual_fund_flow() -> pd.DataFrame:
    """获取个股主力资金流排名（实时）"""
    cache = _load_cache(_cache_path("flow", "individual", "today"), max_age_hours=2)
    if cache is not None:
        logger.info("个股资金流缓存命中")
        return cache
    try:
        df = ak.stock_individual_fund_flow_rank(indicator="今日")
        if df is not None and not df.empty:
            # 统一列名
            col_map = {
                "代码": "code", "名称": "name",
                "主力净流入-净额": "main_net_inflow",
                "主力净流入-净占比": "main_net_pct",
                "超大单净流入-净额": "super_large_net",
                "大单净流入-净额": "large_net",
                "中单净流入-净额": "medium_net",
                "小单净流入-净额": "small_net",
            }
            df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
            _save_cache(_cache_path("flow", "individual", "today"), df)
            logger.info(f"个股资金流获取成功: {len(df)} 只")
            return df
    except Exception as e:
        logger.warning(f"个股资金流获取失败（不影响核心筛选）: {e}")
    return pd.DataFrame()


# ============================================================
# 龙虎榜（东方财富）
# ============================================================
def get_dragon_tiger_list(date_str: str) -> pd.DataFrame:
    """
    获取龙虎榜详情（当日上榜个股）
    包含：龙虎榜净买额、机构买卖、上榜原因等
    """
    cache = _load_cache(_cache_path("lhb", "detail", date_str), max_age_hours=24)
    if cache is not None:
        logger.info(f"龙虎榜缓存命中: {len(cache)} 条")
        return cache
    try:
        # 查当日龙虎榜（日期前后各1天以防数据延迟）
        dt = datetime.strptime(date_str, "%Y%m%d")
        start = (dt - timedelta(days=1)).strftime("%Y%m%d")
        end = dt.strftime("%Y%m%d")
        df = ak.stock_lhb_detail_em(start_date=start, end_date=end)
        if df is None or df.empty:
            return pd.DataFrame()
        # 统一列名
        col_map = {
            "代码": "code", "名称": "name", "上榜日": "lhb_date",
            "收盘价": "close", "涨跌幅": "pct_chg",
            "龙虎榜净买额": "lhb_net_buy", "龙虎榜买入额": "lhb_buy_amt",
            "龙虎榜卖出额": "lhb_sell_amt", "龙虎榜成交额": "lhb_total_amt",
            "市场总成交额": "market_total_amt",
            "净买额占总成交比": "lhb_net_pct", "成交额占总成交比": "lhb_amt_pct",
            "换手率": "turnover", "流通市值": "circ_mv",
            "上榜原因": "lhb_reason", "解读": "lhb_comment",
            "上榜后1日": "after_1d", "上榜后2日": "after_2d",
            "上榜后5日": "after_5d", "上榜后10日": "after_10d",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        _save_cache(_cache_path("lhb", "detail", date_str), df)
        logger.info(f"龙虎榜获取成功: {len(df)} 条")
        return df
    except Exception as e:
        logger.warning(f"龙虎榜获取失败: {e}")
        return pd.DataFrame()


def get_dragon_tiger_institution(date_str: str) -> pd.DataFrame:
    """
    获取龙虎榜机构买卖统计（当日）
    包含：机构买入/卖出总额、净买额等
    """
    cache = _load_cache(_cache_path("lhb", "inst", date_str), max_age_hours=24)
    if cache is not None:
        logger.info(f"龙虎榜机构统计缓存命中: {len(cache)} 条")
        return cache
    try:
        dt = datetime.strptime(date_str, "%Y%m%d")
        start = (dt - timedelta(days=1)).strftime("%Y%m%d")
        end = dt.strftime("%Y%m%d")
        df = ak.stock_lhb_jgmmtj_em(start_date=start, end_date=end)
        if df is None or df.empty:
            return pd.DataFrame()
        col_map = {
            "代码": "code", "名称": "name",
            "收盘价": "close", "涨跌幅": "pct_chg",
            "买方机构数": "buy_inst_count", "卖方机构数": "sell_inst_count",
            "机构买入总额": "inst_buy_amt", "机构卖出总额": "inst_sell_amt",
            "机构买入净额": "inst_net_buy",
            "机构净买额占总成交额比": "inst_net_pct",
            "换手率": "turnover", "流通市值": "circ_mv",
            "上榜原因": "lhb_reason", "上榜日期": "lhb_date",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        _save_cache(_cache_path("lhb", "inst", date_str), df)
        logger.info(f"龙虎榜机构统计获取成功: {len(df)} 条")
        return df
    except Exception as e:
        logger.warning(f"龙虎榜机构统计获取失败: {e}")
        return pd.DataFrame()


# ============================================================
# 北向资金（东方财富 - 沪深港通）
# ============================================================
def get_northbound_flow() -> pd.DataFrame:
    """
    获取北向资金持股排行（当日）
    包含：持股数量、市值、增持估计、占流通股比等
    """
    cache = _load_cache(_cache_path("north", "hold", "today"), max_age_hours=4)
    if cache is not None:
        logger.info(f"北向资金缓存命中: {len(cache)} 只")
        return cache
    try:
        df = ak.stock_hsgt_hold_stock_em(market="北向", indicator="今日排行")
        if df is None or df.empty:
            return pd.DataFrame()
        col_map = {
            "代码": "code", "名称": "name",
            "今日收盘价": "close", "今日涨跌幅": "pct_chg",
            "今日持股-股数": "nb_hold_shares", "今日持股-市值": "nb_hold_mv",
            "今日持股-占流通股比": "nb_hold_circ_pct", "今日持股-占总股本比": "nb_hold_total_pct",
            "今日增持估计-股数": "nb_add_shares", "今日增持估计-市值": "nb_add_mv",
            "今日增持估计-市值增幅": "nb_add_mv_pct",
            "今日增持估计-占流通股比": "nb_add_circ_pct",
            "所属板块": "sector",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        # 确保 code 列是字符串
        df["code"] = df["code"].astype(str).str.zfill(6)
        _save_cache(_cache_path("north", "hold", "today"), df)
        logger.info(f"北向资金获取成功: {len(df)} 只")
        return df
    except Exception as e:
        logger.warning(f"北向资金获取失败: {e}")
        return pd.DataFrame()
