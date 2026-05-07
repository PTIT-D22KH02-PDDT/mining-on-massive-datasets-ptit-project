import os
import json
import torch
import numpy as np
import streamlit as st
import pytorch_lightning as py_light
import random
import math
from torch import nn, tensor, concat, diag, logical_and, logical_or, tile
from torch.nn import Dropout
from datetime import datetime
import traceback
from typing import List, Tuple

# --- SASRec Model Definition ---

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
        self.model = SASRec.load_from_checkpoint(checkpoint_path, map_location=device)
        self.model.eval()
        self.model.to(device)
        self.max_len = self.model.max_len
        self.num_items = self.model.num_items

    def _prepare_sequence(self, click_sequence: List[int]) -> Tuple[torch.Tensor, torch.Tensor]:
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
        logits = multiply_head_with_embedding(last_hidden, self.model.output_embedding.weight).squeeze(0)
        logits[0] = float("-inf")
        if exclude_clicked:
            for aid in click_sequence:
                idx = aid + 1
                if 0 < idx <= self.num_items:
                    logits[idx] = float("-inf")
        actual_k = min(k, self.num_items)
        top_scores_tensor, top_indices_tensor = torch.topk(logits, k=actual_k)
        top_aids = [aid - 1 for aid in top_indices_tensor.cpu().tolist()]
        top_scores = top_scores_tensor.cpu().tolist()
        return top_aids, top_scores

# --- Helpers ---

@st.cache_resource
def load_image_paths():
    json_path = "/kaggle/working/image_paths.json"
    if os.path.exists(json_path):
        with open(json_path, "r") as f:
            return json.load(f)
    return []

def get_image_for_aid(aid, all_images):
    if not all_images:
        return None
    return all_images[aid % len(all_images)]

# --- Streamlit UI ---

st.set_page_config(page_title="Demo Otto Recommender system", layout="wide")

@st.cache_resource
def get_inference_engine(checkpoint_path, device):
    if not os.path.exists(checkpoint_path):
        return None
    try:
        return SASRecInference(checkpoint_path, device=device)
    except:
        return None

all_images = load_image_paths()
num_images = len(all_images) if all_images else 1000000

# Initialize State
if 'history' not in st.session_state:
    st.session_state.history = []
if 'recs' not in st.session_state:
    st.session_state.recs = []

# Đảm bảo Catalog luôn có ít nhất 10 trang (240 sản phẩm)
if 'catalog' not in st.session_state or len(st.session_state.catalog) < 100:
    pool_size = max(240, min(num_images, 1000))
    st.session_state.catalog = random.sample(range(num_images), pool_size)

# Sidebar
with st.sidebar:
    st.title("Controls")
    ckpt_path = "/kaggle/input/models/sandaria/sasrec/pytorch/otto-dataset/1/sasrec-otto-epoch4-recall_cutoff_200.308.ckpt"
    device_opt = "cuda" if torch.cuda.is_available() else "cpu"
    st.divider()
    if st.button("New Catalog Pool"):
        pool_size = max(240, min(num_images, 1000))
        st.session_state.catalog = random.sample(range(num_images), pool_size)
        st.rerun()
    if st.button("Reset Everything"):
        st.session_state.history = []
        st.session_state.recs = []
        st.rerun()

engine = get_inference_engine(ckpt_path, device_opt)

st.title("Visual Recommendation Explorer")

if not engine:
    st.error("Model engine failed to load.")
    st.stop()

# --- Catalog with Pagination ---
st.header("Product Catalog")

items_per_page = 24
catalog_size = len(st.session_state.catalog)
total_pages = math.ceil(catalog_size / items_per_page)

# Cấu trúc điều khiển phân trang
c_pag1, c_pag2 = st.columns([1, 4])
with c_pag1:
    page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1, key="catalog_page_input")
with c_pag2:
    st.write("") 
    st.write(f"Items per page: **{items_per_page}** | Total items: **{catalog_size}**")
    st.info(f"You are on page **{page}** of **{total_pages}**")

start_idx = (page - 1) * items_per_page
end_idx = min(start_idx + items_per_page, catalog_size)
current_items = st.session_state.catalog[start_idx:end_idx]

# Grid display
rows = math.ceil(len(current_items) / 4)
for r in range(rows):
    grid_cols = st.columns(4)
    for c in range(4):
        idx = r * 4 + c
        if idx < catalog_size:
            if idx < len(current_items):
                aid = current_items[idx]
                with grid_cols[c]:
                    img = get_image_for_aid(aid, all_images)
                    if img:
                        st.image(img, use_container_width=True)
                    
                    # Main Click Action (View)
                    if st.button(f"View Item {aid}", key=f"c_{aid}_{idx}_{page}", use_container_width=True):
                        st.session_state.history.append({"aid": aid, "type": "clicks"})
                        st.toast(f"Clicked Item {aid}")
                    
                    # Side Actions (Cart & Buy)
                    btn_c1, btn_c2 = st.columns(2)
                    if btn_c1.button("Cart", key=f"a_{aid}_{idx}_{page}", use_container_width=True):
                        st.session_state.history.append({"aid": aid, "type": "carts"})
                        st.toast(f"Added {aid} to Cart")
                        
                    if btn_c2.button("Buy", key=f"o_{aid}_{idx}_{page}", use_container_width=True):
                        st.session_state.history.append({"aid": aid, "type": "orders"})
                        st.toast(f"Ordered {aid}")

st.divider()

# --- History ---
if st.session_state.history:
    st.subheader("Your Journey")
    h_cols = st.columns(min(len(st.session_state.history), 10))
    for i, event in enumerate(reversed(st.session_state.history[:10])):
        with h_cols[i % 10]:
            h_img = get_image_for_aid(event['aid'], all_images)
            if h_img: st.image(h_img, width=80)
            st.caption(f"{event['type']}\nID: {event['aid']}")

st.divider()

# --- Recommendation Logic ---
if st.button("GENERATE RECOMMENDATIONS", use_container_width=True, type="primary"):
    if st.session_state.history:
        with st.spinner("Calculating..."):
            aids = [e['aid'] for e in st.session_state.history]
            top_aids, top_scores = engine.recommend_topk(aids, k=20)
            st.session_state.recs = list(zip(top_aids, top_scores))
    else:
        st.warning("Interact with products first!")

# --- Results (Top 20) ---
if st.session_state.recs:
    st.header("Top 20 Recommendations")
    res_cols = st.columns(4)
    for i, item in enumerate(st.session_state.recs):
        if isinstance(item, (tuple, list)) and len(item) == 2:
            r_aid, score = item
        else:
            r_aid = item
            score = 0.0
            
        with res_cols[i % 4]:
            r_img = get_image_for_aid(r_aid, all_images)
            if r_img:
                st.image(r_img, use_container_width=True)
            
            # Show ID
            st.write(f"**ID: {r_aid}**")
            
            with st.popover("Details"):
                st.write(f"Confidence Score: **{score:.4f}**")
                st.write(f"Item ID: `{r_aid}`")
