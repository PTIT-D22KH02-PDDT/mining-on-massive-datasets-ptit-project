import { useState, useEffect, useCallback, useRef } from "react";

const API_BASE = "http://localhost:8000";

const SESSION_ID = (() => {
  const stored = sessionStorage.getItem("rec_session_id");
  if (stored) return parseInt(stored);
  const id = Math.floor(Math.random() * 1000000);
  sessionStorage.setItem("rec_session_id", id);
  return id;
})();

const getImage = (aid) => `/images/fashion/${aid % 1000}.jpg`;

const PLACEHOLDER_COLORS = [
  "#E8D5C4","#C4D5E8","#D5E8C4","#E8C4D5","#D5C4E8",
  "#E8E4C4","#C4E8E4","#E4C4E8","#C4E8D5","#E8D4C4",
];
const getColor = (aid) => PLACEHOLDER_COLORS[aid % PLACEHOLDER_COLORS.length];

const EventBadge = ({ type }) => {
  const map = {
    clicks: { bg: "#E6F1FB", color: "#0C447C", label: "Click" },
    carts:  { bg: "#FAEEDA", color: "#633806", label: "Cart" },
    orders: { bg: "#EAF3DE", color: "#27500A", label: "Order" },
  };
  const s = map[type] || { bg: "#F1EFE8", color: "#2C2C2A", label: type };
  return (
    <span style={{
      background: s.bg, color: s.color, fontSize: 12, fontWeight: 600,
      padding: "3px 10px", borderRadius: 6, flexShrink: 0,
    }}>{s.label}</span>
  );
};

/* ── Single product card ── */
const ProductCard = ({ aid, onClick, width = 160, imgHeight = 160 }) => {
  const [imgErr, setImgErr] = useState(false);
  return (
    <div
      onClick={() => onClick?.(aid)}
      style={{
        background: "#fff",
        border: "0.5px solid #e0ddd6",
        borderRadius: 12,
        overflow: "hidden",
        cursor: onClick ? "pointer" : "default",
        transition: "transform 0.15s",
        flexShrink: 0,
        width,
      }}
      onMouseEnter={e => { if (onClick) e.currentTarget.style.transform = "translateY(-3px)"; }}
      onMouseLeave={e => { e.currentTarget.style.transform = "none"; }}
    >
      <div style={{
        width: "100%", height: imgHeight,
        background: getColor(aid),
        display: "flex", alignItems: "center", justifyContent: "center",
        overflow: "hidden",
      }}>
        {!imgErr ? (
          <img
            src={getImage(aid)}
            alt={`Item ${aid}`}
            onError={() => setImgErr(true)}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
          />
        ) : (
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: 28, opacity: 0.3 }}>🛍️</div>
            <div style={{ fontSize: 11, color: "#999", marginTop: 4 }}>{aid}</div>
          </div>
        )}
      </div>
      <div style={{ padding: "10px 12px" }}>
        <div style={{ fontWeight: 600, fontSize: 13, color: "#1a1a1a" }}>#{aid}</div>
        {onClick && <div style={{ fontSize: 11, color: "#aaa", marginTop: 2 }}>Nhấn để xem</div>}
      </div>
    </div>
  );
};

/* ── Auto-scrolling marquee row ── */
const MarqueeRow = ({ items, onProductClick }) => {
  const trackRef = useRef(null);
  const animRef  = useRef(null);
  const posRef   = useRef(0);
  const pauseRef = useRef(false);

  useEffect(() => {
    if (!items.length) return;
    const track = trackRef.current;
    if (!track) return;

    const SPEED = 0.3; // px per frame

    const step = () => {
      if (!pauseRef.current) {
        posRef.current += SPEED;
        const half = track.scrollWidth / 2;
        if (posRef.current >= half) posRef.current -= half;
        track.style.transform = `translateX(-${posRef.current}px)`;
      }
      animRef.current = requestAnimationFrame(step);
    };
    animRef.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(animRef.current);
  }, [items]);

  // duplicate items so the loop is seamless
  const doubled = [...items, ...items];

  return (
    <div
      style={{ overflow: "hidden", width: "100%" }}
      onMouseEnter={() => { pauseRef.current = true; }}
      onMouseLeave={() => { pauseRef.current = false; }}
    >
      <div
        ref={trackRef}
        style={{ display: "flex", gap: 12, width: "max-content", willChange: "transform" }}
      >
        {doubled.map((aid, i) => (
          <ProductCard key={`${aid}-${i}`} aid={aid} onClick={onProductClick} width={170} imgHeight={150} />
        ))}
      </div>
    </div>
  );
};

/* ── Static horizontal scroll (for rec section) ── */
const HScroll = ({ items, onProductClick, cardWidth = 150, imgH = 130 }) => (
  <div style={{ display: "flex", gap: 10, overflowX: "auto", paddingBottom: 6 }}>
    {items.map((aid, i) => (
      <ProductCard key={`${aid}-${i}`} aid={aid} onClick={onProductClick} width={cardWidth} imgHeight={imgH} />
    ))}
  </div>
);

/* ── Recommendation panel ── */
const RecSection = ({ recommendations, title = "Gợi ý cho bạn", onProductClick }) => {
  if (!recommendations) return null;
  const clicks = recommendations.clicks || [];
  const carts  = recommendations.carts  || [];
  const orders = recommendations.orders || [];
  if (!clicks.length && !carts.length && !orders.length) return null;

  const rows = [
    { label: "Có thể bạn sẽ xem",          items: clicks, type: "clicks" },
    { label: "Có thể bạn sẽ thêm vào giỏ", items: carts,  type: "carts"  },
    { label: "Có thể bạn sẽ mua",           items: orders, type: "orders" },
  ].filter(r => r.items.length);

  return (
    <div style={{
      background: "#fafaf8", border: "0.5px solid #e8e5de",
      borderRadius: 14, padding: "20px 22px",
    }}>
      <div style={{ fontWeight: 700, fontSize: 16, color: "#1a1a1a", marginBottom: 18 }}>
        🤖 {title}
      </div>
      {rows.map(({ label, items, type }) => (
        <div key={type} style={{ marginBottom: 20 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
            <EventBadge type={type} />
            <span style={{ fontSize: 13, color: "#555" }}>{label}</span>
          </div>
          <HScroll items={items.slice(0, 10)} onProductClick={onProductClick} />
        </div>
      ))}
    </div>
  );
};

/* ── Popular section (marquee) ── */
const PopularSection = ({ popularData, onProductClick }) => (
  <div>
    <div style={{ fontWeight: 800, fontSize: 22, color: "#1a1a1a", marginBottom: 24 }}>
      🔥 Sản phẩm nổi bật
    </div>
    {[
      { key: "clicks", label: "Xem nhiều",          icon: "👁️" },
      { key: "carts",  label: "Thêm giỏ hàng nhiều", icon: "🛒" },
      { key: "orders", label: "Mua nhiều",            icon: "💳" },
    ].map(({ key, label, icon }) => {
      const items = (popularData[key] || []).map(i => i.aid ?? i).filter(Boolean);
      return (
        <div key={key} style={{ marginBottom: 32 }}>
          <div style={{ fontWeight: 600, fontSize: 15, color: "#333", marginBottom: 12 }}>
            {icon} {label}
          </div>
          {items.length > 0
            ? <MarqueeRow items={items} onProductClick={onProductClick} />
            : <div style={{ fontSize: 13, color: "#bbb" }}>Chưa có dữ liệu</div>
          }
        </div>
      );
    })}
  </div>
);

/* ── Home page ── */
const HomePage = ({ onProductClick, recommendations, popularData }) => (
  <div style={{ padding: "32px 40px", maxWidth: 1400, margin: "0 auto" }}>
    <div style={{
      display: "grid",
      gridTemplateColumns: "minmax(0, 1fr) 420px",
      gap: 40,
      alignItems: "start",
    }}>
      <PopularSection popularData={popularData} onProductClick={onProductClick} />
      <div style={{ position: "sticky", top: 72 }}>
        {recommendations ? (
          <RecSection recommendations={recommendations} onProductClick={onProductClick} />
        ) : (
          <div style={{
            background: "#fafaf8", border: "0.5px solid #e8e5de",
            borderRadius: 14, padding: "36px 24px",
            color: "#bbb", fontSize: 14, textAlign: "center",
          }}>
            <div style={{ fontSize: 40, marginBottom: 12 }}>✨</div>
            Gợi ý cá nhân hóa sẽ xuất hiện<br />sau khi bạn tương tác với sản phẩm.
          </div>
        )}
      </div>
    </div>
  </div>
);

/* ── Product detail page ── */
const ProductDetailPage = ({ aid, onBack, recommendations, onSendEvent, loading, onProductClick }) => {
  const [imgErr, setImgErr] = useState(false);

  return (
    <div style={{ padding: "32px 40px", maxWidth: 1400, margin: "0 auto" }}>
      <button
        onClick={onBack}
        style={{
          background: "none", border: "0.5px solid #d0ccc4",
          borderRadius: 8, padding: "8px 16px", cursor: "pointer",
          fontSize: 14, color: "#555", marginBottom: 28,
        }}
      >
        ← Quay lại
      </button>

      <div style={{
        display: "grid",
        gridTemplateColumns: "400px minmax(0, 1fr)",
        gap: 40, alignItems: "start",
      }}>
        {/* Left */}
        <div>
          <div style={{
            background: getColor(aid), borderRadius: 18, overflow: "hidden",
            aspectRatio: "1/1", marginBottom: 24,
          }}>
            {!imgErr ? (
              <img
                src={getImage(aid)}
                alt={`Product ${aid}`}
                onError={() => setImgErr(true)}
                style={{ width: "100%", height: "100%", objectFit: "cover" }}
              />
            ) : (
              <div style={{
                width: "100%", height: "100%",
                display: "flex", flexDirection: "column",
                alignItems: "center", justifyContent: "center",
              }}>
                <div style={{ fontSize: 72, opacity: 0.25 }}>🛍️</div>
                <div style={{ fontSize: 14, color: "#888", marginTop: 12 }}>ID: {aid}</div>
              </div>
            )}
          </div>

          <div style={{
            background: "#fff", border: "0.5px solid #e0ddd6",
            borderRadius: 14, padding: "22px 24px",
          }}>
            <div style={{ fontSize: 26, fontWeight: 800, color: "#1a1a1a", marginBottom: 4 }}>
              Item #{aid}
            </div>
            <div style={{ fontSize: 13, color: "#aaa", marginBottom: 22 }}>
              Product ID: {aid} · Fashion Collection
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <button
                onClick={() => onSendEvent("carts")}
                disabled={loading}
                style={{
                  background: "#FAEEDA", color: "#633806",
                  border: "none", borderRadius: 12, padding: "15px 8px",
                  cursor: loading ? "not-allowed" : "pointer",
                  fontWeight: 700, fontSize: 15, opacity: loading ? 0.5 : 1,
                  transition: "opacity 0.15s",
                }}
              >
                🛒 Thêm giỏ
              </button>
              <button
                onClick={() => onSendEvent("orders")}
                disabled={loading}
                style={{
                  background: "#EAF3DE", color: "#27500A",
                  border: "none", borderRadius: 12, padding: "15px 8px",
                  cursor: loading ? "not-allowed" : "pointer",
                  fontWeight: 700, fontSize: 15, opacity: loading ? 0.5 : 1,
                  transition: "opacity 0.15s",
                }}
              >
                💳 Mua ngay
              </button>
            </div>
          </div>
        </div>

        {/* Right: recs — pass onProductClick so items are navigable */}
        <div>
          {loading && (
            <div style={{
              background: "#fff8ed", border: "0.5px solid #f5d08a",
              borderRadius: 10, padding: "12px 16px",
              fontSize: 13, color: "#7a5a1a", marginBottom: 16,
            }}>
              ⟳ Đang cập nhật gợi ý...
            </div>
          )}
          {recommendations ? (
            <RecSection
              recommendations={recommendations}
              title="Gợi ý dựa trên hành vi của bạn"
              onProductClick={onProductClick}
            />
          ) : (
            <div style={{
              background: "#fafaf8", border: "0.5px solid #e8e5de",
              borderRadius: 14, padding: "36px 24px",
              color: "#bbb", fontSize: 14, textAlign: "center",
            }}>
              <div style={{ fontSize: 40, marginBottom: 12 }}>🤖</div>
              Gợi ý sẽ xuất hiện sau khi hệ thống xử lý...
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

/* ── History page ── */
const HistoryPage = ({ history }) => (
  <div style={{ padding: "32px 40px", maxWidth: 760, margin: "0 auto" }}>
    <div style={{ fontWeight: 800, fontSize: 22, color: "#1a1a1a", marginBottom: 24 }}>
      📜 Lịch sử hoạt động
    </div>
    <div style={{
      background: "#fff", border: "0.5px solid #e0ddd6",
      borderRadius: 14, overflow: "hidden",
    }}>
      <div style={{
        padding: "14px 20px", background: "#fafaf8",
        borderBottom: "0.5px solid #e8e5de", fontSize: 13, color: "#888",
      }}>
        Session: <span style={{ fontFamily: "monospace", color: "#555" }}>{SESSION_ID}</span>
        {" · "}{history.length} sự kiện
      </div>
      {history.length === 0 ? (
        <div style={{ padding: 48, textAlign: "center", color: "#bbb", fontSize: 14 }}>
          Chưa có hoạt động nào
        </div>
      ) : (
        [...history].reverse().map((h, i) => (
          <div key={i} style={{
            display: "flex", alignItems: "center", gap: 14,
            padding: "13px 20px",
            borderBottom: i < history.length - 1 ? "0.5px solid #f0ede6" : "none",
          }}>
            <div style={{ fontSize: 12, color: "#bbb", minWidth: 48, fontFamily: "monospace" }}>
              {h.time}
            </div>
            <EventBadge type={h.type} />
            <div style={{ fontSize: 14, color: "#333" }}>
              Item <span style={{ fontWeight: 700 }}>#{h.aid}</span>
            </div>
            {h.latency !== undefined && (
              <div style={{ marginLeft: "auto", fontSize: 12, color: "#bbb" }}>
                {h.latency}ms
              </div>
            )}
          </div>
        ))
      )}
    </div>
  </div>
);

/* ── Root ── */
export default function App() {
  const [page, setPage]               = useState("home");
  const [currentAid, setCurrentAid]   = useState(null);
  const [recommendations, setRecs]    = useState(null);
  const [popularData, setPopularData] = useState({ clicks: [], carts: [], orders: [] });
  const [history, setHistory]         = useState([]);
  const [loading, setLoading]         = useState(false);

  const fetchPopular = useCallback(async () => {
    try {
      const [a, b, c] = await Promise.all([
        fetch(`${API_BASE}/api/popular/clicks?limit=20`).then(r => r.json()),
        fetch(`${API_BASE}/api/popular/carts?limit=20`).then(r => r.json()),
        fetch(`${API_BASE}/api/popular/orders?limit=20`).then(r => r.json()),
      ]);
      setPopularData({ clicks: a.items||[], carts: b.items||[], orders: c.items||[] });
    } catch {
      setPopularData({
        clicks: Array.from({length:20},(_,i)=>({ aid: 101+i*13 })),
        carts:  Array.from({length:20},(_,i)=>({ aid: 201+i*17 })),
        orders: Array.from({length:20},(_,i)=>({ aid: 301+i*11 })),
      });
    }
  }, []);

  useEffect(() => { fetchPopular(); }, [fetchPopular]);

  const sendEvent = useCallback(async (aid, type) => {
    setLoading(true);
    const now = new Date();
    const time = `${now.getHours().toString().padStart(2,"0")}:${now.getMinutes().toString().padStart(2,"0")}`;
    try {
      const res = await fetch(`${API_BASE}/api/event`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: SESSION_ID, aid, type }),
      });
      const data = await res.json();
      setRecs(data.recommendations);
      setHistory(prev => [...prev, { aid, type, time, latency: data.latency_ms }]);
    } catch {
      setRecs({
        clicks: Array.from({length:8},(_,i)=>aid+i*7+1),
        carts:  Array.from({length:8},(_,i)=>aid+i*11+2),
        orders: Array.from({length:8},(_,i)=>aid+i*13+3),
      });
      setHistory(prev => [...prev, { aid, type, time }]);
    } finally {
      setLoading(false);
    }
  }, []);

  // Unified handler: navigate to product + fire click event
  const handleProductClick = useCallback(async (aid) => {
    setCurrentAid(aid);
    setPage("product");
    await sendEvent(aid, "clicks");
  }, [sendEvent]);

  return (
    <div style={{
      minHeight: "100vh", width: "100%",
      background: "#f7f5f0",
      fontFamily: "'Segoe UI', system-ui, sans-serif",
    }}>
      <style>{`
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        html, body, #root { width: 100%; min-height: 100vh; background: #f7f5f0; }
        ::-webkit-scrollbar { height: 5px; width: 5px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #d0ccc4; border-radius: 4px; }
        button { font-family: inherit; }
      `}</style>

      {/* Navbar */}
      <nav style={{
        background: "#fff", borderBottom: "0.5px solid #e0ddd6",
        padding: "0 40px", height: 56,
        display: "flex", alignItems: "center", justifyContent: "space-between",
        position: "sticky", top: 0, zIndex: 100, width: "100%",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 24 }}>
          <button
            onClick={() => setPage("home")}
            style={{
              background: "none", border: "none", cursor: "pointer",
              fontWeight: 800, fontSize: 16, color: "#1a1a1a", letterSpacing: -0.5,
            }}
          >
            🛍️ RecStore
          </button>
          <div style={{ display: "flex", gap: 4 }}>
            {[
              { key: "home",    label: "🏠 Trang chủ" },
              { key: "history", label: "📜 Lịch sử" },
            ].map(({ key, label }) => (
              <button
                key={key}
                onClick={() => setPage(key)}
                style={{
                  background: page === key ? "#f0ede6" : "none",
                  border: "none", cursor: "pointer",
                  borderRadius: 8, padding: "6px 14px",
                  fontSize: 14,
                  color: page === key ? "#1a1a1a" : "#666",
                  fontWeight: page === key ? 700 : 400,
                  transition: "all 0.15s",
                }}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{
            fontSize: 12, color: "#aaa", background: "#f5f3ee",
            borderRadius: 6, padding: "4px 10px", fontFamily: "monospace",
          }}>
            session: {SESSION_ID}
          </div>
          <div style={{
            width: 9, height: 9, borderRadius: "50%",
            background: loading ? "#EF9F27" : "#639922",
            transition: "background 0.3s",
          }} title={loading ? "Processing..." : "Ready"} />
        </div>
      </nav>

      {page === "home" && (
        <HomePage
          onProductClick={handleProductClick}
          recommendations={recommendations}
          popularData={popularData}
        />
      )}
      {page === "product" && currentAid !== null && (
        <ProductDetailPage
          aid={currentAid}
          onBack={() => setPage("home")}
          recommendations={recommendations}
          onSendEvent={(type) => sendEvent(currentAid, type)}
          onProductClick={handleProductClick}
          loading={loading}
        />
      )}
      {page === "history" && <HistoryPage history={history} />}
    </div>
  );
}