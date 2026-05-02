#!/usr/bin/env python3
"""
徐翔五维共振 · 涨停板量化筛选系统
用法: python3 main.py [YYYYMMDD]
不传日期默认使用当天
"""
import sys
from datetime import datetime
from data_fetcher import (
    get_limit_up_stocks, get_sector_flow,
    get_individual_fund_flow, batch_get_history
)
from filters import IronFilter
from scorer import FiveDimScorer
from presenter import (
    print_banner, print_stage,
    print_filter_summary, print_results
)


def main():
    if len(sys.argv) > 1:
        date_str = sys.argv[1]
    else:
        date_str = datetime.now().strftime("%Y%m%d")

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

    print("  [3/3] 获取个股资金流...", end="", flush=True)
    fund_flow = get_individual_fund_flow()
    if fund_flow is not None and not fund_flow.empty:
        print(f" ✅ {len(fund_flow)}只个股")
    else:
        print(" ⚠️ 跳过（不影响核心筛选）")

    # 涨停池概览
    print(f"\n📋 当日涨停池概览:")
    for _, r in limit_up_df.head(20).iterrows():
        amt = float(r.get("amount", 0) or 0) / 1e8
        print(f"    {r.get('code','')} {r.get('name',''):　<6} "
              f"收盘{float(r.get('close',0) or 0):.2f} "
              f"{int(r.get('ban_count',1) or 1)}板 "
              f"额{amt:.1f}亿")

    # 预加载历史数据（一次性批量拉取，避免在筛选阶段逐个请求）
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
        history_cache=history_cache
    )
    results = scorer.score_all()

    # ============================================================
    # 输出结果
    # ============================================================
    print_results(results)


if __name__ == "__main__":
    main()
