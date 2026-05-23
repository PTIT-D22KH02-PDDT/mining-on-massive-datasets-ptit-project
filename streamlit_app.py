import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import plotly.graph_objects as go
import json
import logging
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="OTTO Recommender Pipeline Dashboard",
    page_icon=None,
    layout="wide",
)

st_autorefresh(interval=5000, key="monitoring_refresh")

import os
API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
st.sidebar.caption(f"Connected to API: {API_URL}")

if "last_updated" not in st.session_state:
    st.session_state.last_updated = None


def get_stats():
    try:
        resp = requests.get(f"{API_URL}/api/stats", timeout=5)
        resp.raise_for_status()
        st.session_state.last_updated = datetime.now()
        return resp.json()
    except requests.exceptions.Timeout:
        logger.error("API stats request timeout")
        return None
    except requests.exceptions.ConnectionError:
        logger.error("Cannot connect to API for stats")
        return None
    except requests.exceptions.HTTPError as e:
        logger.error(f"API stats HTTP error: {e}")
        return None
    except json.JSONDecodeError:
        logger.error("Invalid JSON response from API stats")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching stats: {e}")
        return None


def get_health():
    try:
        resp = requests.get(f"{API_URL}/api/health", timeout=5)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.Timeout:
        logger.error("API health request timeout")
        return None
    except requests.exceptions.ConnectionError:
        logger.error("Cannot connect to API for health")
        return None
    except requests.exceptions.HTTPError as e:
        logger.error(f"API health HTTP error: {e}")
        return None
    except json.JSONDecodeError:
        logger.error("Invalid JSON response from API health")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching health: {e}")
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
    "Spark Performance",
    "Model Evaluation",
    "Item Insights"
])

st.sidebar.markdown("---")
st.sidebar.header("System Health")
health = get_health()
if health:
    st.sidebar.success(f"API: {health.get('status', 'unknown').upper()}")
    redis_status = health.get('redis', {}).get('status', 'unknown')
    pg_status = health.get('postgres', {}).get('status', 'unknown')
    redis_mem = health.get('redis', {}).get('memory_mb', '-')
    pg_conns = health.get('postgres', {}).get('active_connections', '-')
    st.sidebar.info(f"Redis: {redis_status.upper()} [{redis_mem}]")
    st.sidebar.info(f"Postgres: {pg_status.upper()} [{pg_conns} conns]")
else:
    st.sidebar.error("API: OFFLINE")

st.sidebar.markdown("---")
if st.sidebar.button("Manual Refresh"):
    st.rerun()

# Data Freshness Indicator
if st.session_state.last_updated:
    ago = (datetime.now() - st.session_state.last_updated).total_seconds()
    if ago < 10:
        st.sidebar.success(f"Data fresh ({ago:.0f}s ago)")
    elif ago < 30:
        st.sidebar.warning(f"Data stale ({ago:.0f}s ago)")
    else:
        st.sidebar.error(f"Data outdated ({ago:.0f}s ago)")
else:
    st.sidebar.info("No data fetched yet")

# Lazy-Load Per Tab: each view fetches its own data

# --- View: Dashboard Overview ---
if view == "Dashboard Overview":
    stats = get_stats()
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
            hr = (hit_stats.get("hit_rate") or 0) * 100 if hit_stats else 0
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
    stats = get_stats()
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
                c1.metric("Click -> Cart", f"{(f_data.get('click_to_cart_rate') or 0)*100:.1f}%")
                c2.metric("Cart -> Order", f"{(f_data.get('cart_to_order_rate') or 0)*100:.1f}%")
                c3.metric("Click -> Order", f"{(f_data.get('click_to_order_rate') or 0)*100:.1f}%")
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
                # Deduplicate: keep latest row per window (streaming writes cumulative updates)
                df_h = df_h.sort_values('window_start').drop_duplicates(subset='window_start', keep='last')
                df_h = df_h.sort_values('window_start')
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
                c1.metric("Hit Rate (Conversion)", f"{(hr_stats.get('hit_rate') or 0)*100:.2f}%")
                c2.metric("Total Hits", hr_stats.get("total_hits", 0))
                c3.metric("Total Eval Actions", hr_stats.get("total_actions", 0))
                
                # Your awesome visual gauge chart
                rate = (hr_stats.get('hit_rate') or 0) * 100
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
    stats = get_stats()
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
    stats = get_stats()
    if stats:
        spark = stats.get("spark_metrics", [])
        if spark:
            df_spark = pd.DataFrame(spark)
            df_spark['timestamp'] = pd.to_datetime(df_spark['timestamp'])
            df_spark = df_spark.sort_values('timestamp')

            # 1. Input vs Processing Rate (line chart)
            st.markdown("**Input vs Processing Rate (rows/sec)**")
            fig_rate = px.line(df_spark, x='timestamp',
                              y=['input_rows_per_second', 'process_rows_per_second'],
                              template="plotly_dark", markers=True,
                              labels={'input_rows_per_second': 'Input (rows/s)',
                                      'process_rows_per_second': 'Process (rows/s)'})
            st.plotly_chart(fig_rate, use_container_width=True)

            # 2. Throughput Efficiency Ratio (process/input)
            df_spark['throughput_ratio'] = (
                df_spark['process_rows_per_second'] / df_spark['input_rows_per_second'].replace(0, float('nan'))
            )
            st.markdown("**Processing Efficiency Ratio (process/input)**")
            fig_eff = px.area(df_spark, x='timestamp', y='throughput_ratio',
                            template="plotly_dark", color_discrete_sequence=['#00CC96'])
            fig_eff.update_layout(height=300)
            st.plotly_chart(fig_eff, use_container_width=True)

            # 3. Batch Duration (area chart + alert)
            st.markdown("**Batch Duration (ms)**")
            ALERT_THRESHOLD_MS = 10000
            slow_batches = df_spark[df_spark['batch_duration_ms'] > ALERT_THRESHOLD_MS]
            if not slow_batches.empty:
                st.warning(f"⚠️ {len(slow_batches)} batches exceeded {ALERT_THRESHOLD_MS}ms threshold")
            fig_dur = px.area(df_spark, x='timestamp', y='batch_duration_ms',
                            template="plotly_dark", color_discrete_sequence=['#FFA15A'])
            st.plotly_chart(fig_dur, use_container_width=True)

            # 4. Recent Metrics Table
            st.markdown("**Recent Batch Metrics**")
            display_cols = ['timestamp', 'batch_id', 'input_rows_per_second',
                          'process_rows_per_second', 'batch_duration_ms']
            available = [c for c in display_cols if c in df_spark.columns]
            st.dataframe(df_spark[available].tail(10).sort_values('timestamp', ascending=False),
                        use_container_width=True)
        else:
            st.info("Waiting for Spark performance data...")

# --- View: Model Evaluation ---
elif view == "Model Evaluation":
    st.subheader("Model Quality Metrics")
    stats = get_stats()
    if stats:
        online_metrics_summary = stats.get("online_metrics_summary", [])
        online_metrics_trend = stats.get("online_metrics_trend", [])

        if online_metrics_summary:
            df_metrics = pd.DataFrame(online_metrics_summary)

            st.markdown("**Recall@20 by Recommendation Strategy**")
            recall_df = df_metrics[df_metrics['metric_name'] == 'recall@20']
            if not recall_df.empty:
                fig = px.bar(
                    recall_df, x='model_used', y='avg_value', color='model_used',
                    template="plotly_dark", labels={'avg_value': 'Recall@20', 'model_used': 'Model'}
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No Recall@20 data available yet.")

            st.markdown("**NDCG@20 by Model and Event Type**")
            ndcg_df = df_metrics[df_metrics['metric_name'] == 'ndcg@20']
            if not ndcg_df.empty:
                fig = px.bar(
                    ndcg_df, x='model_used', y='avg_value', color='event_type',
                    barmode='group', template="plotly_dark", labels={'avg_value': 'NDCG@20'}
                )
                st.plotly_chart(fig, use_container_width=True)

            st.markdown("**MRR@20 by Model**")
            mrr_df = df_metrics[df_metrics['metric_name'] == 'mrr@20']
            if not mrr_df.empty:
                fig = px.bar(
                    mrr_df, x='model_used', y='avg_value', color='model_used',
                    template="plotly_dark", labels={'avg_value': 'MRR@20'}
                )
                st.plotly_chart(fig, use_container_width=True)

            st.markdown("**Overall Metrics Summary**")
            st.dataframe(df_metrics, use_container_width=True)

            st.markdown("---")
            st.markdown("**Overall Weighted Recall@20**")
            wr_df = df_metrics[df_metrics['metric_name'] == 'weighted_recall@20']
            if not wr_df.empty:
                avg_wr = wr_df['avg_value'].mean() * 100
                fig = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=avg_wr,
                    title={'text': "Weighted Recall@20 (%)"},
                    gauge={
                        'axis': {'range': [0, 100]},
                        'bar': {'color': "darkblue"},
                        'steps': [
                            {'range': [0, 5], 'color': "red"},
                            {'range': [5, 15], 'color': "yellow"},
                            {'range': [15, 100], 'color': "green"}
                        ]
                    }
                )).update_layout(template="plotly_dark", height=300)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No Weighted Recall@20 data available yet.")
        else:
            st.info("No online evaluation metrics available yet. Start sending cart/order events to see model quality metrics.")

        if online_metrics_trend:
            st.markdown("---")
            st.markdown("**Recall@20 Trend by Model**")
            df_trend = pd.DataFrame(online_metrics_trend)
            if not df_trend.empty and 'latest_at' in df_trend.columns:
                df_trend['latest_at'] = pd.to_datetime(df_trend['latest_at'])
                fig = px.line(
                    df_trend, x='latest_at', y='avg_value', color='model_used',
                    template="plotly_dark", markers=True,
                    labels={'avg_value': 'Recall@20', 'model_used': 'Model'}
                )
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Cannot fetch stats from API. Ensure FastAPI is running.")

# --- View: Item Insights ---
elif view == "Item Insights":
    st.subheader("Item Conversion Insights")
    stats = get_stats()
    if stats:
        item_insights = stats.get("item_insights", [])
        if item_insights:
            df_items = pd.DataFrame(item_insights)
            df_items['aid'] = df_items['aid'].astype(str)

            MIN_CLICKS = st.slider("Minimum clicks to include", min_value=0, max_value=100, value=10)
            df_filtered = df_items[df_items['total_clicks'] >= MIN_CLICKS]

            st.markdown("**Hidden Gems — High Conversion, Low Visibility**")
            st.caption("Items với conversion rate cao nhưng ít click — ứng viên để boost recommendation")
            if not df_filtered.empty:
                fig_scatter = px.scatter(
                    df_filtered, x='total_clicks', y='click_to_order_rate',
                    size='total_orders', color='click_to_order_rate',
                    hover_data=['aid'], template="plotly_dark",
                    labels={'total_clicks': 'Total Clicks', 'click_to_order_rate': 'Click-to-Order Rate'},
                    color_continuous_scale='Viridis'
                )
                fig_scatter.add_hline(
                    y=df_filtered['click_to_order_rate'].quantile(0.75),
                    line_dash="dash", line_color="yellow",
                    annotation_text="Top 25% Conversion"
                )
                fig_scatter.add_vline(
                    x=df_filtered['total_clicks'].quantile(0.25),
                    line_dash="dash", line_color="red",
                    annotation_text="Bottom 25% Clicks"
                )
                st.plotly_chart(fig_scatter, use_container_width=True)

                hidden_gems = df_filtered[
                    (df_filtered['click_to_order_rate'] >= df_filtered['click_to_order_rate'].quantile(0.75)) &
                    (df_filtered['total_clicks'] <= df_filtered['total_clicks'].quantile(0.25))
                ]
                if not hidden_gems.empty:
                    st.success(f"Found {len(hidden_gems)} hidden gems")
                    st.dataframe(hidden_gems[['aid', 'total_clicks', 'total_orders', 'click_to_order_rate']].head(10), use_container_width=True)
            else:
                st.info(f"No items with >= {MIN_CLICKS} clicks.")

            st.markdown("---")
            st.markdown("**Top 20 Items by Click-to-Order Rate**")
            if not df_filtered.empty:
                top_conv = df_filtered.nlargest(20, 'click_to_order_rate')
                fig_bar = px.bar(
                    top_conv, x='aid', y='click_to_order_rate', color='total_orders',
                    template="plotly_dark", labels={'click_to_order_rate': 'Click-to-Order Rate', 'aid': 'Item ID'},
                )
                st.plotly_chart(fig_bar, use_container_width=True)
            else:
                st.info("No data available.")

            st.markdown("---")
            st.markdown("**Popularity vs Conversion — Bubble Chart**")
            st.caption("Bubble size = total orders. Cho thấy mối quan hệ giữa popularity và actual conversion")
            if not df_filtered.empty:
                fig_bubble = px.scatter(
                    df_filtered, x='total_clicks', y='click_to_cart_rate',
                    size='total_orders', color='total_carts',
                    hover_data=['aid'], template="plotly_dark",
                    labels={'total_clicks': 'Total Clicks', 'click_to_cart_rate': 'Click-to-Cart Rate'},
                    color_continuous_scale='Plasma'
                )
                fig_bubble.update_layout(yaxis_tickformat='.0%')
                st.plotly_chart(fig_bubble, use_container_width=True)

            st.markdown("---")
            st.markdown("**All Item Metrics**")
            st.dataframe(df_filtered.sort_values('total_clicks', ascending=False).head(50), use_container_width=True)
        else:
            st.info("No item insights data yet. Run the Spark streaming pipeline to populate stats_items.")
    else:
        st.warning("Cannot fetch stats from API. Ensure FastAPI is running.")

st.markdown("---")
st.caption("OTTO Recommender Hub - Unified Monitoring & Control")
