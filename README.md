🔮 玄学助手 (Fortune Assistant)

基于 Kimi K2 开源模型 的智能玄学助手，集成了 八字分析、紫微斗数、周易卜卦，并支持生成 PDF 报告。
采用 FastAPI 后端 + React 前端 + TailwindCSS 架构。

✨ 功能特性

八字分析
输入出生年月日时，结合五行、格局，输出运势与注意事项。

紫微斗数排盘
根据出生时间排盘，输出命宫、身宫、主星及整体解读。

周易卜卦
支持时间起卦/随机起卦，自动生成卦象与解卦说明。

AI 解读
使用 Kimi K2 生成自然语言分析报告。

PDF 报告导出
一键生成带排版的分析报告。

Web 界面
直观的 React 界面，表单输入 + 结果展示 + 报告下载。

📸 界面预览

（这里可以放前端运行效果图，等你前端跑起来截图粘贴）

📂 项目结构
fortune-assistant/
│── backend/                # FastAPI 后端
│   │── main.py              # 后端入口，定义接口
│   │── kimi_client.py       # Kimi K2 API 封装
│   │── modules/             # 玄学算法模块
│   │   ├── bazi.py          # 八字
│   │   ├── ziwei.py         # 紫微斗数
│   │   ├── zhouyi.py        # 周易
│   │── pdf_report.py        # PDF 报告生成
│   │── requirements.txt     # Python 依赖
│
│── frontend/               # React 前端
│   │── src/
│   │   ├── App.jsx          # 主界面
│   │   ├── components/      # 表单 & 展示组件
│   │── package.json         # 前端依赖
│   │── tailwind.config.js   # Tailwind 配置
│   │── index.css            # 样式
│
│── README.md

🚀 快速启动
1. 克隆项目
git clone https://github.com/yourname/fortune-assistant.git
cd fortune-assistant

2. 后端启动

进入 backend/ 目录，安装依赖并运行：

cd backend
pip install -r requirements.txt
uvicorn main:app --reload


默认运行在 http://127.0.0.1:8000

3. 前端启动

进入 frontend/ 目录，安装依赖并运行：

cd frontend
npm install
npm run dev


默认运行在 http://127.0.0.1:5173

4. 使用方式

打开浏览器访问前端地址

输入出生信息（年月日时、性别等）

点击 分析

获得八字、紫微斗数、周易卜卦分析结果

点击 下载 PDF，获取完整报告

⚙️ 配置说明

后端配置

修改 backend/kimi_client.py 中的：

kimi = KimiClient(api_key="你的API_KEY")


确保网络能访问 Kimi K2 API

前端配置

如果后端端口不是 8000，请修改 frontend/src/App.jsx 里的 API 地址

📄 依赖
后端

FastAPI
 - 高性能 API 框架

Uvicorn
 - ASGI 服务器

Requests
 - HTTP 请求

ReportLab
 - PDF 生成

前端

React 18

Vite 5
 - 前端构建工具

Tailwind CSS
 - 样式框架

🛠️ 扩展计划

✅ 增加 更完整的紫微斗数排盘算法（接入开源排盘库）

✅ 支持 更多卜卦方式（数字卦、梅花易数）

✅ 支持 用户注册 & 历史记录保存

⏳ 增加 批量生成分析报告（如企业客户批量上传生辰信息）

⏳ 接入 多语言支持（中文/英文）

📜 许可证

MIT License. 你可以自由使用、修改和分发本项目。