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

const fault = {
  errorRate: process.env.FEATURE_NEW_PRICING === "true" ? 0.3 : 0,
  latencyMs: 0, // 每个请求额外等待的毫秒数
  leakMbPerSec: 0, // 每秒泄漏多少 MB 内存，0 表示不泄漏
};

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

let leakedMemory: Buffer[] = [];
let leakedTimer: NodeJS.Timeout | null = null;

const app = express();

function recordMetrics(start: number, req: express.Request, status: number) {
  const duration = Date.now() - start;
  const label = {
    method: req.method,
    route: req.route?.path ?? "unmatched",
    status: status,
  };
  httpRequestsDuration.observe(label, duration / 1000);
  httpRequestsTotal.inc(label);
}

app.use((req, res, next) => {
  const start = Date.now();
  let recorded = false;

  const record = (status: number) => {
    if (recorded) return;
    recorded = true;
    recordMetrics(start, req, status);
  };
  res.on("finish", () => record(res.statusCode));
  res.on("close", () => record(res.writableFinished ? res.statusCode : 499));
  next();
});

app.use(express.json());

app.get("/admin/fault", (_req, res) => {
  return res.json(fault);
});

app.post("/admin/fault", (req, res) => {
  const { errorRate, latencyMs, leakMbPerSec } = req.body ?? {};
  if (errorRate !== undefined) {
    if (typeof errorRate !== "number" || errorRate < 0 || errorRate > 1) {
      return res.status(400).json({ message: "Invalid error rate" });
    }
  }
  if (latencyMs !== undefined) {
    if (typeof latencyMs !== "number" || latencyMs < 0) {
      return res.status(400).json({ message: "Invalid latency" });
    }
  }
  if (leakMbPerSec !== undefined) {
    if (typeof leakMbPerSec !== "number" || leakMbPerSec < 0) {
      return res.status(400).json({ message: "Invalid leak memory" });
    }
  }
  fault.errorRate = errorRate ?? fault.errorRate;
  fault.latencyMs = latencyMs ?? fault.latencyMs;
  fault.leakMbPerSec = leakMbPerSec ?? fault.leakMbPerSec;

  if (leakMbPerSec !== undefined) {
    if (leakedTimer) {
      clearInterval(leakedTimer);
      leakedTimer = null;
    }
    if (leakMbPerSec === 0) {
      leakedMemory = [];
    } else {
      leakedTimer = setInterval(() => {
        leakedMemory.push(
          Buffer.alloc(Math.floor(leakMbPerSec * 1024 * 1024), 1)
        );
      }, 1000);
    }
  }
  console.log(
    JSON.stringify({
      level: "warn",
      service: SERVICE_NAME,
      msg: "fault updated",
      fault,
    })
  );
  return res.json(fault);
});

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
app.get("/api/work", async (_req, res) => {
  // Simulate errors
  if (fault.latencyMs > 0) {
    await sleep(fault.latencyMs);
  }
  if (Math.random() < fault.errorRate) {
    console.log(
      JSON.stringify({
        level: "error",
        service: SERVICE_NAME,
        msg: "failed to process request: connection reset",
      })
    );
    res.status(500).json({ service: SERVICE_NAME, error: "internal_error" });
    return;
  }
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
