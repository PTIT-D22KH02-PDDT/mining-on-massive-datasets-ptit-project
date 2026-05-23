import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate } from 'k6/metrics';

const BASE_URL = __ENV.API_BASE_URL || 'http://localhost:8000';
const sessionPool = Array.from({length: 2000}, (_, i) => 100000 + i);
const eventTypes = ['clicks', 'carts', 'orders'];

const apiLatency = new Trend('api_latency');
const errorRate = new Rate('api_errors');

export const options = {
  stages: [
    { duration: '2m', target: 30 },    // Ramp to 30 VUs
    { duration: '2m', target: 60 },    // Ramp to 60 VUs
    { duration: '1m', target: 80 },    // Ramp to 80 VUs
    { duration: '2m', target: 80 },    // Steady-state at 80 VUs
    { duration: '1m', target: 0 },     // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'],
    http_req_failed: ['rate<0.01'],
  },
};

export default function () {
  const sessionId = sessionPool[Math.floor(Math.random() * sessionPool.length)];
  const eventType = eventTypes[Math.floor(Math.random() * 3)];
  const payload = JSON.stringify({
    session_id: sessionId,
    aid: Math.floor(Math.random() * 1850000),
    type: eventType,
  });

  const res = http.post(`${BASE_URL}/api/event`, payload, {
    headers: { 'Content-Type': 'application/json' },
    timeout: '10s',
  });

  apiLatency.add(res.timings.duration);
  check(res, { 'status 200': (r) => r.status === 200 }) || errorRate.add(1);

  sleep(Math.random() * 1 + 0.3);
}

function fmtMs(ms) {
  if (ms >= 1000) return (ms / 1000).toFixed(2) + 's';
  return ms.toFixed(1) + 'ms';
}

function bar(n, max, w) {
  const len = max > 0 ? Math.round((n / max) * w) : 0;
  return '█'.repeat(len) + '░'.repeat(Math.max(0, w - len));
}

export function handleSummary(data) {
  const d = data.metrics.http_req_duration.values;
  const err = data.metrics.http_req_failed.values;
  const iter = data.metrics.iterations.values;
  const durMs = data.state.testRunDurationMs;
  const throughput = durMs > 0 ? (iter.count || 0) / (durMs / 1000) : 0;
  const p95 = d['p(95)'] || 0;
  const errRate = (err.rate || 0) * 100;
  const latencyOk = p95 < 500;
  const errOk = (err.rate || 0) < 0.01;

  const w = 30;
  const maxLat = Math.max(d.max || 0, 1);
  const points = [
    ['avg', d.avg],
    ['min', d.min],
    ['med', d.med],
    ['p(90)', d['p(90)']],
    ['p(95)', d['p(95)']],
    ['max', d.max],
  ];

  const summary =
`\n══════════════════════════════════════════
  OTTO API — K6 SUMMARY
══════════════════════════════════════════

  Requests:     ${data.metrics.http_reqs.values.count} total
  Throughput:   ${throughput.toFixed(1)} req/s
  Duration:     ${(durMs / 1000).toFixed(0)}s

── Latency ───────────────────────────────
${points.map(([l, v]) => `  ${l.padStart(6)}: ${fmtMs(v).padStart(8)}  ${bar(v, maxLat, w)}`).join('\n')}
── SLA ───────────────────────────────────
  P95 < 500ms:  ${fmtMs(p95)}  ${latencyOk ? '✓ PASS' : '✗ FAIL'}
  Error < 1%:   ${errRate.toFixed(2)}%      ${errOk ? '✓ PASS' : '✗ FAIL'}
══════════════════════════════════════════\n`;

  const ts = __ENV.BENCHMARK_TS || new Date().toISOString().replace(/[:.]/g, '-');
  const outDir = __ENV.RESULTS_DIR || '.';
  const outFile = `${outDir}/k6_summary_${ts}.json`;
  return {
    stdout: summary,
    [outFile]: JSON.stringify(data, null, 2),
  };
}
