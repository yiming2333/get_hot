"""
铁律筛选引擎 - 8条刚性准入条件，违反任何一条直接一票否决
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from config import *
from data_fetcher import get_stock_history
import warnings
warnings.filterwarnings("ignore")


def _parse_time(t_str: str):
    """解析时间字符串，支持 092500 和 09:25:00 两种格式"""
    t_str = str(t_str).strip()
    if not t_str:
        return None
    # 先试无冒号格式 092500
    if len(t_str) == 6 and t_str.isdigit():
        try:
            return datetime.strptime(t_str, "%H%M%S")
        except:
            pass
    # 再试有冒号格式
    for fmt in ["%H:%M:%S", "%H:%M"]:
        try:
            return datetime.strptime(t_str, fmt)
        except:
            continue
    return None


class IronFilter:
    """徐翔铁律筛选器"""

    def __init__(self, date_str: str, limit_up_df: pd.DataFrame,
                 turnover_rank_df: pd.DataFrame = None,
                 history_cache: dict = None):
        self.date_str = date_str
        self.limit_up_df = limit_up_df
        self.turnover_rank_df = turnover_rank_df
        self._history_cache = history_cache or {}

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

        for idx, row in self.limit_up_df.iterrows():
            code = row.get("code", "")
            name = row.get("name", "")
            print(f"  筛选 [{idx+1}/{total}] {code} {name} ...", end="")

            reasons = []
            hist = self._get_history(code)

            if not self._rule1_limit_up(row):
                reasons.append("R1-非涨停/尾盘偷袭")
            if not self._rule2_liquidity(row):
                reasons.append("R2-流动性不足")
            if not self._rule3_gene(hist, row):
                reasons.append("R3-涨停基因<5")
            if not self._rule4_volume(hist, row):
                reasons.append("R4-量能不足")
            if not self._rule5_trend(hist, row):
                reasons.append("R5-趋势不达标")
            if not self._rule6_chip_resistance(hist, row):
                reasons.append("R6-上方抛压>20%")
            if not self._rule7_seal_quality(row):
                reasons.append("R7-封板质量差")
            if not self._rule8_risk_exclusion(hist, row):
                reasons.append("R8-风险排除")

            if reasons:
                print(f" ❌ {'|'.join(reasons)}")
            else:
                print(f" ✅ 通过")
                passed.append(row)

        result = pd.DataFrame(passed)
        if not result.empty:
            result = result.reset_index(drop=True)
        return result

    # ============================================================
    # 铁律1：标的范围 - 仅限当日涨停，排除尾盘偷袭
    # ============================================================
    def _rule1_limit_up(self, row) -> bool:
        seal_time = str(row.get("seal_time", "") or row.get("first_seal_time", ""))
        t = _parse_time(seal_time)
        if t and t.hour == 14 and t.minute >= 50:
            return False
        return True

    # ============================================================
    # 铁律2：价格与流动性
    # ============================================================
    def _rule2_liquidity(self, row) -> bool:
        price = float(row.get("close", 0) or 0)
        circ_mv = float(row.get("circ_mv", 0) or 0)
        price_ok = price <= MAX_PRICE
        mv_ok = circ_mv <= MAX_CIRC_MV
        if not (price_ok or mv_ok):
            return False
        amount = float(row.get("amount", 0) or 0)
        return amount > 0

    # ============================================================
    # 铁律3：涨停基因
    # ============================================================
    def _rule3_gene(self, hist: pd.DataFrame, row) -> bool:
        if hist.empty:
            return False
        cutoff = datetime.now() - timedelta(days=GENE_LOOKBACK_MONTHS * 30)
        hist_copy = hist.copy()
        hist_copy["date_dt"] = pd.to_datetime(hist_copy["date"])
        recent = hist_copy[hist_copy["date_dt"] >= cutoff]
        if recent.empty:
            return False
        limit_ups = recent[recent["pct_chg"] >= 9.8]
        return len(limit_ups) >= GENE_MIN_LIMIT_UPS

    # ============================================================
    # 铁律4：量能验证
    # ============================================================
    def _rule4_volume(self, hist: pd.DataFrame, row) -> bool:
        if hist.empty:
            return False
        today_vol = float(row.get("amount", 0) or 0)
        if today_vol <= 0 and len(hist) >= 1:
            today_vol = float(hist.iloc[-1].get("amount", 0) or 0)
        if len(hist) < VOL_LOOKBACK_DAYS + 1:
            return False
        prev_avg = hist["amount"].astype(float).iloc[-(VOL_LOOKBACK_DAYS+1):-1].mean()
        if prev_avg <= 0:
            return False
        return today_vol >= prev_avg * (1 + VOL_MIN_AMPLIFY)

    # ============================================================
    # 铁律5：趋势斜率
    # ============================================================
    def _rule5_trend(self, hist: pd.DataFrame, row) -> bool:
        if len(hist) < 30:
            return False
        closes = hist["close"].astype(float).values
        ma5 = pd.Series(closes).rolling(5).mean().dropna().values
        if len(ma5) < 5:
            return False
        slope_pct = (ma5[-1] - ma5[-5]) / ma5[-5] * 100
        daily_slope = slope_pct / 5
        if daily_slope >= 1.0:
            return True
        current_price = closes[-1]
        for ma_len in LONG_TERM_MAS:
            if len(closes) >= ma_len:
                ma_val = np.mean(closes[-ma_len:])
                if abs(current_price - ma_val) / ma_val < 0.03:
                    pct = float(row.get("pct_chg", 0) or 0)
                    if pct >= 9.8:
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
        return resistance <= MAX_CHIP_RESISTANCE

    # ============================================================
    # 铁律7：封板质量
    # ============================================================
    def _rule7_seal_quality(self, row) -> bool:
        seal_time = str(row.get("seal_time", "") or row.get("first_seal_time", ""))
        t = _parse_time(seal_time)
        if not t:
            return False
        # 开盘09:30，1小时内 = 10:30前封板
        if t.hour < 9 or (t.hour == 9 and t.minute < 30):
            return False  # 异常时间
        deadline = t.replace(hour=10, minute=30, second=0)
        if t > deadline:
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
        recent = hist.tail(RISK_LOOKBACK_DAYS + 1)
        if len(recent) >= 2:
            for _, r in recent.iterrows():
                high = float(r.get("high", 0) or 0)
                low = float(r.get("low", 0) or 0)
                close = float(r.get("close", 0) or 0)
                open_ = float(r.get("open", 0) or 0)
                if open_ > 0 and close > 0:
                    intraday_range = (high - low) / open_
                    if intraday_range > 0.18:
                        return False
                    if high > 0 and (high - close) / high > abs(CRASH_THRESHOLD):
                        pct = float(r.get("pct_chg", 0) or 0)
                        if pct < 5:
                            return False
        return True
