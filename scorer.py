"""
五维共振评分引擎
D1: 涨停板溢价    D2: 主力资金共振
D3: 全网消息催化  D4: 龙头地位确认
D5: 量价健康度
"""
import pandas as pd
import numpy as np
from datetime import datetime
import logging
from typing import Dict, Tuple

from config import CFG, WEIGHTS, OUTPUT_TOP_N
from data_fetcher import get_stock_history
from utils import parse_time, safe_float, safe_int

logger = logging.getLogger("scorer")


class FiveDimScorer:
    """五维共振评分器"""

    def __init__(self, candidates: pd.DataFrame, date_str: str,
                 sector_flow: pd.DataFrame = None,
                 fund_flow: pd.DataFrame = None,
                 dragon_tiger: pd.DataFrame = None,
                 dragon_tiger_inst: pd.DataFrame = None,
                 northbound: pd.DataFrame = None,
                 history_cache: dict = None):
        self.candidates = candidates
        self.date_str = date_str
        self.sector_flow = sector_flow
        self.fund_flow = fund_flow
        self.dragon_tiger = dragon_tiger
        self.dragon_tiger_inst = dragon_tiger_inst
        self.northbound = northbound
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

            weight_map = {
                "d1_limit_premium": "limit_up_premium",
                "d2_capital": "capital_resonance",
                "d3_news": "news_catalyst",
                "d4_leader": "leader_status",
                "d5_vol_health": "vol_health",
            }
            total_score = sum(scores[k] * WEIGHTS[weight_map[k]] for k in scores)

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
        ban_count = safe_int(row.get("ban_count"), 1)
        if ban_count >= 3:
            score += 25
        elif ban_count >= 2:
            score += 15
        else:
            score += 5

        seal_time = str(row.get("seal_time", "") or row.get("first_seal_time", ""))
        t = parse_time(seal_time)
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
        score = 30.0  # 基础分降低，给新数据源腾空间
        turnover = safe_float(row.get("turnover"))
        if 5 <= turnover <= 15:
            score += 10
        elif 3 <= turnover <= 20:
            score += 5

        amount = safe_float(row.get("amount"))
        if amount > 20e8:
            score += 10
        elif amount > 10e8:
            score += 8
        elif amount > 5e8:
            score += 5
        elif amount > 2e8:
            score += 3

        # --- 个股资金流 ---
        if self.fund_flow is not None and not self.fund_flow.empty:
            try:
                code_col = "代码" if "代码" in self.fund_flow.columns else "code"
                flow_row = self.fund_flow[self.fund_flow[code_col].astype(str) == code]
                if not flow_row.empty:
                    net_col = "main_net_inflow" if "main_net_inflow" in flow_row.columns else "主力净流入-净额"
                    net_inflow = safe_float(flow_row.iloc[0].get(net_col))
                    if net_inflow > 0:
                        score += 8
                    if net_inflow > 1e8:
                        score += 5
            except Exception as e:
                logger.debug(f"资金流匹配失败 {code}: {e}")

        # --- 龙虎榜：机构净买入 ---
        if self.dragon_tiger_inst is not None and not self.dragon_tiger_inst.empty:
            try:
                lhb_row = self.dragon_tiger_inst[
                    self.dragon_tiger_inst["code"].astype(str) == code
                ]
                if not lhb_row.empty:
                    inst_net = safe_float(lhb_row.iloc[0].get("inst_net_buy"))
                    buy_count = safe_int(lhb_row.iloc[0].get("buy_inst_count"))
                    sell_count = safe_int(lhb_row.iloc[0].get("sell_inst_count"))
                    if inst_net > 0:
                        score += 10  # 机构净买入
                    if inst_net > 5e8:
                        score += 5   # 大额机构买入
                    if buy_count > sell_count:
                        score += 5   # 买方机构多于卖方
                    logger.debug(f"{code} 龙虎榜机构: 净买={inst_net/1e8:.1f}亿 买方{buy_count}家")
            except Exception as e:
                logger.debug(f"龙虎榜机构匹配失败 {code}: {e}")

        # --- 龙虎榜：游资席位净买入 ---
        if self.dragon_tiger is not None and not self.dragon_tiger.empty:
            try:
                lhb_row = self.dragon_tiger[
                    self.dragon_tiger["code"].astype(str) == code
                ]
                if not lhb_row.empty:
                    lhb_net = safe_float(lhb_row.iloc[0].get("lhb_net_buy"))
                    lhb_pct = safe_float(lhb_row.iloc[0].get("lhb_net_pct"))
                    if lhb_net > 0:
                        score += 5
                    if lhb_pct > 5:
                        score += 3  # 净买额占成交比>5%
            except Exception as e:
                logger.debug(f"龙虎榜匹配失败 {code}: {e}")

        # --- 北向资金增持 ---
        if self.northbound is not None and not self.northbound.empty:
            try:
                nb_row = self.northbound[
                    self.northbound["code"].astype(str) == code
                ]
                if not nb_row.empty:
                    hold_pct = safe_float(nb_row.iloc[0].get("nb_hold_circ_pct"))
                    add_mv = safe_float(nb_row.iloc[0].get("nb_add_mv"))
                    add_pct = safe_float(nb_row.iloc[0].get("nb_add_mv_pct"))
                    if hold_pct > 3:
                        score += 5   # 北向重仓股（>3%流通股）
                    if hold_pct > 5:
                        score += 3   # 北向高度控盘
                    if add_mv > 0 and add_pct > 10:
                        score += 5   # 北向大幅增持（市值增幅>10%）
                    logger.debug(f"{code} 北向: 持仓{hold_pct}% 增持{add_pct}%")
            except Exception as e:
                logger.debug(f"北向资金匹配失败 {code}: {e}")

        return min(100.0, score)

    # ============================================================
    # D3: 全网消息催化（0-100）
    # ============================================================
    def _score_news_catalyst(self, row, code: str) -> float:
        score = 40.0  # 基础分降低，给龙虎榜解读腾空间
        industry = str(row.get("industry", ""))
        if self.sector_flow is not None and not self.sector_flow.empty and industry:
            try:
                for col in self.sector_flow.columns:
                    if "名称" in col or "板块" in col:
                        match = self.sector_flow[
                            self.sector_flow[col].astype(str).str.contains(
                                industry[:2], na=False
                            )
                        ]
                        if not match.empty:
                            score += 15
                            break
            except Exception:
                pass
        ban_count = safe_int(row.get("ban_count"), 1)
        if ban_count >= 3:
            score += 15
        elif ban_count >= 2:
            score += 8

        # --- 龙虎榜解读（人工/机构评价） ---
        if self.dragon_tiger is not None and not self.dragon_tiger.empty:
            try:
                lhb_row = self.dragon_tiger[
                    self.dragon_tiger["code"].astype(str) == code
                ]
                if not lhb_row.empty:
                    comment = str(lhb_row.iloc[0].get("lhb_comment", ""))
                    reason = str(lhb_row.iloc[0].get("lhb_reason", ""))
                    # 机构买入信号
                    if "机构" in comment and "买入" in comment:
                        score += 15
                    elif "机构" in comment and "卖出" in comment:
                        score -= 5
                    # 知名游资
                    if any(kw in comment for kw in ["知名游资", "章盟主", "赵老哥", "作手新一", "溧阳路"]):
                        score += 10
                    # 涨停上榜（正面催化）
                    if "涨幅" in reason or "涨停" in reason:
                        score += 8
                    # 跌停/跌幅上榜（负面催化）
                    if "跌幅" in reason or "跌停" in reason:
                        score -= 10
                    logger.debug(f"{code} 龙虎榜: {comment[:30]}")
            except Exception as e:
                logger.debug(f"龙虎榜解读匹配失败 {code}: {e}")

        # --- 北向资金动向（外资风向标） ---
        if self.northbound is not None and not self.northbound.empty:
            try:
                nb_row = self.northbound[
                    self.northbound["code"].astype(str) == code
                ]
                if not nb_row.empty:
                    add_pct = safe_float(nb_row.iloc[0].get("nb_add_mv_pct"))
                    if add_pct > 20:
                        score += 10  # 外资大幅加仓，强信号
                    elif add_pct > 10:
                        score += 5
                    elif add_pct < -10:
                        score -= 5  # 外资减仓
            except Exception:
                pass

        return min(100.0, max(0.0, score))

    # ============================================================
    # D4: 龙头地位确认（0-100）
    # ============================================================
    def _score_leader_status(self, row, hist: pd.DataFrame) -> float:
        score = 30.0
        ban_count = safe_int(row.get("ban_count"), 1)
        if ban_count >= 4:
            score += 35
        elif ban_count >= 3:
            score += 25
        elif ban_count >= 2:
            score += 15

        if not hist.empty:
            recent_12m = hist.tail(250)
            # 自适应涨停阈值
            max_pct = recent_12m["pct_chg"].astype(float).max()
            threshold = 19.5 if max_pct > 15 else 9.5
            limit_ups = len(recent_12m[recent_12m["pct_chg"].astype(float) >= threshold])
            density = limit_ups / max(len(recent_12m) / 20, 1)
            if density >= 2:
                score += 20
            elif density >= 1:
                score += 10
        score += 15  # 基础分（已通过铁律筛选）
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

        # 量比
        if len(volumes) >= 6:
            vol_ratio = volumes[-1] / (np.mean(volumes[-6:-1]) + 1e-9)
            if 1.3 <= vol_ratio <= 3.0:
                score += 25
            elif 3.0 < vol_ratio <= 5.0:
                score += 15
            elif vol_ratio > 5.0:
                score += 5

        # 相对位置
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

        # 均线多头排列
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
    def _calc_points(self, row, hist: pd.DataFrame) -> Tuple[str, str, str]:
        close = safe_float(row.get("close"))
        ban_count = safe_int(row.get("ban_count"), 1)
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
