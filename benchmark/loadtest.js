import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate } from 'k6/metrics';

const BASE_URL = 'http://localhost:8000';
const sessionPool = Array.from({length: 2000}, (_, i) => 100000 + i);
const eventTypes = ['clicks', 'carts', 'orders'];

const apiLatency = new Trend('api_latency');
const errorRate = new Rate('api_errors');

export const options = {
  stages: [
    { duration: '1m', target: 30 },
    { duration: '1m', target: 80 },
    { duration: '1m', target: 0 },
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
