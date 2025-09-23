from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
from modules import bazi, ziwei, zhouyi
from kimi_client import KimiClient
from pdf_report import generate_pdf

app = FastAPI()
kimi = KimiClient(api_key="你的API_KEY")

# 跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/analyze")
def analyze(birth: dict = Body(...), divination: dict = Body(...)):
    # 八字
    bazi_result = bazi.analyze_bazi(birth)
    bazi_text = kimi.chat(f"根据八字结果生成分析报告：{bazi_result}")

    # 紫微斗数
    ziwei_result = ziwei.generate_ziwei_chart(birth)
    ziwei_text = kimi.chat(f"根据紫微斗数排盘结果，详细解读：{ziwei_result}")

    # 周易卦象
    hexagram, meaning = zhouyi.generate_hexagram()
    zhouyi_text = kimi.chat(f"解读卦象《{hexagram}》：{meaning}")

    # PDF 报告
    pdf_path = generate_pdf(bazi_text, ziwei_text, zhouyi_text)

    return {
        "bazi": bazi_text,
        "ziwei": ziwei_text,
        "zhouyi": zhouyi_text,
        "pdf_report": pdf_path
    }
