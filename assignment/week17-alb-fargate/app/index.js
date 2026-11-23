const http = require("http");
const crypto = require("crypto");
const os = require("os");

const port = process.env.PORT || 3000;
// 요청 1개당 CPU 작업량 (TLS handshake 비용을 흉내 냄)
const work = Number(process.env.WORK || 30000);
// task에 할당된 vCPU. 처리량 계산에만 사용
const vcpu = Number(process.env.VCPU || 0.25);

const server = http.createServer((req, res) => {
  if (req.url === "/health") {
    res.writeHead(200);
    return res.end("ok");
  }

  const start = process.cpuUsage();
  crypto.pbkdf2Sync("password", "salt", work, 32, "sha256");
  const used = process.cpuUsage(start);
  const cpuMs = (used.user + used.system) / 1000;

  res.writeHead(200, { "Content-Type": "application/json; charset=utf-8" });
  res.end(JSON.stringify({
    message: "hello",
    task: os.hostname().split(".")[0],
    cpu_ms: Math.round(cpuMs),
    // 이 task가 1초에 처리할 수 있는 요청 수 (대략)
    capacity_rps: Math.round((vcpu * 1000) / Math.max(cpuMs, 1))
  }));
});

server.listen(port, "0.0.0.0", () => {
  console.log(`server listening on ${port} (WORK=${work}, VCPU=${vcpu})`);
});
