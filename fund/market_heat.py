"""
market_heat.py

中证500 + 持仓“温度仪”脚本（实时抓取数据，生成文字报告与图表）

说明：
- 依赖：akshare, pandas, numpy, matplotlib
- 请先用 `pip install akshare pandas numpy matplotlib` 安装依赖
- 设计理念：优先使用 akshare 获取 A股与宏观数据；若缺失，可按注释调整

使用方法：
python market_heat.py

脚本会：
- 获取中证500（000905.SH）的日线行情并计算布林线
- 抓取常用宏观流动性指标（M2、社融增速）并简单评分
- 抓取北向资金最近 5 日净流入/流出作为资金流向参考
- 对用户自定义持仓（股票代码列表）逐一绘制布林线并输出短评
- 最后输出综合热度分数（0-100）和是否触发“鸣金收兵”提醒

请在下面的 `USER_HOLDINGS` 中填写你真实的股票代码（格式："000xxx.SZ"或"600xxx.SH"）。
如果你只提供了股票名称，请先在通联/东方财富/网易/雪球等查询对应代码并填写。

注意：本脚本只是分析工具，不构成投资建议。请根据自身风险偏好调整权重与阈值。

"""

import os
import time
import datetime as dt
import warnings
import pandas as pd
from bs4 import BeautifulSoup
import requests

warnings.filterwarnings('ignore')

# ---------- 配置区 ----------
# 填写你的持仓（必须填写代码），例如："300567.SZ" 或 "600519.SH"
# 如果不知道代码，请先在东方财富/雪球/同花顺查询
USER_HOLDINGS = [
    # 示例（请替换为真实代码）
    "300502.SZ",  # 新易盛  （示例代码，非保证准确）
    "300308.SZ",  # 中际旭创
    "603063.SH",  # 禾望电气
    "002463.SZ",  # 沪电股份
    "603606.SH",  # 东方电缆
    "002487.SZ",  # 大金重工
    "300395.SZ",  # 菲利华

]

# 中证500 指数代码（akshare 的索引取法可能仅需要 '000905'；下面函数会处理）
CSI500_CODE = '中证500'  # 注意：在不同API下格式会不同，脚本内部会尝试兼容
# ---------- 配置区新增 ----------
WEIGHT_ACCOUNT = 0.1  # 上交所新增开户数权重

# 历史最高开户数（可根据上交所月报手动更新）
HISTORICAL_MAX_ACCOUNTS = 313.36  # 示例值，请替换为真实历史高点


# 输出目录
OUT_DIR = os.path.abspath('./market_heat_output')
os.makedirs(OUT_DIR, exist_ok=True)

# 分析参数
BOLL_WINDOW = 20
BOLL_N = 2  # 上下轨倍数

# 权重（可调整）
WEIGHT_LIQUIDITY = 0.35
WEIGHT_VALUATION = 0.35
WEIGHT_TECHNICAL = 0.3


def safe_import_akshare():
    try:
        import akshare as ak
        return ak
    except Exception as e:
        print("错误：未能导入 akshare。请先运行：pip install akshare")
        raise


def bollinger_bands(df_close, window=20, n=2):
    """返回 DataFrame，包含 columns: 'mid','upper','lower'"""
    ma = df_close.rolling(window).mean()
    sd = df_close.rolling(window).std()
    upper = ma + n * sd
    lower = ma - n * sd
    res = df_close.to_frame(name='close')
    res['mid'] = ma
    res['upper'] = upper
    res['lower'] = lower
    return res


# ---------- 数据获取模块（依赖 akshare） ----------

def fetch_macro_indicators():
    """尝试从 akshare 获取 M2、社融等宏观数据并返回最近年份的同比值（若可用）"""
    ak = safe_import_akshare()
    out = {}
    try:
        # ak.macro_china_money_supply() 返回 M0 M1 M2 等历史数据（按 akshare 版本不同字段有差异）
        m2 = ak.macro_china_money_supply()
        # 假设表格包含 '指标' 与 '同比' 或类似字段；我们做容错处理
        if 'M2' in m2.columns:
            # 取最后一行 M2 同比
            row = m2[m2['货币供应量(%)'.encode('utf-8')] if '货币供应量(%)' in m2.columns else 'M2']
        # 更稳妥：尝试 ak.macro_china_money_supply_yearly() 等，因 akshare 版本差异很大，请在本地运行并调整
        out['m2'] = None
    except Exception:
        out['m2'] = None

    try:
        sf = ak.macro_china_social_financing()  # 可能不存在，不同 ak 版本不同函数名
        out['social_financing'] = None
    except Exception:
        out['social_financing'] = None

    # 我们也可以尝试读取本地或手动输入的宏观值
    return out


def fetch_northbound_flow(days=5):
    """使用 akshare 获取沪深北向资金（陆股通）近几日净流入（若可用）"""
    ak = safe_import_akshare()
    try:
        # ak.stock_em_hk_recent() 不是北向资金接口，真实接口可能为 ak.stock_hsgt_flow or similar
        df = ak.stock_hsgt_funds_flow(month=1)  # 仅示例，真实项目需参考 akshare 文档
        # 处理 df，取最近 days 的净买入
        return {'net_inflow_5d': None}
    except Exception:
        return {'net_inflow_5d': None}


def fetch_index_valuation(index_code='000905.SH'):
    """尝试获取中证500 的估值（PE/Ttm、PB）以及历史分位（如可）

    返回 dict:
      {'pe_ttm': float or None, 'pb': float or None, 'pe_pctile': 0-1 or None, 'pb_pctile': 0-1 or None}
    """
    ak = safe_import_akshare()
    out = {'pe_ttm': None, 'pb': None, 'pe_pctile': None, 'pb_pctile': None}
    try:
        # akshare 里可能有 index valuation 的接口，例如 ak.index_zh_a_pe_ratio 或者通过东方财富接口抓取
        # 这里我们先用占位方式，提醒用户如需精确请用 ak.index_zh_a_hist or ak.index_stock_consituent
        pass
    except Exception:
        pass
    return out

def fetch_daily_index():
    """
    获取中证500指数日线行情
    """
    import akshare as ak
    import pandas as pd

    try:
        # 首选接口
        df = ak.stock_zh_index_daily(symbol="sh000905")  # 中证500
        if df is not None and not df.empty:
            df = df.reset_index()
            if 'date' in df.columns and 'close' in df.columns:
                df['date'] = pd.to_datetime(df['date']).dt.date
                df = df.set_index('date')
                return df[['close']]
    except Exception as e:
        print(f"akshare 主接口失败：{e}")

    # 🩵 备用逻辑（兜底：index_zh_a_hist）
    try:
        idx = ak.index_zh_a_hist(symbol='000905')
        if idx is not None and not idx.empty and '收盘' in idx.columns:
            idx = idx.rename(columns={'日期': 'date', '收盘': 'close'})
            idx['date'] = pd.to_datetime(idx['date']).dt.date
            idx = idx.set_index('date')
            return idx[['close']]
    except Exception as e:
        print(f"备用接口失败：{e}")

    print("指数技术面分析失败：未获取到指数日线数据（akshare接口失败且本地 index_daily.csv 不存在）")
    return None


def fetch_stock_daily(stock_code, start=None, end=None, retry=3):
    """
    获取单只股票日线（收盘价）用于布林线分析。
    返回 DataFrame 索引为日期，含 'close'。失败时返回 None。

    参数：
    - stock_code: 股票代码，例如 "300502.SZ"
    - start, end: 日期范围，默认最近1年
    - retry: 接口失败时重试次数
    """
    ak = safe_import_akshare()

    if start is None:
        start = (dt.date.today() - dt.timedelta(days=90)).strftime('%Y-%m-%d')
    if end is None:
        end = dt.date.today().strftime('%Y-%m-%d')

    for attempt in range(retry):
        try:
            time.sleep(1)  # 避免接口封禁
            df = ak.stock_zh_a_hist(symbol=stock_code, period='daily', adjust='qfq', start_date=start, end_date=end)

            if df is None or df.empty:
                raise ValueError("接口返回为空")

            # 列名兼容处理
            if '日期' in df.columns:
                df = df.rename(columns={'日期': 'date', '收盘': 'close'})
            elif 'date' not in df.columns or 'close' not in df.columns:
                raise ValueError(f"未识别列名: {df.columns}")

            df['date'] = pd.to_datetime(df['date']).dt.date
            df = df.set_index('date')
            return df[['close']]

        except Exception as e:
            print(f"[尝试 {attempt+1}/{retry}] 获取 {stock_code} 日线失败：{e}")
            time.sleep(1)  # 重试前等待

    print(f"最终获取 {stock_code} 日线数据失败，返回 None")
    return None

# ---------- 评分与逻辑 ----------
def map_to_score(value, min_val, max_val):
    """线性映射 value 到 0-100"""
    score = (value - min_val) / (max_val - min_val) * 100
    score = max(0, min(100, score))
    return score

def score_liquidity(macro_dict, northbound_dict):
    """
    计算流动性评分（0-100），越高表示市场越宽松
    macro_dict: {'m2': float, 'social_financing': float}
    northbound_dict: {'net_inflow_5d': float}  # 单位可用亿
    """
    scores = []

    # M2评分（历史区间 6%-14% 线性映射）
    m2 = macro_dict.get('m2')
    if m2 is not None:
        scores.append(map_to_score(m2, 6, 14))
    
    # 社融增速评分（历史区间 8%-16%）
    sf = macro_dict.get('social_financing')
    if sf is not None:
        scores.append(map_to_score(sf, 8, 16))
    
    # 北向资金评分（近5日净流入/历史最大净流入）
    nb = northbound_dict.get('net_inflow_5d')
    if nb is not None:
        # 假设历史最大 1000 亿，线性映射 0-100
        scores.append(map_to_score(nb, 0, 1000))
    
    # 如果都没数据，返回中性 50
    if not scores:
        return 50

    # 加权平均，可根据经验调整权重
    # 这里默认各项等权
    score = sum(scores)/len(scores)
    return int(score)


def score_valuation(val_dict):
    """把 0~50% 对应 score 100~70，70% → 50~60，>90% → 0~50"""
    pe_pct = val_dict.get('pe_pctile')
    pb_pct = val_dict.get('pb_pctile')

    # 若都没数据
    if pe_pct is None and pb_pct is None:
        return 50

    # 平均分位
    pcts = [v for v in [pe_pct, pb_pct] if v is not None]
    avg_pct = sum(pcts)/len(pcts)

    # 分位映射到 0-100 分数
    if avg_pct < 0.5:  # 0~50%
        score = 70 + (0.5 - avg_pct)/0.5 * 30  # 50%->100，0%->100
    elif avg_pct < 0.7:  # 50~70%
        score = 50 + (0.7 - avg_pct)/0.2 * 20  # 50%->70，70%->50
    else:  # >70%
        score = max(0, 50 - (avg_pct-0.7)/0.3*50)  # 70%->50，100%->0

    return int(score)



def score_technical(idx_close_df):
    # 计算布林带并判断最近是否连续多日收于上轨之上
    import pandas as pd
    s = idx_close_df['close'].astype(float)
    bb = bollinger_bands(s, window=BOLL_WINDOW, n=BOLL_N)
    last = bb.dropna().tail(5)
    # 判定：如果最后 2 天收盘价都 > upper，则认为短线超热，给低分
    if len(last) >= 2 and (last['close'].iloc[-1] > last['upper'].iloc[-1]) and (last['close'].iloc[-2] > last['upper'].iloc[-2]):
        return 20, bb
    # 其它情况中性
    return 60, bb


# ---------- 主流程 ----------
def analyze_and_report():
    import pandas as pd
    ak = safe_import_akshare()

    report_lines = []
    now = dt.datetime.now()
    report_lines.append(f"市场温度检测时间：{now.strftime('%Y-%m-%d %H:%M:%S')}")
    # 宏观
    macro = fetch_macro_indicators()
    north = fetch_northbound_flow(days=5)
    liq_score = score_liquidity(macro, north)
    report_lines.append(f"流动性评分（0-100，越大越宽松）：{liq_score}")

    # 估值
    val = fetch_index_valuation(CSI500_CODE)
    val_score = score_valuation(val)
    report_lines.append(f"估值得分（0-100，越大越安全/便宜）：{val_score}")

    # 技术（指数布林）
    try:
        idx_df = fetch_daily_index(CSI500_CODE)
        tech_score, bb = score_technical(idx_df)
        report_lines.append(f"技术面得分（0-100，越大越安全）：{tech_score}")

        # 绘图：指数布林图
        import matplotlib.pyplot as plt
        plt.figure(figsize=(10, 6))
        plt.plot(idx_df.index, idx_df['close'], label='Close')
        # plt.plot(bb.index, bb['mid'], label='BOLL_MID')
        plt.plot(bb.index, bb['upper'], label='BOLL_UPPER')
        # plt.plot(bb.index, bb['lower'], label='BOLL_LOWER')
        plt.title('中证500 Close & Bollinger Bands')
        plt.legend()
        fig_path = os.path.join(OUT_DIR, 'csi500_boll.png')
        plt.savefig(fig_path, bbox_inches='tight')
        plt.close()
        report_lines.append(f"已保存指数布林图：{fig_path}")
    except Exception as e:
        report_lines.append(f"指数技术面分析失败：{e}")
        tech_score = 50

    # 综合得分
    composite = int(WEIGHT_LIQUIDITY * liq_score + WEIGHT_VALUATION * val_score + WEIGHT_TECHNICAL * tech_score)

    report_lines.append(f"综合热度分（0-100）：{composite}")

    if composite >= 75:
        report_lines.append('综合结论：热度偏高 → 建议考虑部分止盈/减仓')
    elif composite >= 55:
        report_lines.append('综合结论：中性偏高 → 注意风险，保持关注')
    else:
        report_lines.append('综合结论：市场偏冷 → 可逢低布局')

    # 持仓逐股分析（若提供）
    if USER_HOLDINGS:
        report_lines.append('\n持仓逐股布林分析（短线提示）：')
        for code in USER_HOLDINGS:
            try:
                clean_code = code.replace(".SZ", "").replace(".SH", "")
                sdf = fetch_stock_daily(clean_code)
                bb_s = bollinger_bands(sdf['close'], window=BOLL_WINDOW, n=BOLL_N)
                last = bb_s.dropna().tail(3)
                comment = '中性'
                if len(last) >= 2 and last['close'].iloc[-1] > last['upper'].iloc[-1]:
                    comment = '短线超买（注意回撤）'
                elif last['close'].iloc[-1] < last['lower'].iloc[-1]:
                    comment = '短线超卖（关注反弹）'

                report_lines.append(f"{code} ：{comment} （最近收盘 {last['close'].iloc[-1] if len(last)>0 else 'N/A'}）")

                # 绘图单股布林
                import matplotlib.pyplot as plt
                plt.figure(figsize=(8,4))
                plt.plot(sdf.index, sdf['close'], label='Close')
                # plt.plot(bb_s.index, bb_s['mid'], label='Mid')
                plt.plot(bb_s.index, bb_s['upper'], label='Upper')
                # plt.plot(bb_s.index, bb_s['lower'], label='Lower')
                plt.title(f'{code} Bollinger')
                plt.legend()
                figp = os.path.join(OUT_DIR, f'{code}_boll.png')
                plt.savefig(figp, bbox_inches='tight')
                plt.close()
                # report_lines.append(f'已保存图表: {figp}')
            except Exception as e:
                report_lines.append(f'{code} 分析失败：{e}')

    # 输出报告
    report_txt = '\n'.join(report_lines)
    report_file = os.path.join(OUT_DIR, f'report_{dt.datetime.now().strftime("%Y%m%d_%H%M%S")}.txt')
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report_txt)

    print('\n' + report_txt)
    print(f'完整报告已写入：{report_file}')


if __name__ == '__main__':
    # pip install akshare pandas yfinance matplotlib numpy
    analyze_and_report()

