import express from "express";
import {
  Counter,
  Histogram,
  register,
  collectDefaultMetrics,
} from "prom-client";

const SERVICE_NAME = process.env.SERVICE_NAME ?? "unknown";
const DOWNSTREAM_URL = process.env.DOWNSTREAM_URL;
const PORT = Number(process.env.PORT ?? 8080);

const httpRequestsTotal = new Counter({
  name: "http_requests_total",
  help: "Total number of HTTP requests",
  labelNames: ["method", "route", "status"],
});

const httpRequestsDuration = new Histogram({
  name: "http_request_duration_seconds",
  help: "Total number of HTTP request seconds",
  buckets: [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10],
  labelNames: ["method", "route", "status"],
});

collectDefaultMetrics();

const app = express();

app.use((req, res, next) => {
  const start = Date.now();
  res.on("finish", () => {
    const duration = Date.now() - start;
    const label = {
      method: req.method,
      route: req.route?.path ?? "unmatched",
      status: res.statusCode,
    };
    httpRequestsDuration.observe(label, duration / 1000);
    httpRequestsTotal.inc(label);
  });
  next();
});

app.get("/api/work", async (_req, res) => {
  if (!DOWNSTREAM_URL) {
    res.json({ service: SERVICE_NAME });
    return;
  }
  try {
    const response = await fetch(`${DOWNSTREAM_URL}/api/work`, {
      signal: AbortSignal.timeout(2000),
    });
    if (!response.ok) {
      res.status(502).json({
        service: SERVICE_NAME,
        downstream_status: response.status,
        error: "downstream_error",
      });
      return;
    }
    const data = await response.json();
    res.json({ service: SERVICE_NAME, downstream: data });
  } catch (error) {
    if (error instanceof Error && error.name === "TimeoutError") {
      res
        .status(504)
        .json({ service: SERVICE_NAME, error: "downstream_timeout" });
    } else {
      res.status(502).json({
        service: SERVICE_NAME,
        error: "downstream_unavailable",
      });
    }
  }
});

app.get("/metrics", async (_req, res) => {
  res.set("Content-Type", register.contentType);
  res.send(await register.metrics());
});

// pod health check
app.get("/health", (_req, res) => {
  res.send("OK");
});

// pod readiness check
app.get("/ready", (_req, res) => {
  res.send("OK");
});

const server = app.listen(PORT, () => {
  console.log(
    `${SERVICE_NAME} is running on port ${PORT}, downstream: ${DOWNSTREAM_URL}`
  );
});

function shutdown(signal: string) {
  server.close(() => {
    console.log(`${SERVICE_NAME} is shutting down`);
    process.exit(0);
  });
  setTimeout(() => {
    console.log(`${SERVICE_NAME} is shutting down`);
    process.exit(1);
  }, 10000);
}

process.on("SIGINT", () => {
  shutdown("SIGINT");
});

process.on("SIGTERM", () => {
  shutdown("SIGTERM");
});
