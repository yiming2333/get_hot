"""
铁律筛选引擎 - 8条刚性准入条件，违反任何一条直接一票否决
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
from typing import List, Optional

from config import CFG
from data_fetcher import get_stock_history
from utils import parse_time, safe_float, safe_int

logger = logging.getLogger("filter")


class IronFilter:
    """徐翔铁律筛选器"""

    def __init__(self, date_str: str, limit_up_df: pd.DataFrame,
                 turnover_rank_df: pd.DataFrame = None,
                 history_cache: dict = None):
        self.date_str = date_str
        self.limit_up_df = limit_up_df
        self.turnover_rank_df = turnover_rank_df
        self._history_cache = history_cache or {}
        self.rules = CFG.iron

    def _get_history(self, code: str) -> pd.DataFrame:
        if code not in self._history_cache:
            self._history_cache[code] = get_stock_history(code, days=300)
        return self._history_cache[code]

    def run_all(self) -> pd.DataFrame:
        """对涨停池逐条执行8条铁律"""
        if self.limit_up_df.empty:
            return pd.DataFrame()

        passed = []
        total = len(self.limit_up_df)
        reject_reasons: dict = {}

        for idx, row in self.limit_up_df.iterrows():
            code = row.get("code", "")
            name = row.get("name", "")
            print(f"  筛选 [{idx+1}/{total}] {code} {name} ...", end="")

            reasons: List[str] = []
            hist = self._get_history(code)

            if not self._rule1_limit_up(row):
                reasons.append("R1-非涨停/尾盘偷袭")
            if not self._rule2_liquidity(row):
                reasons.append("R2-流动性不足")
            if not self._rule3_gene(hist, row):
                reasons.append("R3-涨停基因不足")
            if not self._rule4_volume(hist, row):
                reasons.append("R4-量能不足")
            if not self._rule5_trend(hist, row):
                reasons.append("R5-趋势不达标")
            if not self._rule6_chip_resistance(hist, row):
                reasons.append("R6-上方抛压过大")
            if not self._rule7_seal_quality(row):
                reasons.append("R7-封板质量差")
            if not self._rule8_risk_exclusion(hist, row):
                reasons.append("R8-风险排除")

            if reasons:
                print(f" ❌ {'|'.join(reasons)}")
                for r in reasons:
                    reject_reasons[r] = reject_reasons.get(r, 0) + 1
            else:
                print(f" ✅ 通过")
                passed.append(row)

        result = pd.DataFrame(passed)
        if not result.empty:
            result = result.reset_index(drop=True)

        # 记录淘汰分布
        if reject_reasons:
            logger.info(f"淘汰分布: {reject_reasons}")

        return result

    # ============================================================
    # 铁律1：标的范围 - 仅限当日涨停，排除尾盘偷袭
    # ============================================================
    def _rule1_limit_up(self, row) -> bool:
        seal_time = str(row.get("seal_time", "") or row.get("first_seal_time", ""))
        t = parse_time(seal_time)
        if t and t.hour >= self.rules.late_seal_hour and t.minute >= self.rules.late_seal_minute:
            return False
        return True

    # ============================================================
    # 铁律2：价格与流动性
    # ============================================================
    def _rule2_liquidity(self, row) -> bool:
        price = safe_float(row.get("close"))
        circ_mv = safe_float(row.get("circ_mv"))
        price_ok = price <= self.rules.max_price
        mv_ok = circ_mv <= self.rules.max_circ_mv
        if not (price_ok or mv_ok):
            return False
        amount = safe_float(row.get("amount"))
        return amount > 0

    # ============================================================
    # 铁律3：涨停基因（修复：兼容10%/20%涨跌幅）
    # ============================================================
    def _rule3_gene(self, hist: pd.DataFrame, row) -> bool:
        if hist.empty:
            return False
        cutoff = datetime.now() - timedelta(days=self.rules.gene_lookback_months * 30)
        hist_copy = hist.copy()
        hist_copy["date_dt"] = pd.to_datetime(hist_copy["date"])
        recent = hist_copy[hist_copy["date_dt"] >= cutoff]
        if recent.empty:
            return False
        # 自适应涨停阈值：根据近12月最大涨幅判断是10%还是20%板
        max_pct = recent["pct_chg"].astype(float).max()
        if max_pct > 15:
            threshold = 19.5  # 20%涨跌幅限制
        else:
            threshold = self.rules.gene_pct_threshold  # 10%涨跌幅限制
        limit_ups = recent[recent["pct_chg"].astype(float) >= threshold]
        logger.debug(f"{row.get('code')}: 涨停基因={len(limit_ups)}次(阈值={threshold}%)")
        return len(limit_ups) >= self.rules.gene_min_limit_ups

    # ============================================================
    # 铁律4：量能验证
    # ============================================================
    def _rule4_volume(self, hist: pd.DataFrame, row) -> bool:
        if hist.empty:
            return False
        today_vol = safe_float(row.get("amount"))
        if today_vol <= 0 and len(hist) >= 1:
            today_vol = safe_float(hist.iloc[-1].get("amount"))
        lookback = self.rules.vol_lookback_days
        if len(hist) < lookback + 1:
            return False
        prev_avg = hist["amount"].astype(float).iloc[-(lookback + 1):-1].mean()
        if prev_avg <= 0:
            return False
        return today_vol >= prev_avg * (1 + self.rules.vol_min_amplify)

    # ============================================================
    # 铁律5：趋势斜率（修复：日均斜率替代角度制）
    # ============================================================
    def _rule5_trend(self, hist: pd.DataFrame, row) -> bool:
        if len(hist) < 30:
            return False
        closes = hist["close"].astype(float).values
        ma5 = pd.Series(closes).rolling(self.rules.ma_short).mean().dropna().values
        if len(ma5) < 5:
            return False
        # 日均斜率百分比
        slope_pct = (ma5[-1] - ma5[-5]) / ma5[-5] * 100
        daily_slope = slope_pct / 5
        if daily_slope >= self.rules.trend_slope_threshold:
            return True
        # 或者突破长期均线
        current_price = closes[-1]
        for ma_len in self.rules.long_term_mas:
            if len(closes) >= ma_len:
                ma_val = np.mean(closes[-ma_len:])
                if abs(current_price - ma_val) / ma_val < 0.03:
                    pct = safe_float(row.get("pct_chg"))
                    if pct >= 9.5:
                        return True
        return False

    # ============================================================
    # 铁律6：上方阻力
    # ============================================================
    def _rule6_chip_resistance(self, hist: pd.DataFrame, row) -> bool:
        if len(hist) < 60:
            return True
        closes = hist["close"].astype(float).values
        current = closes[-1]
        lookback = min(120, len(closes))
        recent = closes[-lookback:]
        above = np.sum(recent > current * 1.02)
        resistance = above / lookback
        return resistance <= self.rules.max_chip_resistance

    # ============================================================
    # 铁律7：封板质量
    # ============================================================
    def _rule7_seal_quality(self, row) -> bool:
        seal_time = str(row.get("seal_time", "") or row.get("first_seal_time", ""))
        t = parse_time(seal_time)
        if not t:
            return False
        # 必须在开盘后
        if t.hour < 9 or (t.hour == 9 and t.minute < 30):
            return False
        # 开盘后 N 分钟内封板
        minutes_from_open = (t.hour - 9) * 60 + t.minute - 30
        if minutes_from_open > self.rules.seal_time_limit_min:
            return False
        # 炸板次数
        open_count = safe_int(row.get("open_count"))
        if open_count > self.rules.seal_open_times_max:
            return False
        return True

    # ============================================================
    # 铁律8：风险排除
    # ============================================================
    def _rule8_risk_exclusion(self, hist: pd.DataFrame, row) -> bool:
        name = str(row.get("name", ""))
        if "ST" in name or "*ST" in name:
            return False
        if hist.empty:
            return True
        recent = hist.tail(self.rules.risk_lookback_days + 1)
        if len(recent) >= 2:
            for _, r in recent.iterrows():
                high = safe_float(r.get("high"))
                low = safe_float(r.get("low"))
                close = safe_float(r.get("close"))
                open_ = safe_float(r.get("open"))
                if open_ > 0 and close > 0:
                    intraday_range = (high - low) / open_
                    if intraday_range > self.rules.intraday_range_max:
                        return False
                    if high > 0 and (high - close) / high > abs(self.rules.crash_threshold):
                        pct = safe_float(r.get("pct_chg"))
                        if pct < 5:
                            return False
        return True
