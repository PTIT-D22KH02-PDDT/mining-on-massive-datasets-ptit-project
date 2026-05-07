"""
Streamlit Demo: Otto user action simulation

This demo does not use mock product metadata.
It allows you to simulate a user session by adding actions one by one,
then send the current session history through the recommendation model.
"""

import os
import pickle
import json
import streamlit as st
import numpy as np
from datetime import datetime
import traceback

st.set_page_config(page_title="Otto Action Simulation Demo", page_icon="🧠", layout="wide")

@st.cache_resource
def load_embeddings_and_mappings():
    embeddings_path = "item_embeddings.npy"
    mappings_path = "demo_mappings.pkl"
    if not os.path.exists(embeddings_path) or not os.path.exists(mappings_path):
        return None, None
    embeddings = np.load(embeddings_path, mmap_mode="r")
    with open(mappings_path, "rb") as f:
        mappings = pickle.load(f)
    return embeddings, mappings

@st.cache_data
def load_sample_sessions():
    samples_path = "demo_sessions.json"
    if not os.path.exists(samples_path):
        return []
    with open(samples_path, "r") as f:
        return json.load(f)


def flatten_history_aids(session_history):
    return [entry["aid"] for entry in session_history if isinstance(entry, dict) and "aid" in entry]


def log_event(message, payload=None):
    try:
        ts = datetime.utcnow().isoformat()
        with open("streamlit_demo_actions.log", "a") as f:
            f.write(f"[{ts}] {message}\n")
            if payload is not None:
                f.write(f"{payload}\n")
    except Exception:
        pass


def get_recommendations(session_history, embeddings, aid2idx, idx2aid, num_sessions, top_k=10):
    history_aids = flatten_history_aids(session_history)
    if not history_aids or embeddings is None:
        return []

    valid_items = [aid for aid in history_aids if aid in aid2idx]
    if not valid_items:
        return []

    item_indices = [aid2idx[aid] - num_sessions for aid in valid_items]
    history_embs = embeddings[item_indices]
    user_emb = np.mean(history_embs, axis=0, keepdims=True).astype(np.float32)
    similarities = np.dot(embeddings, user_emb.T).squeeze()
    top_indices = np.argsort(similarities)[::-1]

    recommendations = []
    for idx in top_indices:
        aid = idx2aid.get(idx + num_sessions)
        if not aid:
            continue
        if aid in valid_items:
            continue
        recommendations.append((aid, float(similarities[idx])))
        if len(recommendations) >= top_k:
            break
    return recommendations

if "history" not in st.session_state:
    st.session_state.history = []
if "recommendations" not in st.session_state:
    st.session_state.recommendations = []
if "last_action" not in st.session_state:
    st.session_state.last_action = None

embeddings, mappings = load_embeddings_and_mappings()
sample_sessions = load_sample_sessions()

st.title("🧠 Otto User Action Simulation")
st.markdown(
    "Use the left controls to simulate user actions one by one, then press Predict to see model recommendations."
)

col1, col2 = st.columns([2, 5])

with col1:
    st.header("Simulation Controls")

    if embeddings is None or mappings is None:
        st.error("item_embeddings.npy or demo_mappings.pkl not found. Please run setup_demo.py first.")
    else:
        aid2idx = mappings.get("aid2idx", {})
        idx2aid = mappings.get("idx2aid", {})
        num_sessions = mappings.get("num_sessions", 0)
        available_aids = sorted(aid2idx.keys())

        st.markdown("Start with an empty session and add user actions manually.")

        def add_user_action(aid, action_type):
            if aid is None:
                return
            if "history" not in st.session_state or not isinstance(st.session_state.history, list):
                st.session_state.history = []
            st.session_state.history.append({"aid": aid, "action": action_type})
            st.session_state.last_action = f"{action_type} AID {aid}"
            st.session_state.recommendations = []

        with st.expander("Add user action"):
            if st.session_state.history:
                st.write(f"Current session length: {len(st.session_state.history)} action(s)")
            else:
                st.write("Current session is empty.")

            sample_aids = []
            if sample_sessions:
                sample_aids = sorted(
                    {
                        event["aid"]
                        for session in sample_sessions
                        for event in session.get("events", [])
                        if "aid" in event
                    }
                )[:50]

            action_type = st.selectbox(
                "Action type",
                ["Click", "Add to cart", "Purchase"],
                key="action_type",
            )

            action_aid_input = st.text_input("Enter item AID", value="", key="action_aid_input")
            action_aid_choice = st.selectbox(
                "Or choose a sample AID",
                sample_aids,
                format_func=lambda x: str(x),
                key="action_aid_choice",
            ) if sample_aids else None

            if st.button("Add action", key="add_action"):
                try:
                    log_event("Add action clicked", {
                        "history_len": len(st.session_state.history),
                        "action_type": action_type,
                        "input": action_aid_input,
                        "choice": action_aid_choice,
                    })
                    aid = None
                    if action_aid_input.strip():
                        try:
                            aid = int(action_aid_input.strip())
                        except ValueError:
                            st.warning("AID phải là số nguyên. Vui lòng nhập đúng định dạng.")
                    elif action_aid_choice is not None:
                        aid = int(action_aid_choice)

                    if aid is not None:
                        add_user_action(aid, action_type)
                    else:
                        st.warning("Vui lòng nhập hoặc chọn một AID hợp lệ.")
                except Exception as e:
                    log_event("Add action error", traceback.format_exc())
                    st.error(f"Add action error: {e}")

        if st.button("Predict recommendations", key="predict_button"):
            try:
                st.session_state.recommendations = get_recommendations(
                    st.session_state.history,
                    embeddings,
                    aid2idx,
                    idx2aid,
                    num_sessions,
                    top_k=15,
                )
            except Exception as e:
                st.session_state.recommendations = []
                st.error(f"Recommendation error: {e}")

        if st.button("Reset session"):
            st.session_state.history = []
            st.session_state.recommendations = []
            st.session_state.last_action = None

with col2:
    st.header("Session History")
    if st.session_state.history:
        filtered_history = [
            entry for entry in st.session_state.history
            if isinstance(entry, dict) and "aid" in entry and "action" in entry
        ]
        st.write(f"Total actions: {len(filtered_history)}")
        history_table = [
            {"Step": i + 1, "AID": entry["aid"], "Action": entry["action"]}
            for i, entry in enumerate(filtered_history)
        ]
        st.table(history_table)
        if st.session_state.last_action is not None:
            st.success(f"Last action: {st.session_state.last_action}")
    else:
        st.info("No actions yet. Add an item AID as a user action.")

    st.markdown("---")
    st.header("Recommendations")
    if st.session_state.recommendations:
        for rank, (aid, score) in enumerate(st.session_state.recommendations, start=1):
            st.write(f"{rank}. AID {aid} — similarity {score:.4f}")
    else:
        st.info("No recommendations yet. Add an action or press Predict.")

st.markdown("---")
st.markdown(
    "### Notes\n"
    "- This demo uses only Otto AIDs and the trained embeddings.\n"
    "- No mock product metadata is displayed.\n"
    "- Each action has a type: Click, Add to cart, Purchase.\n"
    "- When you add an action, the session history is updated.\n"
    "- If auto-predict is enabled, recommendations refresh after each new action.\n"
    "- You can also press `Predict recommendations` manually."
)
