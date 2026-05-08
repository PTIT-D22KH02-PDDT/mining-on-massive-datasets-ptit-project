import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(
    page_title="OTTO Recommender Pipeline Dashboard",
    page_icon="🤖",
    layout="wide",
)

API_URL = "http://localhost:8000"

def get_stats():
    try:
        resp = requests.get(f"{API_URL}/api/stats")
        return resp.json()
    except:
        return None

def get_health():
    try:
        resp = requests.get(f"{API_URL}/api/health")
        return resp.json()
    except:
        return None


st.title("🤖 OTTO Recommender Hub")
st.markdown("---")

# --- Sidebar Navigation ---
st.sidebar.title("🧭 Navigation")
view = st.sidebar.radio("Go to", [
    "📈 Dashboard Overview", 
    "🔬 Advanced Analytics", 
    "🚨 Anomaly Detection", 
    "🎯 Recommendation Demo", 
    "⚡ Spark Performance"
])

st.sidebar.markdown("---")
st.sidebar.header("System Health")
health = get_health()
if health:
    st.sidebar.success(f"API: {health['status'].upper()}")
    st.sidebar.info(f"Redis: {health['redis']}")
    st.sidebar.info(f"Postgres: {health['postgres']}")
else:
    st.sidebar.error("API: OFFLINE")

st.sidebar.markdown("---")
if st.sidebar.button("Manual Refresh"):
    st.rerun()

# Global Data Fetching
stats = get_stats()

# --- View: Dashboard Overview ---
if view == "📈 Dashboard Overview":
    if stats:
        # 1. Key Metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Active Sessions", stats["active_sessions"])
        with col2:
            st.metric("Collected Events", stats["collected_events"])
        with col3:
            pred_stats = stats.get("prediction_stats", {})
            st.metric("Total Predictions", pred_stats.get("total_predictions", 0))
        with col4:
            avg_latency = pred_stats.get("avg_latency_ms") or 0
            st.metric("Avg Latency", f"{avg_latency:.1f} ms")

        st.markdown("---")

        # 2. Charts
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Event Distribution")
            ev_dist = stats.get("event_distribution", [])
            if ev_dist:
                df_ev = pd.DataFrame(ev_dist)
                st.plotly_chart(px.bar(df_ev, x='event_type', y='count', color='event_type', template="plotly_dark"), use_container_width=True)
        
        with c2:
            st.subheader("Model Usage")
            usage = stats.get("model_usage", [])
            if usage:
                st.plotly_chart(px.pie(pd.DataFrame(usage), values='count', names='model_used', hole=.4, template="plotly_dark"), use_container_width=True)

        # 3. Popular Items
        st.subheader("🔥 Top Popular Items")
        pop_type = st.radio("Item Type", ["clicks", "carts", "orders"], horizontal=True)
        try:
            pop_resp = requests.get(f"{API_URL}/api/popular/{pop_type}?limit=10")
            if pop_resp.status_code == 200:
                df_pop = pd.DataFrame(pop_resp.json().get("items", []))
                if not df_pop.empty:
                    df_pop['aid'] = df_pop['aid'].astype(str)
                    st.plotly_chart(px.bar(df_pop, x='aid', y='count', color='count', template="plotly_dark"), use_container_width=True)
        except:
            st.warning("Could not load popular items.")

# --- View: Advanced Analytics ---
elif view == "🔬 Advanced Analytics":
    st.subheader("🔬 Advanced Batch Analytics")
    if stats:
        t1, t2, t3, t4 = st.tabs(["🎯 Conversion Funnel", "⏰ Hourly Traffic", "👥 Session Insights", "📈 Online Evaluation"])
        
        with t1:
            f_data = stats.get("funnel_stats", {})
            if f_data:
                df_f = pd.DataFrame({
                    "Stage": ["Sessions", "Clicks", "Carts", "Orders"], 
                    "Count": [f_data.get(k, 0) for k in ["total_sessions", "sessions_with_clicks", "sessions_with_carts", "sessions_with_orders"]]
                })
                st.plotly_chart(px.funnel(df_f, x='Count', y='Stage', template="plotly_dark"), use_container_width=True)
                
                c1, c2, c3 = st.columns(3)
                c1.metric("Click -> Cart", f"{f_data.get('click_to_cart_rate', 0)*100:.1f}%")
                c2.metric("Cart -> Order", f"{f_data.get('cart_to_order_rate', 0)*100:.1f}%")
                c3.metric("Click -> Order", f"{f_data.get('click_to_order_rate', 0)*100:.1f}%")
            
        with t2:
            hourly = stats.get("hourly_stats", [])
            if hourly:
                df_h = pd.DataFrame(hourly)
                df_h['window_start'] = pd.to_datetime(df_h['window_start'])
                st.plotly_chart(px.area(df_h, x='window_start', y=['total_clicks', 'total_carts', 'total_orders'], template="plotly_dark"), use_container_width=True)

        with t3:
            sess_dist = stats.get("session_distribution", [])
            if sess_dist:
                df_s = pd.DataFrame(sess_dist)
                st.plotly_chart(px.bar(df_s, x='session_type', y='count', color='avg_length', template="plotly_dark"), use_container_width=True)

        with t4:
            hr_stats = stats.get("hit_rate_stats", {})
            if hr_stats and hr_stats.get("total_actions", 0) > 0:
                st.subheader("🎯 Real-time Recommendation Accuracy")
                c1, c2, c3 = st.columns(3)
                c1.metric("Hit Rate (Conversion)", f"{hr_stats.get('hit_rate', 0)*100:.2f}%")
                c2.metric("Total Hits", hr_stats.get("total_hits", 0))
                c3.metric("Total Eval Actions", hr_stats.get("total_actions", 0))
                
                # Visual Gauge
                rate = hr_stats.get('hit_rate', 0) * 100
                st.plotly_chart(go.Figure(go.Indicator(
                    mode = "gauge+number",
                    value = rate,
                    title = {'text': "Hit Rate %"},
                    gauge = {'axis': {'range': [0, 100]}, 'bar': {'color': "darkblue"}, 'steps': [{'range': [0, 5], 'color': "red"}, {'range': [5, 15], 'color': "yellow"}, {'range': [15, 100], 'color': "green"}]}
                )).update_layout(template="plotly_dark", height=300), use_container_width=True)
            else:
                st.info("No online evaluation data yet. Start sending order/cart events to see conversion accuracy.")

# --- View: Anomaly Detection ---
elif view == "🚨 Anomaly Detection":
    st.subheader("🚨 Real-time Anomaly Detection")
    if stats:
        anomalies = stats.get("anomaly_logs", [])
        if anomalies:
            df_a = pd.DataFrame(anomalies)
            st.warning(f"Detected {len(df_a)} anomaly logs in the last window.")
            st.dataframe(df_a, use_container_width=True)
            
            st.subheader("Anomaly Type Breakdown")
            st.plotly_chart(px.pie(df_a, names='anomaly_type', hole=.4, template="plotly_dark"), use_container_width=True)
        else:
            st.success("No recent anomalies detected. System is healthy.")

# --- View: Recommendation Demo ---
elif view == "🎯 Recommendation Demo":
    st.subheader("🎯 Test Recommendations")
    col_a, col_b = st.columns([1, 2])
    with col_a:
        s_id = st.number_input("Session ID", value=12345, step=1)
        aid = st.number_input("Article ID", value=1, step=1)
        etype = st.selectbox("Action Type", ["clicks", "carts", "orders"])
        if st.button("Submit Event"):
            resp = requests.post(f"{API_URL}/api/event", json={"session_id": s_id, "aid": aid, "type": etype})
            if resp.status_code == 200:
                st.session_state["demo_res"] = resp.json()
                st.session_state["demo_sid"] = s_id
                st.success("Event tracked!")
    
    with col_b:
        if "demo_res" in st.session_state:
            res = st.session_state["demo_res"]
            st.info(f"Model: {res['model_used']} | Latency: {res['latency_ms']}ms")
            recs = res["recommendations"]
            t1, t2, t3 = st.tabs(["Clicks", "Carts", "Orders"])
            t1.write(recs.get("clicks", []))
            t2.write(recs.get("carts", []))
            t3.write(recs.get("orders", []))
            
            # Show History
            hist_resp = requests.get(f"{API_URL}/api/session/{st.session_state['demo_sid']}")
            if hist_resp.status_code == 200:
                st.write("**Current Session History:**")
                st.dataframe(pd.DataFrame(hist_resp.json()["events"]), use_container_width=True)

# --- View: Spark Performance ---
elif view == "⚡ Spark Performance":
    st.subheader("⚡ Spark Streaming Metrics")
    if stats:
        spark = stats.get("spark_metrics", [])
        if spark:
            df_spark = pd.DataFrame(spark)
            df_spark['timestamp'] = pd.to_datetime(df_spark['timestamp'])
            st.markdown("**Processing vs Input Rate (rows/sec)**")
            st.plotly_chart(px.line(df_spark, x='timestamp', y=['input_rows_per_second', 'processed_rows_per_second'], template="plotly_dark"), use_container_width=True)
            st.markdown("**Batch Duration (ms)**")
            st.plotly_chart(px.bar(df_spark, x='timestamp', y='batch_duration_ms', color='num_input_rows', template="plotly_dark"), use_container_width=True)
        else:
            st.info("Waiting for Spark performance data...")

st.markdown("---")
st.caption("OTTO Recommender Hub — Unified Monitoring & Control")
