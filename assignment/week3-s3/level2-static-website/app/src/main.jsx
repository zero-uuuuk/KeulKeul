import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const panels = {
  home: {
    title: "S3 Static Website",
    body: "React와 Vite로 만든 CSR 앱을 S3 정적 웹 사이트 호스팅으로 배포합니다.",
  },
  build: {
    title: "Build Artifact",
    body: "npm run build 결과로 생성되는 dist 폴더의 파일을 S3 버킷에 업로드합니다.",
  },
  route53: {
    title: "Route 53 Ready",
    body: "다음 level에서는 이 S3 website endpoint를 Route 53 alias record와 연결합니다.",
  },
};

function App() {
  const [activePanel, setActivePanel] = useState("home");
  const panel = panels[activePanel];

  return (
    <main className="page">
      <section className="hero">
        <p className="eyebrow">KeulKeul Week 3</p>
        <h1>React CSR on Amazon S3</h1>
        <p className="lead">
          서버에서 HTML을 매번 렌더링하지 않고, 브라우저가 JavaScript를 받아 화면을 구성합니다.
        </p>
      </section>

      <nav className="tabs" aria-label="실습 단계">
        {Object.entries(panels).map(([key, value]) => (
          <button
            className={activePanel === key ? "tab active" : "tab"}
            key={key}
            onClick={() => setActivePanel(key)}
            type="button"
          >
            {value.title}
          </button>
        ))}
      </nav>

      <section className="panel">
        <h2>{panel.title}</h2>
        <p>{panel.body}</p>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
