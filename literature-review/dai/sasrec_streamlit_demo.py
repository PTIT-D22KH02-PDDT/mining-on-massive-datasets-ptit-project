import os
import json
import torch
import numpy as np
import streamlit as st
import pytorch_lightning as py_light
from torch import nn, tensor, concat, diag, logical_and, logical_or, tile
from torch.nn import Dropout
from datetime import datetime
import traceback
from typing import List, Tuple

# --- SASRec Model Definition (from sasrec-inference.ipynb) ---

def multiply_head_with_embedding(prediction_head, embeddings):
    return prediction_head.matmul(embeddings.transpose(-1, -2))

class DynamicPositionEmbedding(nn.Module):
    def __init__(self, max_len, dimension):
        super(DynamicPositionEmbedding, self).__init__()
        self.max_len = max_len
        self.embedding = nn.Embedding(max_len, dimension)
        self.pos_indices = torch.arange(0, self.max_len, dtype=torch.int)
        self.register_buffer('pos_indices_const', self.pos_indices)

    def forward(self, x):
        seq_len = x.shape[1]
        return self.embedding(self.pos_indices_const[-seq_len:]) + x

class SASRec(py_light.LightningModule):
    def __init__(self,
                 hidden_size,
                 dropout_rate,
                 max_len,
                 num_items,
                 batch_size,
                 num_layers=2,
                 output_bias=False,
                 share_embeddings=True,
                 **kwargs):
        super(SASRec, self).__init__()
        self.hidden_size = hidden_size
        self.num_items = num_items
        self.max_len = max_len
        self.output_bias = output_bias
        self.share_embeddings = share_embeddings
        self.num_layers = num_layers
        
        self.future_mask = torch.triu(torch.ones(max_len, max_len) * float('-inf'), diagonal=1)
        self.register_buffer('future_mask_const', self.future_mask)
        self.register_buffer('seq_diag_const', ~diag(torch.ones(max_len, dtype=torch.bool)))
        self.register_buffer('bias_ones', torch.ones([batch_size, max_len, 1]))

        if output_bias and share_embeddings:
            self.item_embedding = nn.Embedding(num_items + 1, hidden_size + 1, padding_idx=0)
        else:
            self.item_embedding = nn.Embedding(num_items + 1, hidden_size, padding_idx=0)
        
        self.positional_embedding_layer = DynamicPositionEmbedding(max_len, hidden_size)

        if share_embeddings:
            self.output_embedding = self.item_embedding
        elif (not share_embeddings) and output_bias:
            self.output_embedding = nn.Embedding(num_items + 1, hidden_size + 1, padding_idx=0)
        else:
            self.output_embedding = nn.Embedding(num_items + 1, hidden_size, padding_idx=0)

        self.norm = nn.LayerNorm([hidden_size])
        self.input_dropout = Dropout(dropout_rate)
        
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_size,
            nhead=1,
            dim_feedforward=hidden_size,
            dropout=dropout_rate,
            batch_first=True,
            norm_first=True
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers, norm=self.norm)
        self.merge_attn_mask = True

    def merge_attn_masks(self, padding_mask):
        batch_size = padding_mask.shape[0]
        seq_len = padding_mask.shape[1]
        padding_mask_broadcast = ~padding_mask.bool().unsqueeze(1)
        future_masks = tile(self.future_mask_const[:seq_len, :seq_len], (batch_size, 1, 1))
        merged_masks = logical_or(padding_mask_broadcast, future_masks)
        diag_masks = tile(self.seq_diag_const[:seq_len, :seq_len], (batch_size, 1, 1))
        return logical_and(diag_masks, merged_masks)

    def forward(self, item_indices, mask):
        att_mask = self.merge_attn_masks(mask)
        items = self.item_embedding(item_indices)[:, :, :-1] if self.output_bias and self.share_embeddings else self.item_embedding(item_indices)
        x = items * np.sqrt(self.hidden_size)
        x = self.positional_embedding_layer(x)
        x = self.encoder(self.input_dropout(x), att_mask)
        return concat([x, self.bias_ones], dim=-1) if self.output_bias else x

class SASRecInference:
    def __init__(self, checkpoint_path, device=None):
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        # Load the model directly using the defined class
        self.model = SASRec.load_from_checkpoint(checkpoint_path, map_location=device)
        self.model.eval()
        self.model.to(device)
        self.max_len = self.model.max_len
        self.num_items = self.model.num_items

    def _prepare_sequence(self, click_sequence: List[int]) -> Tuple[torch.Tensor, torch.Tensor]:
        # Sequence comes as raw AIDs, SasRec expects shifted AIDs (aid + 1)
        seq = [aid + 1 for aid in click_sequence[-self.max_len:]]
        seq_len = len(seq)
        pad_len = self.max_len - seq_len
        padded = [0] * pad_len + seq
        mask_arr = [0.0] * pad_len + [1.0] * seq_len
        
        item_indices = torch.tensor([padded], dtype=torch.long, device=self.device)
        mask = torch.tensor([mask_arr], dtype=torch.float, device=self.device)
        return item_indices, mask

    @torch.no_grad()
    def recommend_topk(self, click_sequence: List[int], k=20, exclude_clicked=True) -> Tuple[List[int], List[float]]:
        if not click_sequence:
            return [], []
            
        item_indices, mask = self._prepare_sequence(click_sequence)
        x_hat = self.model.forward(item_indices, mask)
        last_hidden = x_hat[:, -1, :]
        
        logits = multiply_head_with_embedding(
            last_hidden,
            self.model.output_embedding.weight,
        ).squeeze(0)
        
        logits[0] = float("-inf") # padding
        
        if exclude_clicked:
            for aid in click_sequence:
                idx = aid + 1
                if 0 < idx <= self.num_items:
                    logits[idx] = float("-inf")
                    
        actual_k = min(k, self.num_items)
        top_scores_tensor, top_indices_tensor = torch.topk(logits, k=actual_k)
        
        top_aids_shifted = top_indices_tensor.cpu().tolist()
        top_scores = top_scores_tensor.cpu().tolist()
        
        # Convert back to original OTTO AIDs
        top_aids = [aid - 1 for aid in top_aids_shifted]
        return top_aids, top_scores

# --- Streamlit Application ---

st.set_page_config(
    page_title="SasRec Recommender",
    layout="wide"
)

# Helper for logging
def log_event(message, payload=None):
    try:
        ts = datetime.now().isoformat()
        with open("sasrec_demo.log", "a") as f:
            f.write(f"[{ts}] {message}\n")
            if payload:
                f.write(f"{json.dumps(payload)}\n")
    except: pass

@st.cache_resource
def get_inference_engine(checkpoint_path, device):
    if not os.path.exists(checkpoint_path):
        return None
    try:
        return SASRecInference(checkpoint_path, device=device)
    except Exception as e:
        st.error(f"Error loading model: {e}")
        return None

@st.cache_data
def load_sample_data(file_path, num_samples=20):
    if not os.path.exists(file_path):
        return []
    samples = []
    try:
        with open(file_path, 'r') as f:
            for i, line in enumerate(f):
                if i >= num_samples: break
                samples.append(json.loads(line))
    except Exception as e:
        st.sidebar.error(f"Error loading data: {e}")
    return samples

# --- Sidebar Configuration ---
with st.sidebar:
    st.header("Settings")
    
    # Checkpoint path
    default_ckpt = "/kaggle/input/models/sandaria/sasrec/pytorch/otto-dataset/1/sasrec-otto-epoch4-recall_cutoff_200.308.ckpt"
    ckpt_path = st.text_input("Model Checkpoint Path", value=default_ckpt)
    
    device_option = st.selectbox("Inference Device", ["cpu", "cuda"] if torch.cuda.is_available() else ["cpu"])
    
    st.divider()
    st.header("Data Configuration")
    test_data_path = "/kaggle/input/competitions/otto-recommender-system/test.jsonl"
    sample_size = st.slider("Samples to Load", 10, 200, 50)
    
    if st.button("Reload Data"):
        st.cache_data.clear()
        st.rerun()

# --- Load Model ---
engine = get_inference_engine(ckpt_path, device_option)

# --- App State ---
if 'history' not in st.session_state:
    st.session_state.history = []
if 'recs' not in st.session_state:
    st.session_state.recs = []

# --- Main UI ---
st.title("SasRec Recommender Demo")

if not engine:
    st.error(f"Model checkpoint not found at: {ckpt_path}")

col_left, col_right = st.columns(2)

with col_left:
    st.header("Simulation")
    
    # Sample selection
    samples = load_sample_data(test_data_path, sample_size)
    if samples:
        selected_session = st.selectbox(
            "Load a session",
            options=[None] + samples,
            format_func=lambda x: f"Session {x['session']} ({len(x['events'])} events)" if x else "Manual..."
        )
        if selected_session and st.button("Load Session"):
            st.session_state.history = [{"aid": e['aid'], "type": e['type']} for e in selected_session['events']]
            st.session_state.recs = []
            st.rerun()

    st.subheader("Add Action")
    c1, c2 = st.columns([2, 1])
    with c1:
        aid_input = st.number_input("Item ID", min_value=0, step=1, value=0)
    with c2:
        action_type = st.selectbox("Type", ["clicks", "carts", "orders"])
    
    if st.button("Add to Sequence"):
        st.session_state.history.append({"aid": aid_input, "type": action_type})
        st.session_state.recs = []
        st.rerun()

    if st.session_state.history:
        st.subheader("Current Sequence")
        st.table(st.session_state.history[-10:])
        
        if st.button("Reset Session"):
            st.session_state.history = []
            st.session_state.recs = []
            st.rerun()

with col_right:
    st.header("Recommendations")
    
    if st.button("Predict"):
        if engine and st.session_state.history:
            with st.spinner("Predicting..."):
                aids = [e['aid'] for e in st.session_state.history]
                top_aids, top_scores = engine.recommend_topk(aids, k=20)
                st.session_state.recs = list(zip(top_aids, top_scores))
        else:
            st.warning("Model not loaded or history empty.")

    if st.session_state.recs:
        # Display as a clean table
        recs_df = [{"Rank": i+1, "Item AID": aid, "Score": f"{score:.4f}"} 
                   for i, (aid, score) in enumerate(st.session_state.recs)]
        st.table(recs_df)
    else:
        st.info("No recommendations yet.")

# --- Info ---
st.divider()
with st.expander("Technical Details"):
    if engine:
        st.write(f"Max Sequence Length: {engine.max_len}")
        st.write(f"Total Items: {engine.num_items}")
    else:
        st.write("Model not loaded.")
