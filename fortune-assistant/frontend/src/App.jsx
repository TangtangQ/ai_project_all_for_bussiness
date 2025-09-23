import { useState } from "react";

function App() {
  const [birth, setBirth] = useState({year:1995, month:8, day:15, hour:14, gender:"男"});
  const [result, setResult] = useState(null);

  const handleAnalyze = async () => {
    const res = await fetch("http://127.0.0.1:8000/analyze", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ birth, divination:{} })
    });
    setResult(await res.json());
  };

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">玄学助手 🔮</h1>
      <button onClick={handleAnalyze} className="bg-purple-500 text-white px-4 py-2 rounded">
        开始分析
      </button>
      {result && (
        <div className="mt-4">
          <h2 className="font-semibold">八字分析</h2>
          <p>{result.bazi}</p>
          <h2 className="font-semibold mt-2">紫微斗数</h2>
          <p>{result.ziwei}</p>
          <h2 className="font-semibold mt-2">周易卜卦</h2>
          <p>{result.zhouyi}</p>
          <a href={result.pdf_report} target="_blank" rel="noopener noreferrer" className="text-blue-500 underline mt-2 block">
            下载 PDF 报告
          </a>
        </div>
      )}
    </div>
  );
}

export default App;
