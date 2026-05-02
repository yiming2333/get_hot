#!/usr/bin/env python3
"""
徐翔五维共振 · 涨停板量化筛选系统 v2.0
用法:
  python3 main.py                   # 默认当天（收盘后运行）
  python3 main.py 20260430          # 指定日期
  python3 main.py --backtest 20260101 20260430  # 回测模式
"""
import sys
import argparse
import logging
from datetime import datetime

from config import CFG, LOG_LEVEL, LOG_FORMAT
from data_fetcher import (
    get_limit_up_stocks, get_sector_flow,
    get_individual_fund_flow, batch_get_history,
    get_dragon_tiger_list, get_dragon_tiger_institution,
    get_northbound_flow
)
from filters import IronFilter
from scorer import FiveDimScorer
from presenter import (
    print_banner, print_stage,
    print_filter_summary, print_results,
    print_backtest_summary
)

# 配置日志
logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger("main")


def parse_args():
    parser = argparse.ArgumentParser(description="徐翔五维共振 · 涨停板量化筛选系统")
    parser.add_argument("date", nargs="?", default=datetime.now().strftime("%Y%m%d"),
                        help="交易日 YYYYMMDD（默认今天）")
    parser.add_argument("--backtest", nargs=2, metavar=("START", "END"),
                        help="回测模式：起止日期")
    parser.add_argument("--hold-days", type=int, default=3,
                        help="回测持仓天数（默认3）")
    parser.add_argument("--top", type=int, default=None,
                        help="输出Top N标的（覆盖配置）")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="详细日志")
    return parser.parse_args()


def run_screen(date_str: str):
    """主筛选流程"""
    print_banner()
    print(f"📅 交易日: {date_str[:4]}-{date_str[4:6]}-{date_str[6:]}")
    print(f"⏰ 运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # ============================================================
    # 第一阶段：数据采集
    # ============================================================
    print_stage("第一阶段: 数据采集")

    print("  [1/3] 获取涨停股池...", end="", flush=True)
    limit_up_df = get_limit_up_stocks(date_str)
    if limit_up_df.empty:
        print(" ❌ 无数据")
        print("\n⚠️  未获取到涨停数据。可能原因:")
        print("  1. 非交易日（周末/节假日）")
        print("  2. 盘中运行时尚未收盘，数据未更新")
        print("  3. 网络连接问题")
        print(f"\n请在收盘后重试，或指定交易日: python3 main.py 20260430")
        return
    print(f" ✅ {len(limit_up_df)}只涨停股")

    print("  [2/3] 获取板块资金流...", end="", flush=True)
    sector_flow = get_sector_flow()
    if sector_flow is not None and not sector_flow.empty:
        print(f" ✅ {len(sector_flow)}个板块")
    else:
        print(" ⚠️ 跳过（不影响核心筛选）")

    print("  [3/5] 获取个股资金流...", end="", flush=True)
    fund_flow = get_individual_fund_flow()
    if fund_flow is not None and not fund_flow.empty:
        print(f" ✅ {len(fund_flow)}只个股")
    else:
        print(" ⚠️ 跳过")

    print("  [4/5] 获取龙虎榜...", end="", flush=True)
    dragon_tiger = get_dragon_tiger_list(date_str)
    dragon_tiger_inst = get_dragon_tiger_institution(date_str)
    if dragon_tiger is not None and not dragon_tiger.empty:
        print(f" ✅ {len(dragon_tiger)}条上榜记录")
    else:
        print(" ⚠️ 跳过（当日无龙虎榜数据）")

    print("  [5/5] 获取北向资金...", end="", flush=True)
    northbound = get_northbound_flow()
    if northbound is not None and not northbound.empty:
        print(f" ✅ {len(northbound)}只北向持股")
    else:
        print(" ⚠️ 跳过")

    # 涨停池概览
    print(f"\n📋 当日涨停池概览:")
    from utils import safe_float, safe_int
    for _, r in limit_up_df.head(20).iterrows():
        amt = safe_float(r.get("amount")) / 1e8
        print(f"    {r.get('code','')} {r.get('name',''):　<6} "
              f"收盘{safe_float(r.get('close')):.2f} "
              f"{safe_int(r.get('ban_count'), 1)}板 "
              f"额{amt:.1f}亿")

    # 预加载历史数据
    print(f"\n  正在批量拉取 {len(limit_up_df)} 只涨停股历史数据（约需1-2分钟）...")
    codes = limit_up_df["code"].tolist()
    history_cache = batch_get_history(codes, days=250, date_str=date_str)
    print(f"  ✅ 成功获取 {len(history_cache)}/{len(codes)} 只")

    # ============================================================
    # 第二阶段：铁律筛选
    # ============================================================
    print_stage("第二阶段: 八条铁律筛选")

    iron = IronFilter(date_str, limit_up_df, history_cache=history_cache)
    candidates = iron.run_all()

    print_filter_summary(len(limit_up_df), len(candidates))

    if candidates.empty:
        print("\n⚠️  无标的通过全部铁律。")
        print("  徐翔铁则: 宁可错过，不可做错。空仓也是一种操作。")
        return

    # ============================================================
    # 第三阶段：五维评分
    # ============================================================
    print_stage("第三阶段: 五维共振评分")

    scorer = FiveDimScorer(
        candidates, date_str,
        sector_flow=sector_flow,
        fund_flow=fund_flow,
        dragon_tiger=dragon_tiger,
        dragon_tiger_inst=dragon_tiger_inst,
        northbound=northbound,
        history_cache=history_cache
    )
    results = scorer.score_all()

    # ============================================================
    # 输出结果
    # ============================================================
    print_results(results)


def main():
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.top:
        from config import OUTPUT_TOP_N
        import config
        config.OUTPUT_TOP_N = args.top

    if args.backtest:
        from backtester import run_backtest
        run_backtest(args.backtest[0], args.backtest[1], args.hold_days)
    else:
        run_screen(args.date)


if __name__ == "__main__":
    main()
