"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const express_1 = __importDefault(require("express"));
const prom_client_1 = require("prom-client");
const SERVICE_NAME = process.env.SERVICE_NAME ?? "unknown";
const DOWNSTREAM_URL = process.env.DOWNSTREAM_URL;
const PORT = Number(process.env.PORT ?? 8080);
const httpRequestsTotal = new prom_client_1.Counter({
    name: "http_requests_total",
    help: "Total number of HTTP requests",
    labelNames: ["method", "route", "status"],
});
const httpRequestsDuration = new prom_client_1.Histogram({
    name: "http_request_duration_seconds",
    help: "Total number of HTTP request seconds",
    buckets: [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10],
    labelNames: ["method", "route", "status"],
});
(0, prom_client_1.collectDefaultMetrics)();
const app = (0, express_1.default)();
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
    }
    catch (error) {
        if (error instanceof Error && error.name === "TimeoutError") {
            res
                .status(504)
                .json({ service: SERVICE_NAME, error: "downstream_timeout" });
        }
        else {
            res.status(502).json({
                service: SERVICE_NAME,
                error: "downstream_unavailable",
            });
        }
    }
});
app.get("/metrics", async (_req, res) => {
    res.set("Content-Type", prom_client_1.register.contentType);
    res.send(await prom_client_1.register.metrics());
});
// pod health check
app.get("/health", (_req, res) => {
    res.send("OK");
});
// pod readiness check
app.get("/ready", (_req, res) => {
    res.send("OK");
});
app.listen(PORT, () => {
    console.log(`${SERVICE_NAME} is running on port ${PORT}, downstream: ${DOWNSTREAM_URL}`);
});
