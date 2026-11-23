// 사용법: node load.js <URL> [초당 요청 수]
// 응답을 기다리지 않고 정해진 속도로 요청을 계속 보낸다. (사용자는 서버 사정을 봐주지 않는다)
const [url, rpsArg] = process.argv.slice(2);
if (!url) {
  console.log("사용법: node load.js <URL> [초당 요청 수]");
  process.exit(1);
}
const target = url.startsWith("http") ? url : `http://${url}`;
const rps = Number(rpsArg || 2);
const TIMEOUT_MS = 5000;

const fresh = () => ({ sent: 0, ok: 0, errors: {}, latency: 0, tasks: {}, capacity: 0 });
let stats = fresh();

async function request() {
  stats.sent++;
  const start = Date.now();
  try {
    const res = await fetch(target, { signal: AbortSignal.timeout(TIMEOUT_MS) });
    if (!res.ok) {
      await res.arrayBuffer();
      return fail(res.status);
    }
    const body = await res.json();
    stats.ok++;
    stats.latency += Date.now() - start;
    stats.tasks[body.task] = (stats.tasks[body.task] || 0) + 1;
    stats.capacity += body.capacity_rps;
  } catch (e) {
    fail(e.name === "TimeoutError" ? "timeout" : "연결실패");
  }
}

function fail(key) {
  stats.errors[key] = (stats.errors[key] || 0) + 1;
}

function report() {
  const s = stats;
  stats = fresh();
  const failed = Object.values(s.errors).reduce((a, b) => a + b, 0);
  const detail = Object.entries(s.errors).map(([k, v]) => `${k}×${v}`).join(", ");
  const tasks = Object.entries(s.tasks).map(([k, v]) => `${k}:${v}`).join("  ");
  const time = new Date().toTimeString().slice(0, 8);
  console.log([
    time,
    `보냄 ${s.sent}`,
    `성공 ${s.ok}`,
    failed ? `실패 ${failed} (${detail}) !!` : "실패 0",
    s.ok ? `평균 ${Math.round(s.latency / s.ok)}ms` : "평균 -",
    s.ok ? `task 1개 처리량≈${Math.round(s.capacity / s.ok)}rps` : "",
    tasks ? `| ${tasks}` : ""
  ].join("  "));
}

console.log(`${target} 으로 초당 ${rps}개 요청 (timeout ${TIMEOUT_MS / 1000}s). 종료: Ctrl+C`);
setInterval(request, 1000 / rps);
setInterval(report, 1000);
