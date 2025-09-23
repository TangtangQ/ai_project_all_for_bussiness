from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

def generate_pdf(bazi_text, ziwei_text, zhouyi_text, filename="report.pdf"):
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(filename)
    story = []

    story.append(Paragraph("🔮 玄学综合分析报告", styles["Title"]))
    story.append(Spacer(1, 20))

    story.append(Paragraph("一、八字分析", styles["Heading2"]))
    story.append(Paragraph(bazi_text, styles["Normal"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("二、紫微斗数", styles["Heading2"]))
    story.append(Paragraph(ziwei_text, styles["Normal"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("三、周易卜卦", styles["Heading2"]))
    story.append(Paragraph(zhouyi_text, styles["Normal"]))

    doc.build(story)
    return filename
