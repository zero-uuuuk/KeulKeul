const http = require("http");

const port = process.env.PORT || 3000;

const server = http.createServer((req, res) => {
  res.writeHead(200, { "Content-Type": "application/json; charset=utf-8" });
  res.end(JSON.stringify({
    message: "hello ecs",
    path: req.url,
    container: "week9-level1"
  }));
});

server.listen(port, "0.0.0.0", () => {
  console.log(`server listening on ${port}`);
});

