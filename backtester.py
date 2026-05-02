"""
简易回测引擎 - 验证策略历史胜率
用法: python3 backtester.py 20260101 20260430
"""
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
from typing import Dict, List, Optional

from data_fetcher import batch_get_history
from utils import safe_float, safe_int

logger = logging.getLogger("backtest")


class SimpleBacktester:
    """
    简易回测器：
    对历史涨停股运行筛选规则，追踪次日/N日收益
    """

    def __init__(self, hold_days: int = 3, stop_loss: float = -0.05,
                 take_profit: float = 0.10):
        self.hold_days = hold_days
        self.stop_loss = stop_loss
        self.take_profit = take_profit

    def run(self, signals: List[Dict], history_cache: Dict[str, pd.DataFrame],
            date_str: str) -> Dict:
        """
        对一组信号进行回测
        signals: [{"code": "000001", "name": "xx", "close": 10.0, ...}, ...]
        """
        if not signals:
            return self._empty_result(date_str, date_str)

        results = []
        for sig in signals:
            code = sig.get("code", "")
            buy_price = safe_float(sig.get("close"))
            if buy_price <= 0 or code not in history_cache:
                continue

            hist = history_cache[code]
            if hist.empty:
                continue

            # 找到买入日之后的K线
            hist_copy = hist.copy()
            hist_copy["date_dt"] = pd.to_datetime(hist_copy["date"])
            buy_date = pd.to_datetime(date_str)
            future = hist_copy[hist_copy["date_dt"] > buy_date].head(self.hold_days)

            if future.empty:
                continue

            # 模拟持仓
            sell_price = buy_price
            sell_reason = "持有到期"
            for _, day in future.iterrows():
                day_close = safe_float(day.get("close"))
                day_low = safe_float(day.get("low"))
                day_high = safe_float(day.get("high"))

                # 盘中触及止损
                if day_low > 0:
                    drawdown = (day_low - buy_price) / buy_price
                    if drawdown <= self.stop_loss:
                        sell_price = buy_price * (1 + self.stop_loss)
                        sell_reason = "止损"
                        break

                # 盘中触及止盈
                if day_high > 0:
                    gain = (day_high - buy_price) / buy_price
                    if gain >= self.take_profit:
                        sell_price = buy_price * (1 + self.take_profit)
                        sell_reason = "止盈"
                        break

                sell_price = day_close

            ret = (sell_price - buy_price) / buy_price
            results.append({
                "code": code,
                "name": sig.get("name", ""),
                "buy_price": buy_price,
                "sell_price": round(sell_price, 2),
                "return": round(ret, 4),
                "sell_reason": sell_reason,
            })

        return self._calc_stats(results, date_str, date_str)

    def _calc_stats(self, results: List[Dict], start: str, end: str) -> Dict:
        if not results:
            return self._empty_result(start, end)

        returns = [r["return"] for r in results]
        wins = [r for r in results if r["return"] > 0]
        losses = [r for r in results if r["return"] <= 0]

        avg_win = np.mean([r["return"] for r in wins]) if wins else 0
        avg_loss = abs(np.mean([r["return"] for r in losses])) if losses else 0.01

        return {
            "start_date": start,
            "end_date": end,
            "trading_days": 0,
            "total_signals": len(results),
            "win_count": len(wins),
            "loss_count": len(losses),
            "win_rate": len(wins) / len(results) if results else 0,
            "avg_return": np.mean(returns),
            "max_win": max(returns) if returns else 0,
            "max_loss": min(returns) if returns else 0,
            "profit_loss_ratio": avg_win / avg_loss if avg_loss > 0 else float("inf"),
            "details": results,
        }

    def _empty_result(self, start: str, end: str) -> Dict:
        return {
            "start_date": start,
            "end_date": end,
            "trading_days": 0,
            "total_signals": 0,
            "win_rate": 0,
            "avg_return": 0,
            "max_win": 0,
            "max_loss": 0,
            "profit_loss_ratio": 0,
            "details": [],
        }


def run_backtest(start_date: str, end_date: str, hold_days: int = 3):
    """便捷入口：回测指定区间"""
    from config import CFG

    bt = SimpleBacktester(
        hold_days=hold_days,
        stop_loss=CFG.iron.crash_threshold,
        take_profit=0.10
    )

    # 简化版：获取区间内所有交易日的涨停数据并回测
    # 实际使用时应配合 main.py 的完整筛选流程
    logger.info(f"回测区间: {start_date} ~ {end_date}, 持仓天数: {hold_days}")
    print(f"📊 回测区间: {start_date} ~ {end_date}")
    print(f"   持仓天数: {hold_days}  止损: {bt.stop_loss:.0%}  止盈: {bt.take_profit:.0%}")
    print()

    # 生成日期序列（简化：只取月末交易日）
    from data_fetcher import get_limit_up_stocks
    current = datetime.strptime(start_date, "%Y%m%d")
    end_dt = datetime.strptime(end_date, "%Y%m%d")
    all_results = []

    while current <= end_dt:
        date_str = current.strftime("%Y%m%d")
        # 跳过周末
        if current.weekday() < 5:
            print(f"  📅 {date_str} ...", end="")
            pool = get_limit_up_stocks(date_str)
            if not pool.empty:
                codes = pool["code"].tolist()
                hist = batch_get_history(codes, days=30, date_str=date_str)
                signals = pool.to_dict("records")
                result = bt.run(signals, hist, date_str)
                if result["total_signals"] > 0:
                    all_results.append(result)
                    print(f" {result['total_signals']}信号, "
                          f"胜率{result['win_rate']:.0%}, "
                          f"均收{result['avg_return']:.2%}")
                else:
                    print(" 无信号")
            else:
                print(" 非交易日")
        current += timedelta(days=1)

    # 汇总
    if all_results:
        total_sigs = sum(r["total_signals"] for r in all_results)
        total_wins = sum(r["win_count"] for r in all_results)
        all_returns = []
        for r in all_results:
            all_returns.extend([d["return"] for d in r.get("details", [])])

        print(f"\n{'='*60}")
        print(f"  📊 回测汇总")
        print(f"{'='*60}")
        print(f"  交易日数:   {len(all_results)}")
        print(f"  总信号数:   {total_sigs}")
        print(f"  总胜率:     {total_wins/total_sigs:.1%}" if total_sigs > 0 else "  总胜率: N/A")
        if all_returns:
            print(f"  平均收益:   {np.mean(all_returns):.2%}")
            print(f"  最大盈利:   {max(all_returns):.2%}")
            print(f"  最大亏损:   {min(all_returns):.2%}")
        print(f"{'='*60}")
    else:
        print("\n⚠️  回测区间内无有效信号")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python3 backtester.py <起始日期> <结束日期> [持仓天数]")
        print("示例: python3 backtester.py 20260101 20260430 3")
        sys.exit(1)

    start = sys.argv[1]
    end = sys.argv[2]
    hold = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    logging.basicConfig(level=logging.INFO)
    run_backtest(start, end, hold)
