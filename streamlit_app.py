import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(
    page_title="OTTO Recommender Pipeline Dashboard",
    page_icon=None,
    layout="wide",
)

API_URL = "http://localhost:8000"

def get_stats():
    try:
        resp = requests.get(f"{API_URL}/api/stats", timeout=2)
        return resp.json()
    except:
        return None

def get_health():
    try:
        resp = requests.get(f"{API_URL}/api/health", timeout=2)
        return resp.json()
    except:
        return None

st.title("OTTO Recommender Hub")
st.markdown("""
    *Hệ thống gợi ý đa mục tiêu với chiến lược **Hybrid Inference** & **Real-time Monitoring**.*
""")
st.markdown("---")

# --- Sidebar Navigation ---
st.sidebar.title("Navigation")
view = st.sidebar.radio("Go to", [
    "Dashboard Overview", 
    "Advanced Analytics", 
    "Anomaly Detection", 
    "Recommendation Demo", 
    "Spark Performance"
])

st.sidebar.markdown("---")
st.sidebar.header("System Health")
health = get_health()
if health:
    st.sidebar.success(f"API: {health['status'].upper()}")
    st.sidebar.info(f"Redis: {health['redis'].upper()}")
    st.sidebar.info(f"Postgres: {health['postgres'].upper()}")
else:
    st.sidebar.error("API: OFFLINE")

st.sidebar.markdown("---")
if st.sidebar.button("Manual Refresh"):
    st.rerun()

# Global Data Fetching
stats = get_stats()

# --- View: Dashboard Overview ---
if view == "Dashboard Overview":
    if stats:
        # 1. Key Metrics (Combined: 5 columns including Hit Rate)
        m1, m2, m3, m4, m5 = st.columns(5)
        with m1:
            st.metric("Active Sessions", stats.get("active_sessions", 0))
        with m2:
            st.metric("Total Events", stats.get("collected_events", 0))
        with m3:
            pred_stats = stats.get("prediction_stats", {})
            st.metric("Total Predictions", pred_stats.get("total_predictions", 0))
        with m4:
            avg_latency = pred_stats.get("avg_latency_ms") or 0
            st.metric("Avg Latency", f"{avg_latency:.1f} ms")
        with m5:
            hit_stats = stats.get("hit_rate_stats", {})
            hr = hit_stats.get("hit_rate", 0) * 100 if hit_stats else 0
            st.metric("Hit Rate", f"{hr:.2f}%")

        st.markdown("---")

        # 2. Charts
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Event Distribution")
            ev_dist = stats.get("event_distribution", [])
            if ev_dist:
                df_ev = pd.DataFrame(ev_dist)
                st.plotly_chart(px.bar(df_ev, x='event_type', y='count', color='event_type', template="plotly_dark"), use_container_width=True)
            else:
                st.info("No event distribution data yet.")
        
        with c2:
            st.subheader("Model Usage (Hybrid Strategy)")
            usage = stats.get("model_usage", [])
            if usage:
                df_usage = pd.DataFrame(usage)
                fig = px.pie(df_usage, values='count', names='model_used', hole=.4, template="plotly_dark", color_discrete_sequence=px.colors.qualitative.T10)
                fig.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No predictions logged yet.")

        # 3. Popular Items
        st.subheader("Top Popular Items")
        pop_type = st.radio("Item Type", ["clicks", "carts", "orders"], horizontal=True)
        try:
            pop_resp = requests.get(f"{API_URL}/api/popular/{pop_type}?limit=10")
            if pop_resp.status_code == 200:
                df_pop = pd.DataFrame(pop_resp.json().get("items", []))
                if not df_pop.empty:
                    df_pop['aid'] = df_pop['aid'].astype(str)
                    st.plotly_chart(px.bar(df_pop, x='aid', y='count', color='count', template="plotly_dark"), use_container_width=True)
                else:
                    st.info("No popular items computed for this type. Run the batch job.")
        except:
            st.warning("Could not load popular items.")
    else:
        st.warning("Cannot fetch stats from API. Ensure FastAPI is running.")

# --- View: Advanced Analytics ---
elif view == "Advanced Analytics":
    st.subheader("Advanced Analytics")
    if stats:
        t1, t2, t3, t4, t5 = st.tabs(["Conversion Funnel", "Model Performance", "Hourly Traffic", "Session Insights", "Online Evaluation"])
        
        with t1:
            # My Fallback Logic for Real-time Funnel vs Batch Funnel
            f_data = stats.get("funnel_stats", {})
            if not f_data:
                hourly = stats.get("hourly_stats", [])
                if hourly:
                    latest = hourly[-1]
                    f_data = {
                        "total_sessions": latest.get("unique_sessions", 0),
                        "sessions_with_clicks": latest.get("total_clicks", 0),
                        "sessions_with_carts": latest.get("total_carts", 0),
                        "sessions_with_orders": latest.get("total_orders", 0)
                    }

            if f_data:
                df_f = pd.DataFrame({
                    "Stage": ["Sessions", "Clicks", "Carts", "Orders"], 
                    "Count": [f_data.get(k, 0) for k in ["total_sessions", "sessions_with_clicks", "sessions_with_carts", "sessions_with_orders"]]
                })
                # Reversing the order to ensure it looks like a funnel (wide at top) if Plotly default is bottom-up
                df_f = df_f.iloc[::-1]
                # Your awesome funnel chart + My customized colors
                fig = px.funnel(df_f, x='Count', y='Stage', template="plotly_dark", color='Stage', 
                                color_discrete_sequence=["#636EFA", "#EF553B", "#00CC96", "#AB63FA"])
                st.plotly_chart(fig, use_container_width=True)
                
                c1, c2, c3 = st.columns(3)
                c1.metric("Click -> Cart", f"{f_data.get('click_to_cart_rate', 0)*100:.1f}%")
                c2.metric("Cart -> Order", f"{f_data.get('cart_to_order_rate', 0)*100:.1f}%")
                c3.metric("Click -> Order", f"{f_data.get('click_to_order_rate', 0)*100:.1f}%")
            else:
                st.info("No funnel data available.")
            
        with t2:
            st.subheader("Real-time Model Performance Comparison")
            adv_funnel = stats.get("advanced_funnel", [])
            if adv_funnel:
                df_adv = pd.DataFrame(adv_funnel)
                
                # Plot 1: Conversion Rate per Model
                st.markdown("**Click-to-Order Rate by Recommendation Strategy**")
                fig_rate = px.bar(
                    df_adv, x='model_used', y='click_to_order_rate', 
                    color='model_used', text_auto='.2%',
                    template="plotly_dark", title="Efficiency (Conversion Rate)"
                )
                st.plotly_chart(fig_rate, use_container_width=True)
                
                # Plot 2: Total Impact (Grouped Bar)
                st.markdown("**Raw Funnel Counts per Model**")
                df_melted = df_adv.melt(
                    id_vars=['model_used'], 
                    value_vars=['total_sessions', 'sessions_with_clicks', 'sessions_with_carts', 'sessions_with_orders'],
                    var_name='Stage', value_name='Count'
                )
                fig_compare = px.bar(
                    df_melted, x='Stage', y='Count', color='model_used', 
                    barmode='group', template="plotly_dark"
                )
                st.plotly_chart(fig_compare, use_container_width=True)
                
                # Data Table
                st.markdown("**Detailed Metrics**")
                st.dataframe(df_adv, use_container_width=True)
            else:
                st.info("No advanced model performance data yet. Start generating recommendations and events.")
            
        with t3:
            hourly = stats.get("hourly_stats", [])
            if hourly:
                df_h = pd.DataFrame(hourly)
                df_h['window_start'] = pd.to_datetime(df_h['window_start'])
                st.plotly_chart(px.area(df_h, x='window_start', y=['total_clicks', 'total_carts', 'total_orders'], template="plotly_dark"), use_container_width=True)
            else:
                st.info("No hourly traffic data.")

        with t4:
            sess_dist = stats.get("session_distribution", [])
            if sess_dist:
                df_s = pd.DataFrame(sess_dist)
                st.plotly_chart(px.bar(df_s, x='session_type', y='count', color='avg_length', template="plotly_dark"), use_container_width=True)
            else:
                st.info("Run Batch Analysis to see session segmentation.")

        with t5:
            hr_stats = stats.get("hit_rate_stats", {})
            if hr_stats and hr_stats.get("total_actions", 0) > 0:
                st.subheader("Real-time Recommendation Accuracy")
                c1, c2, c3 = st.columns(3)
                c1.metric("Hit Rate (Conversion)", f"{hr_stats.get('hit_rate', 0)*100:.2f}%")
                c2.metric("Total Hits", hr_stats.get("total_hits", 0))
                c3.metric("Total Eval Actions", hr_stats.get("total_actions", 0))
                
                # Your awesome visual gauge chart
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
elif view == "Anomaly Detection":
    st.subheader("Real-time Anomaly Detection")
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
elif view == "Recommendation Demo":
    st.subheader("Test Recommendations")
    col_a, col_b = st.columns([1, 2])
    with col_a:
        s_id = st.number_input("Session ID", value=888, step=1)
        aid = st.number_input("Item ID", value=1000, step=1)
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
            st.info(f"Model: {res['model_used'].upper()} | Latency: {res['latency_ms']}ms")
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
elif view == "Spark Performance":
    st.subheader("Spark Streaming Metrics")
    if stats:
        spark = stats.get("spark_metrics", [])
        if spark:
            df_spark = pd.DataFrame(spark)
            df_spark['timestamp'] = pd.to_datetime(df_spark['timestamp'])
            
            st.markdown("**Processing vs Input Rate (rows/sec)**")
            # Sửa lại process_rows_per_second cho chuẩn schema DB
            st.plotly_chart(px.line(df_spark, x='timestamp', y=['input_rows_per_second', 'process_rows_per_second'], template="plotly_dark"), use_container_width=True)
            
            st.markdown("**Batch Duration (ms)**")
            # My area chart for duration is visually better for time series
            fig_dur = px.area(df_spark, x='timestamp', y='batch_duration_ms', template="plotly_dark", color_discrete_sequence=['#FFA15A'])
            st.plotly_chart(fig_dur, use_container_width=True)
        else:
            st.info("Waiting for Spark performance data...")

st.markdown("---")
st.caption("OTTO Recommender Hub - Unified Monitoring & Control")
