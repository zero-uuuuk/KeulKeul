const http = require("http");

const port = process.env.PORT || 3000;
const members = new Set(["장영욱", "정유진", "정현도", "정주현", "이태호", "지문호", "임수하", "이태환", "백현려", "하지찬"]);

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  const name = url.searchParams.get("name");
  const isMember = members.has(name);

  res.writeHead(200, { "Content-Type": "application/json; charset=utf-8" });
  res.end(JSON.stringify({
    name,
    keulkeul_member: isMember ? "yes" : "no"
  }));
});

server.listen(port, "0.0.0.0", () => {
  console.log(`api listening on ${port}`);
});
