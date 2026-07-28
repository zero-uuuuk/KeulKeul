import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const API_BASE = "https://{본인_API_ID}.execute-api.{REGION}.amazonaws.com"

const statusLabels = {
  PENDING_UPLOAD: "업로드 대기",
  REVIEW: "검토 중",
  PRODUCTION: "운영 승인",
};

function formatPercent(value) {
  return `${(Number(value) * 100).toFixed(2)}%`;
}

function resultText(item) {
  if (!item.lastTestResult) {
    return "아직 테스트 전";
  }

  const result = item.lastTestResult;
  if (result.errorMessage) {
    return `테스트 실패 · ${result.errorType || result.errorMessage}`;
  }
  if (!result.predictedLabel || result.confidence == null || result.latencyMs == null) {
    return "테스트 결과 형식 오류";
  }

  return `${result.predictedLabel} · ${Math.round(result.confidence * 100)}% · ${result.latencyMs}ms`;
}

async function assertOk(response) {
  if (response.ok) {
    return response;
  }

  const body = await response.json().catch(() => ({}));
  throw new Error(body.message || `HTTP ${response.status}`);
}

function App() {
  const [models, setModels] = useState([]);
  const [message, setMessage] = useState("모델 registry 상태를 불러오는 중입니다.");
  const [busyId, setBusyId] = useState("");
  const [testImages, setTestImages] = useState({});

  const summary = useMemo(() => {
    return models.reduce(
      (acc, item) => {
        acc.total += 1;
        acc[item.status] = (acc[item.status] || 0) + 1;
        return acc;
      },
      { total: 0, PENDING_UPLOAD: 0, REVIEW: 0, PRODUCTION: 0 },
    );
  }, [models]);

  async function loadModels() {
    const response = await assertOk(await fetch(`${API_BASE}/models`));
    const body = await response.json();
    setModels(body.items || []);
    setMessage("모델 목록이 최신 상태입니다.");
  }

  async function registerModel(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const artifact = form.get("artifact");

    if (!artifact || artifact.size === 0) {
      setMessage("ONNX 모델 파일을 선택하세요.");
      return;
    }

    setMessage("업로드 URL을 발급하는 중입니다.");
    const createResponse = await assertOk(await fetch(`${API_BASE}/models/upload-url`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        modelName: form.get("modelName"),
        version: form.get("version"),
        accuracy: Number(form.get("accuracy")),
        filename: artifact.name,
      }),
    }));
    const upload = await createResponse.json();

    setMessage("ONNX 모델 파일을 S3에 업로드하는 중입니다.");
    await assertOk(await fetch(upload.uploadUrl, {
      method: "PUT",
      headers: { "content-type": "application/octet-stream" },
      body: artifact,
    }));

    setMessage("업로드 완료. S3 이벤트 처리를 기다리는 중입니다.");
    setTimeout(() => loadModels().catch((error) => setMessage(error.message)), 3000);
  }

  async function uploadTestImage(modelId) {
    const image = testImages[modelId];
    if (!image) {
      throw new Error("테스트 이미지를 선택하세요.");
    }

    // 테스트 이미지는 Presigned URL로 S3에 직접 업로드
    const createResponse = await assertOk(await fetch(`${API_BASE}/models/${modelId}/test-image-url`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        filename: image.name,
        contentType: image.type || "image/jpeg",
      }),
    }));
    const upload = await createResponse.json();

    await assertOk(await fetch(upload.uploadUrl, {
      method: "PUT",
      headers: { "content-type": image.type || "image/jpeg" },
      body: image,
    }));

    return upload.imageKey;
  }

  async function runAction(modelId, action) {
    setBusyId(`${modelId}:${action}`);
    setMessage(`${modelId} ${action === "test" ? "테스트 추론" : "Production 승인"} 처리 중입니다.`);

    try {
      const path = action === "test"
        ? `/models/${modelId}/test-inference`
        : `/models/${modelId}/status`;
      const body = action === "test"
        ? { imageKey: await uploadTestImage(modelId) }
        : { status: "PRODUCTION" };

      await assertOk(await fetch(`${API_BASE}${path}`, {
        method: action === "test" ? "POST" : "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      }));
      await loadModels();
    } finally {
      setBusyId("");
    }
  }

  useEffect(() => {
    loadModels().catch((error) => setMessage(error.message));
  }, []);

  return (
    <main className="page">
      <header className="topbar">
        <div>
          <p className="eyebrow">KeulKeul Week 5 · Serverless MLOps</p>
          <h1>AI 모델 승인 콘솔</h1>
        </div>
        <button className="ghost" onClick={() => loadModels().catch((error) => setMessage(error.message))} type="button">
          새로고침
        </button>
      </header>

      <section className="summary" aria-label="모델 상태 요약">
        <div>
          <span>{summary.total}</span>
          <p>전체 모델</p>
        </div>
        <div>
          <span>{summary.PENDING_UPLOAD}</span>
          <p>업로드 대기</p>
        </div>
        <div>
          <span>{summary.REVIEW}</span>
          <p>검토 중</p>
        </div>
        <div>
          <span>{summary.PRODUCTION}</span>
          <p>운영 승인</p>
        </div>
      </section>

      <p className="message">{message}</p>

      <section className="workspace">
        <form className="register" onSubmit={(event) => registerModel(event).catch((error) => setMessage(error.message))}>
          <h2>후보 모델 등록</h2>
          <label>
            모델 이름
            <input name="modelName" defaultValue="resnet18-image-classifier" required />
          </label>
          <label>
            버전
            <input name="version" defaultValue="v1" required />
          </label>
          <label>
            Accuracy
            <input name="accuracy" defaultValue="0.69758" min="0" max="1" step="0.00001" type="number" required />
          </label>
          <label>
            ONNX 모델
            <input accept=".onnx" name="artifact" type="file" required />
          </label>
          <button type="submit">등록 및 업로드</button>
        </form>

        <section className="tableWrap">
          <div className="tableHead">
            <h2>후보 모델 목록</h2>
            <span>{models.length} items</span>
          </div>
          <table>
            <thead>
              <tr>
                <th>Model ID</th>
                <th>Accuracy</th>
                <th>Status</th>
                <th>S3 Key</th>
                <th>Test Image</th>
                <th>Last Test</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {models.map((item) => {
                const canTest = item.status === "REVIEW";
                const hasTestImage = Boolean(testImages[item.modelId]);
                const canApprove = item.status === "REVIEW" && item.lastTestResult;

                return (
                  <tr key={item.modelId}>
                    <td className="modelId">{item.modelId}</td>
                    <td>{formatPercent(item.accuracy)}</td>
                    <td><span className={`badge ${item.status.toLowerCase()}`}>{statusLabels[item.status] || item.status}</span></td>
                    <td className="s3key">{item.artifactKey}</td>
                    <td>
                      <input
                        accept="image/*"
                        disabled={!canTest || Boolean(busyId)}
                        onChange={(event) => setTestImages({
                          ...testImages,
                          [item.modelId]: event.target.files[0],
                        })}
                        type="file"
                      />
                    </td>
                    <td>{resultText(item)}</td>
                    <td>
                      <div className="actions">
                        <button
                          disabled={!canTest || !hasTestImage || busyId === `${item.modelId}:test`}
                          onClick={() => runAction(item.modelId, "test").catch((error) => setMessage(error.message))}
                          type="button"
                        >
                          테스트
                        </button>
                        <button
                          disabled={!canApprove || busyId === `${item.modelId}:approve`}
                          onClick={() => runAction(item.modelId, "approve").catch((error) => setMessage(error.message))}
                          type="button"
                        >
                          승인
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
