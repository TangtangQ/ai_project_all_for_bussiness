"""
market_heat.py  — 修复/加固版

主要修复点：
- 统一处理指数/股票代码格式（去后缀、尝试 sh/sz 前缀）
- fetch_stock_daily 增加重试、延迟、列名兼容、返回 None（失败不抛）
- 上层持仓循环对 None 做跳过处理，避免 'NoneType' 错误
- fetch_daily_index 更稳健地尝试主/备用接口
- score 函数对 None 输入返回中性值
- 增加日志/提示，方便排查网络/接口问题
"""

import os
import time
import datetime as dt
import warnings
import pandas as pd
import numpy as np

warnings.filterwarnings('ignore')

# ---------- 配置区 ----------
USER_HOLDINGS = [
    "300502.SZ",  # 新易盛
    "300308.SZ",  # 中际旭创
    "603063.SH",  # 禾望电气
    "002463.SZ",  # 沪电股份
    "603606.SH",  # 东方电缆
    "002487.SZ",  # 大金重工
    "300395.SZ",  # 菲利华
]

CSI500_CODE = '000905.SH'   # 支持 '000905.SH' / '000905' / 'sh000905' 等
OUT_DIR = os.path.abspath('./market_heat_output')
os.makedirs(OUT_DIR, exist_ok=True)

BOLL_WINDOW = 20
BOLL_N = 2

# 权重（总和=1）
WEIGHT_LIQUIDITY = 0.35
WEIGHT_VALUATION = 0.35
WEIGHT_TECHNICAL = 0.30

# ---------- 辅助工具 ----------
def safe_import_akshare():
    try:
        import akshare as ak
        return ak
    except Exception as e:
        print("错误：未能导入 akshare。请先运行：pip install akshare")
        raise

def bollinger_bands(df_close, window=20, n=2):
    ma = df_close.rolling(window).mean()
    sd = df_close.rolling(window).std()
    upper = ma + n * sd
    lower = ma - n * sd
    res = df_close.to_frame(name='close')
    res['mid'] = ma
    res['upper'] = upper
    res['lower'] = lower
    return res

# ---------- 数据获取模块（健壮版） ----------

def _clean_index_symbol(code):
    """清理并生成候选的指数 symbol 格式供 akshare 使用"""
    c = str(code).lower().strip()
    # 去掉后缀
    c = c.replace('.sh', '').replace('.sz', '')
    candidates = [c, 'sh'+c, 'sz'+c]
    # 一般中证指数在 akshare 用法是 'sh000905' 或 '000905'
    return candidates

def fetch_daily_index(code):
    """
    获取指数日线（返回 DataFrame 含 'close' 列，索引为 date）
    尝试多种 symbol 及备用接口，失败返回 None
    """
    ak = safe_import_akshare()
    import pandas as pd

    candidates = _clean_index_symbol(code)
    last_exc = None
    for sym in candidates:
        try:
            # ak.stock_zh_index_daily 常用
            df = ak.stock_zh_index_daily(symbol=sym)
            if isinstance(df, pd.DataFrame) and not df.empty:
                # 有些 akshare 返回 index 为 trade_date，或有 date 列
                df = df.reset_index()
                # 尝试兼容列名
                if 'date' not in df.columns and 'trade_date' in df.columns:
                    df = df.rename(columns={'trade_date': 'date'})
                if 'date' in df.columns:
                    df['date'] = pd.to_datetime(df['date']).dt.date
                    # detect close column names
                    if 'close' not in df.columns and 'close' in df.columns:
                        pass
                    # set and return
                    df = df.set_index('date')
                    if 'close' in df.columns:
                        return df[['close']]
            # else try next candidate
        except Exception as e:
            last_exc = e
            # 不抛，继续尝试备用
            # print(f"尝试 {sym} 失败：{e}")

    # 备用： index_zh_a_hist
    try:
        idx = ak.index_zh_a_hist(symbol='000905')  # 备用尝试固定中证500符号
        if isinstance(idx, pd.DataFrame) and not idx.empty:
            # 兼容列名
            if '日期' in idx.columns and '收盘' in idx.columns:
                idx = idx.rename(columns={'日期': 'date', '收盘': 'close'})
            if 'date' in idx.columns:
                idx['date'] = pd.to_datetime(idx['date']).dt.date
                idx = idx.set_index('date')
                if 'close' in idx.columns:
                    return idx[['close']]
    except Exception as e:
        last_exc = e

    # 如果一切失败
    print("指数日线获取失败（尝试多接口），最后异常：", last_exc)
    return None

def fetch_stock_daily(stock_code, start=None, end=None, retry=2):
    """
    稳健获取个股日线：
    - 去后缀（支持带 .SZ/.SH 或纯代码）
    - 限制默认区间为近 90 天，避免一次性请求太久
    - 重试机制、延迟、列名兼容
    - 失败返回 None（不抛）
    """
    ak = safe_import_akshare()
    import pandas as pd

    # 清理代码：传入可能带 .SZ/.SH 或裸码
    code = str(stock_code).strip()
    code = code.replace('.SZ', '').replace('.SH', '').replace('.sz', '').replace('.sh', '')

    if start is None:
        start = (dt.date.today() - dt.timedelta(days=90)).strftime('%Y-%m-%d')
    if end is None:
        end = dt.date.today().strftime('%Y-%m-%d')

    last_exc = None
    for attempt in range(1, retry+1):
        try:
            time.sleep(0.8)  # 小延迟，避免速率限制
            # ak.share 接口可能接受 start_date/end_date 或 start/end，兼容使用关键字参数可能不同，各版本差异：
            # 大多数 akshare 版本 stock_zh_a_hist 支持 start_date, end_date
            df = ak.stock_zh_a_hist(symbol=code, period='daily', adjust='qfq', start_date=start, end_date=end)
            if df is None or (isinstance(df, pd.DataFrame) and df.empty):
                raise ValueError("接口返回空/None")

            # 兼容列名
            if '日期' in df.columns and '收盘' in df.columns:
                df = df.rename(columns={'日期': 'date', '收盘': 'close'})
            elif 'date' in df.columns and 'close' in df.columns:
                pass
            elif 'trade_date' in df.columns and 'close' in df.columns:
                df = df.rename(columns={'trade_date': 'date'})
            else:
                # 有时 akshare 返回的列名不同，尝试查找近似列
                cols = [c.lower() for c in df.columns]
                if 'close' not in cols and '收盘' in df.columns:
                    df = df.rename(columns={'收盘': 'close'})
                if 'date' not in cols and ('date' in df.columns or '日期' in df.columns or 'trade_date' in df.columns):
                    if '日期' in df.columns:
                        df = df.rename(columns={'日期': 'date'})
                    elif 'trade_date' in df.columns:
                        df = df.rename(columns={'trade_date': 'date'})

            if 'date' not in df.columns or 'close' not in df.columns:
                raise ValueError(f"未识别的列名：{df.columns}")

            df['date'] = pd.to_datetime(df['date']).dt.date
            df = df.set_index('date')
            # 保证数值类型
            df['close'] = pd.to_numeric(df['close'], errors='coerce')
            df = df.dropna(subset=['close'])
            if df.empty:
                raise ValueError("经转换后无有效 close 数据")
            return df[['close']]
        except Exception as e:
            last_exc = e
            print(f"[{code}] 获取尝试 {attempt}/{retry} 失败：{e}")
            time.sleep(0.8)

    print(f"[{code}] 最终获取失败，返回 None，最后异常：{last_exc}")
    return None

# ---------- 评分逻辑 ----------
def map_to_score(value, min_val, max_val):
    """线性映射 value 到 0-100（稳健边界）"""
    try:
        v = float(value)
    except Exception:
        return None
    if max_val == min_val:
        return 50
    score = (v - min_val) / (max_val - min_val) * 100
    score = max(0, min(100, score))
    return score

def score_liquidity(macro_dict, northbound_dict):
    """更专业的流动性评分（见脚注）"""
    scores = []
    m2 = macro_dict.get('m2') if isinstance(macro_dict, dict) else None
    if m2 is not None:
        s = map_to_score(m2, 6, 14)
        if s is not None: scores.append(s)
    sf = macro_dict.get('social_financing') if isinstance(macro_dict, dict) else None
    if sf is not None:
        s = map_to_score(sf, 8, 16)
        if s is not None: scores.append(s)
    nb = northbound_dict.get('net_inflow_5d') if isinstance(northbound_dict, dict) else None
    if nb is not None:
        s = map_to_score(nb, 0, 1000)  # 假设历史最大 1000（单位亿）
        if s is not None: scores.append(s)
    if not scores:
        return 50
    return int(sum(scores)/len(scores))

def score_valuation(val_dict):
    """把估值分位映射为 0-100 的评分（稳健）"""
    pe_pct = val_dict.get('pe_pctile') if isinstance(val_dict, dict) else None
    pb_pct = val_dict.get('pb_pctile') if isinstance(val_dict, dict) else None
    if pe_pct is None and pb_pct is None:
        return 50
    pcts = [v for v in [pe_pct, pb_pct] if v is not None]
    try:
        avg_pct = float(sum(pcts)/len(pcts))
    except Exception:
        return 50
    if avg_pct < 0.5:
        score = 70 + (0.5 - avg_pct)/0.5 * 30
    elif avg_pct < 0.7:
        score = 50 + (0.7 - avg_pct)/0.2 * 20
    else:
        score = max(0, 50 - (avg_pct-0.7)/0.3*50)
    return int(score)

def score_technical(idx_close_df):
    """技术面评分：布林带判断，返回 (score, bb_df)"""
    if idx_close_df is None or idx_close_df.empty:
        return 50, None
    s = idx_close_df['close'].astype(float)
    bb = bollinger_bands(s, window=BOLL_WINDOW, n=BOLL_N)
    last = bb.dropna().tail(5)
    if len(last) >= 2 and (last['close'].iloc[-1] > last['upper'].iloc[-1]) and (last['close'].iloc[-2] > last['upper'].iloc[-2]):
        return 20, bb
    return 60, bb

def fetch_index_valuation(index_code='000905.SH'):
    """
    获取指数估值数据（支持中证500、沪深300、上证50等）
    来源：东方财富网估值中心
    返回：
        {
          'pe_ttm': float,
          'pb': float,
          'pe_pctile': float (0~1),
          'pb_pctile': float (0~1)
        }
    """
    import requests
    import pandas as pd
    from io import StringIO

    # 东方财富指数估值接口（无需登录）
    url = (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get?"
        "fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,"
        "f56,f57,f58,f59,f60,f61&ut=b2884a393a59ad64002292a3e90d46a5"
        f"&secid=1.{index_code[:6]}"  # 1=上证, 0=深证
        "&klt=101&fqt=1&lmt=2000"
    )

    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200 or "data" not in resp.text:
            raise ValueError("指数行情获取失败")

        # 东方财富没有直接提供估值API，只能用历史估值网页接口
        val_url = (
            "https://data.eastmoney.com/api/qt/stock/get"
            f"?fltt=2&invt=2&secid=1.{index_code[:6]}"
            "&fields=f43,f44,f45,f46,f47,f48,f49,f50,f60,f62,f104,f105,f115,f116,f117,f118"
        )
        val_resp = requests.get(val_url, timeout=10)
        js = val_resp.json()
        if "data" not in js or not js["data"]:
            raise ValueError("估值数据缺失")

        data = js["data"]
        pe = float(data.get("f115", 0))  # 动态市盈率
        pb = float(data.get("f117", 0))  # 市净率

        # 使用东方财富估值分位网站接口
        pe_url = f"https://legulegu.com/api/stock-data/pe/{index_code[:6]}"
        pb_url = f"https://legulegu.com/api/stock-data/pb/{index_code[:6]}"
        try:
            pe_pct = requests.get(pe_url, timeout=8).json().get("percentile", None)
            pb_pct = requests.get(pb_url, timeout=8).json().get("percentile", None)
        except Exception:
            pe_pct, pb_pct = None, None

        return {
            "pe_ttm": round(pe, 2) if pe else None,
            "pb": round(pb, 2) if pb else None,
            "pe_pctile": round(pe_pct / 100, 4) if pe_pct else None,
            "pb_pctile": round(pb_pct / 100, 4) if pb_pct else None,
        }

    except Exception as e:
        print(f"[警告] 获取估值失败: {e}")
        return {'pe_ttm': None, 'pb': None, 'pe_pctile': None, 'pb_pctile': None}


# ---------- 主流程 ----------
def analyze_and_report():
    ak = None
    try:
        ak = safe_import_akshare()
    except Exception:
        print("akshare 未导入, 后面的 ak 数据获取将失败（脚本会尽力继续运行）")

    report_lines = []
    now = dt.datetime.now()
    report_lines.append(f"市场温度检测时间：{now.strftime('%Y-%m-%d %H:%M:%S')}")

    # 宏观（占位实现：若 ak 可用尝试获取）
    macro = {'m2': None, 'social_financing': None}
    north = {'net_inflow_5d': None}
    if ak is not None:
        try:
            # 尝试获取 M2（兼容不同 akshare 版本）
            try:
                m2_df = ak.macro_china_money_supply()
                # 找到可能的 M2 同比列
                # 这里做最稳妥的处理：若返回 DataFrame 尝试检索数值列
                if isinstance(m2_df, pd.DataFrame) and not m2_df.empty:
                    # 尝试找包含 'M2' 或 '货币供应量' 的列名
                    for c in m2_df.columns:
                        if 'M2' in str(c) or '货币' in str(c):
                            # 取最后一行的同比或最后值
                            try:
                                val = pd.to_numeric(m2_df[c].iloc[-1], errors='coerce')
                                if not np.isnan(val):
                                    macro['m2'] = float(val)
                                    break
                            except Exception:
                                pass
            except Exception:
                pass

            # 北向资金（示例尝试）
            try:
                hsgt = ak.stock_hsgt_funds_flow()
                if isinstance(hsgt, pd.DataFrame) and not hsgt.empty:
                    # 找最后 5 个交易日的 north_net 列（不同版本列名不同）
                    # 先尝试列包含 '净买入' 或 'net' 等关键词
                    cols = list(hsgt.columns)
                    # 尝试自动选列
                    cand = None
                    for c in cols:
                        if '净' in str(c) or 'net' in str(c).lower():
                            cand = c
                            break
                    if cand is not None:
                        # 取最后 5 条求和（单位以 ak 返回为准）
                        val = pd.to_numeric(hsgt[cand].tail(5).sum(), errors='coerce')
                        if not np.isnan(val):
                            north['net_inflow_5d'] = float(val)
            except Exception:
                pass

        except Exception as e:
            print("宏观/资金数据抓取失败：", e)

    liq_score = score_liquidity(macro, north)
    report_lines.append(f"流动性评分（0-100，越大越宽松）：{liq_score}")

    # 估值（占位：如果你希望自动获取估值分位，可在此实现）
    # val = {'pe_ttm': None, 'pb': None, 'pe_pctile': None, 'pb_pctile': None}
    val = fetch_index_valuation(CSI500_CODE)
    val_score = score_valuation(val)
    report_lines.append(f"估值得分（0-100，越大越安全/便宜）：{val_score}")

    # 技术面（中证500）
    idx_df = None
    try:
        idx_df = fetch_daily_index(CSI500_CODE)
        tech_score, bb = score_technical(idx_df)
        report_lines.append(f"技术面得分（0-100，越大越安全）：{tech_score}")

        # 绘图：指数布林图（如果有数据）
        if idx_df is not None and bb is not None:
            import matplotlib.pyplot as plt
            plt.figure(figsize=(10, 6))
            plt.plot(idx_df.index, idx_df['close'], label='Close')
            plt.plot(bb.index, bb['upper'], label='BOLL_UPPER')
            plt.title('中证500 Close & Bollinger Bands')
            plt.legend()
            fig_path = os.path.join(OUT_DIR, 'csi500_boll.png')
            plt.savefig(fig_path, bbox_inches='tight')
            plt.close()
            report_lines.append(f"已保存指数布林图：{fig_path}")
    except Exception as e:
        report_lines.append(f"指数技术面分析失败：{e}")
        tech_score = 50

    # 综合得分（权重已归一）
    composite = int(WEIGHT_LIQUIDITY * liq_score + WEIGHT_VALUATION * val_score + WEIGHT_TECHNICAL * tech_score)
    report_lines.append(f"综合热度分（0-100）：{composite}")

    if composite >= 75:
        report_lines.append('综合结论：热度偏高 → 建议考虑部分止盈/减仓')
    elif composite >= 55:
        report_lines.append('综合结论：中性偏高 → 注意风险，保持关注')
    else:
        report_lines.append('综合结论：市场偏冷 → 可逢低布局')

    # 持仓逐股分析（短线布林） — <--- 加了 None 检查，失败优雅跳过
    if USER_HOLDINGS:
        report_lines.append('\n持仓逐股布林分析（短线提示）：')
        for code in USER_HOLDINGS:
            try:
                # 保留原带后缀输出，内部使用纯数字代码
                clean_code = code.replace(".SZ", "").replace(".SH", "").replace(".sz", "").replace(".sh", "")
                sdf = fetch_stock_daily(clean_code)
                if sdf is None:
                    report_lines.append(f"{code} ：无法获取数据（接口失败或无数据），已跳过。")
                    continue

                # 计算布林
                bb_s = bollinger_bands(sdf['close'], window=BOLL_WINDOW, n=BOLL_N)
                last = bb_s.dropna().tail(3)
                comment = '中性'
                if len(last) >= 2 and last['close'].iloc[-1] > last['upper'].iloc[-1]:
                    comment = '短线超买（注意回撤）'
                elif len(last) > 0 and last['close'].iloc[-1] < last['lower'].iloc[-1]:
                    comment = '短线超卖（关注反弹）'

                last_close = last['close'].iloc[-1] if len(last) > 0 else 'N/A'
                report_lines.append(f"{code} ：{comment} （最近收盘 {last_close}）")

                # 绘图单股布林（仅保存，不影响主流程）
                import matplotlib.pyplot as plt
                plt.figure(figsize=(8,4))
                plt.plot(sdf.index, sdf['close'], label='Close')
                plt.plot(bb_s.index, bb_s['upper'], label='Upper')
                plt.title(f'{code} Bollinger')
                plt.legend()
                figp = os.path.join(OUT_DIR, f'{code}_boll.png')
                plt.savefig(figp, bbox_inches='tight')
                plt.close()
            except Exception as e:
                report_lines.append(f'{code} 分析失败：{e}')

    # 输出并保存报告
    report_txt = '\n'.join(report_lines)
    report_file = os.path.join(OUT_DIR, f'report_{dt.datetime.now().strftime("%Y%m%d_%H%M%S")}.txt')
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report_txt)

    print('\n' + report_txt)
    print(f'完整报告已写入：{report_file}')


if __name__ == '__main__':
    analyze_and_report()
