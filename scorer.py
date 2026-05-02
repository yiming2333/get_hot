"""
五维共振评分引擎
D1: 涨停板溢价    D2: 主力资金共振
D3: 全网消息催化  D4: 龙头地位确认
D5: 量价健康度
"""
import pandas as pd
import numpy as np
from datetime import datetime
from config import WEIGHTS, OUTPUT_TOP_N
from data_fetcher import get_stock_history
import warnings
warnings.filterwarnings("ignore")


def _parse_time(t_str: str):
    """解析时间字符串，支持 092500 和 09:25:00 两种格式"""
    t_str = str(t_str).strip()
    if not t_str:
        return None
    if len(t_str) == 6 and t_str.isdigit():
        try:
            return datetime.strptime(t_str, "%H%M%S")
        except:
            pass
    for fmt in ["%H:%M:%S", "%H:%M"]:
        try:
            return datetime.strptime(t_str, fmt)
        except:
            continue
    return None


class FiveDimScorer:
    """五维共振评分器"""

    def __init__(self, candidates: pd.DataFrame, date_str: str,
                 sector_flow: pd.DataFrame = None,
                 fund_flow: pd.DataFrame = None,
                 history_cache: dict = None):
        self.candidates = candidates
        self.date_str = date_str
        self.sector_flow = sector_flow
        self.fund_flow = fund_flow
        self._history_cache = history_cache or {}

    def _get_history(self, code: str) -> pd.DataFrame:
        if code not in self._history_cache:
            self._history_cache[code] = get_stock_history(code, days=120)
        return self._history_cache[code]

    def score_all(self) -> pd.DataFrame:
        """对所有候选标的进行五维评分"""
        if self.candidates.empty:
            return pd.DataFrame()

        results = []
        total = len(self.candidates)

        for idx, row in self.candidates.iterrows():
            code = row.get("code", "")
            name = row.get("name", "")
            print(f"  评分 [{idx+1}/{total}] {code} {name} ...", end="")

            hist = self._get_history(code)

            scores = {
                "d1_limit_premium": self._score_limit_premium(row, hist),
                "d2_capital": self._score_capital_resonance(row, code),
                "d3_news": self._score_news_catalyst(row, code),
                "d4_leader": self._score_leader_status(row, hist),
                "d5_vol_health": self._score_vol_health(row, hist),
            }

            total_score = sum(
                scores[k] * WEIGHTS[{
                    "d1_limit_premium": "limit_up_premium",
                    "d2_capital": "capital_resonance",
                    "d3_news": "news_catalyst",
                    "d4_leader": "leader_status",
                    "d5_vol_health": "vol_health",
                }[k]] for k in scores
            )

            entry = row.to_dict()
            entry.update(scores)
            entry["total_score"] = round(total_score, 2)
            entry["buy_point"], entry["sell_point"], entry["timing"] = self._calc_points(row, hist)
            results.append(entry)
            print(f" → {total_score:.1f}分")

        df = pd.DataFrame(results).sort_values("total_score", ascending=False)
        return df.head(OUTPUT_TOP_N).reset_index(drop=True)

    # ============================================================
    # D1: 涨停板溢价（0-100）
    # ============================================================
    def _score_limit_premium(self, row, hist: pd.DataFrame) -> float:
        score = 50.0
        ban_count = int(row.get("ban_count", 1) or 1)
        if ban_count >= 3:
            score += 25
        elif ban_count >= 2:
            score += 15
        else:
            score += 5

        seal_time = str(row.get("seal_time", "") or row.get("first_seal_time", ""))
        t = _parse_time(seal_time)
        if t:
            minutes_from_open = (t.hour - 9) * 60 + t.minute - 30
            if minutes_from_open <= 5:
                score += 20
            elif minutes_from_open <= 15:
                score += 15
            elif minutes_from_open <= 30:
                score += 10
            else:
                score += 5
        return min(100.0, score)

    # ============================================================
    # D2: 主力资金共振（0-100）
    # ============================================================
    def _score_capital_resonance(self, row, code: str) -> float:
        score = 40.0
        turnover = float(row.get("turnover", 0) or 0)
        if 5 <= turnover <= 15:
            score += 20
        elif 3 <= turnover <= 20:
            score += 10

        amount = float(row.get("amount", 0) or 0)
        if amount > 20e8:
            score += 25
        elif amount > 10e8:
            score += 20
        elif amount > 5e8:
            score += 15
        elif amount > 2e8:
            score += 10

        if self.fund_flow is not None and not self.fund_flow.empty:
            try:
                flow_row = self.fund_flow[self.fund_flow["代码"].astype(str) == code]
                if not flow_row.empty:
                    net_inflow = float(flow_row.iloc[0].get("主力净流入-净额", 0) or 0)
                    if net_inflow > 0:
                        score += 15
                    if net_inflow > 1e8:
                        score += 10
            except:
                pass
        return min(100.0, score)

    # ============================================================
    # D3: 全网消息催化（0-100）
    # ============================================================
    def _score_news_catalyst(self, row, code: str) -> float:
        score = 50.0
        industry = str(row.get("industry", ""))
        if self.sector_flow is not None and not self.sector_flow.empty:
            try:
                for col in self.sector_flow.columns:
                    if "名称" in col or "板块" in col:
                        match = self.sector_flow[
                            self.sector_flow[col].astype(str).str.contains(
                                industry[:2], na=False
                            )
                        ]
                        if not match.empty:
                            score += 20
                            break
            except:
                pass
        ban_count = int(row.get("ban_count", 1) or 1)
        if ban_count >= 3:
            score += 25
        elif ban_count >= 2:
            score += 15
        return min(100.0, score)

    # ============================================================
    # D4: 龙头地位确认（0-100）
    # ============================================================
    def _score_leader_status(self, row, hist: pd.DataFrame) -> float:
        score = 30.0
        ban_count = int(row.get("ban_count", 1) or 1)
        if ban_count >= 4:
            score += 35
        elif ban_count >= 3:
            score += 25
        elif ban_count >= 2:
            score += 15

        if not hist.empty:
            recent_12m = hist.tail(250)
            limit_ups = len(recent_12m[recent_12m["pct_chg"] >= 9.8])
            density = limit_ups / max(len(recent_12m) / 20, 1)
            if density >= 2:
                score += 20
            elif density >= 1:
                score += 10
        score += 15
        return min(100.0, score)

    # ============================================================
    # D5: 量价健康度（0-100）
    # ============================================================
    def _score_vol_health(self, row, hist: pd.DataFrame) -> float:
        score = 40.0
        if hist.empty or len(hist) < 10:
            return score

        closes = hist["close"].astype(float).values
        volumes = hist["volume"].astype(float).values

        if len(volumes) >= 6:
            vol_ratio = volumes[-1] / np.mean(volumes[-6:-1])
            if 1.3 <= vol_ratio <= 3.0:
                score += 25
            elif 3.0 < vol_ratio <= 5.0:
                score += 15
            elif vol_ratio > 5.0:
                score += 5

        if len(closes) >= 60:
            high_60 = np.max(closes[-60:])
            low_60 = np.min(closes[-60:])
            position = (closes[-1] - low_60) / (high_60 - low_60 + 1e-9)
            if 0.5 <= position <= 0.85:
                score += 20
            elif 0.3 <= position < 0.5:
                score += 15
            elif position > 0.85:
                score += 5

        if len(closes) >= 20:
            ma5 = np.mean(closes[-5:])
            ma10 = np.mean(closes[-10:])
            ma20 = np.mean(closes[-20:])
            if ma5 > ma10 > ma20:
                score += 15
        return min(100.0, score)

    # ============================================================
    # 买卖点位计算
    # ============================================================
    def _calc_points(self, row, hist: pd.DataFrame) -> tuple:
        close = float(row.get("close", 0) or 0)
        ban_count = int(row.get("ban_count", 1) or 1)
        if close <= 0:
            return ("—", "—", "—")

        if ban_count >= 2:
            buy = f"集合竞价排板 {close:.2f}（竞价抢筹）"
            timing = "09:15-09:25 集合竞价"
        else:
            buy_low = round(close * 0.97, 2)
            buy = f"竞价区间 {buy_low:.2f}-{close:.2f}"
            timing = "09:15-09:25 竞价观察 / 盘中回踩5日线低吸"

        if ban_count >= 3:
            sell_target = round(close * 1.15, 2)
            sell = f"连板持有至断板出，目标 {sell_target:.2f}（+15%）"
        elif ban_count >= 2:
            sell_target = round(close * 1.10, 2)
            sell_stop = round(close * 0.95, 2)
            sell = f"目标 {sell_target:.2f}（+10%），止损 {sell_stop:.2f}（-5%）"
        else:
            sell_target = round(close * 1.07, 2)
            sell_stop = round(close * 0.95, 2)
            sell = f"目标 {sell_target:.2f}（+7%），止损 {sell_stop:.2f}（-5%）"

        return (buy, sell, timing)
