"""
SASRec Recommender - Deep Learning Sequential Recommendation.
This module implements the SASRec model (Self-Attention based Sequential Recommendation).
It supports two modes:
1. Local: Runs PyTorch locally (requires torch).
2. Remote: Calls a remote Kaggle/Server host via HTTP (no local torch required).
"""

import os
import logging
import random
import requests
from typing import List, Tuple, Dict, Optional

logger = logging.getLogger(__name__)

# Try to import torch for local mode, but don't fail if missing
try:
    import torch
    import numpy as np
    from torch import nn, tile, logical_and, logical_or, diag
    from torch.nn import Dropout
    import pytorch_lightning as py_light
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    logger.warning("Torch not found. SASRec will only work in Remote mode.")

# --- Remote Configuration ---
# Set this to your Kaggle/ngrok URL
SASREC_REMOTE_URL = os.getenv("SASREC_REMOTE_URL", "") # Example: "https://your-ngrok-id.ngrok-free.app"

# --- SASRec Model Definition (Only needed for Local Mode) ---
if HAS_TORCH:
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
            return torch.concat([x, self.bias_ones], dim=-1) if self.output_bias else x

class SASRecRecommender:
    """Wrapper for SASRec model. Can work locally or via remote Kaggle bridge."""
    
    def __init__(self, checkpoint_path: str = None, remote_url: str = SASREC_REMOTE_URL):
        self.remote_url = remote_url
        self.model = None
        self.device = "cpu"
        
        if self.remote_url:
            logger.info(f"SASRec initialized in REMOTE mode via {self.remote_url}")
        elif HAS_TORCH:
            self.checkpoint_path = checkpoint_path or "models/sasrec/sasrec-otto.ckpt"
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            if os.path.exists(self.checkpoint_path):
                try:
                    self.model = SASRec.load_from_checkpoint(self.checkpoint_path, map_location=self.device)
                    self.model.eval()
                    self.model.to(self.device)
                    logger.info(f"SASRec initialized in LOCAL mode from {self.checkpoint_path}")
                except Exception as e:
                    logger.error(f"Failed to load SASRec locally: {e}")
            else:
                logger.warning(f"SASRec checkpoint not found. Using dummy mode.")
        else:
            logger.warning("Torch not available and no Remote URL set. Using dummy mode.")

    def _predict_remote(self, session_aids: List[int], top_k: int) -> List[int]:
        """Call the Kaggle host for recommendations."""
        try:
            resp = requests.post(
                f"{self.remote_url}/recommend",
                json={"session_aids": session_aids, "top_k": top_k},
                timeout=5
            )
            if resp.status_code == 200:
                return resp.json().get("recommendations", [])
            else:
                logger.error(f"Remote SASRec error: {resp.text}")
                return []
        except Exception as e:
            logger.error(f"Remote SASRec connection failed: {e}")
            return []

    def _predict_local(self, session_aids: List[int], top_k: int) -> List[int]:
        """Run local PyTorch inference."""
        if not self.model or not HAS_TORCH:
            # Dummy fallback
            last_item = session_aids[-1]
            return [last_item + i for i in range(1, top_k + 1)]

        # Prepare sequence
        seq = [aid + 1 for aid in session_aids[-self.model.max_len:]]
        seq_len = len(seq)
        pad_len = self.model.max_len - seq_len
        padded = [0] * pad_len + seq
        mask_arr = [0.0] * pad_len + [1.0] * seq_len
        
        item_indices = torch.tensor([padded], dtype=torch.long, device=self.device)
        mask = torch.tensor([mask_arr], dtype=torch.float, device=self.device)

        with torch.no_grad():
            x_hat = self.model.forward(item_indices, mask)
            last_hidden = x_hat[:, -1, :]
            logits = multiply_head_with_embedding(last_hidden, self.model.output_embedding.weight).squeeze(0)
            logits[0] = float("-inf")
            
            # Exclude clicked
            for aid in session_aids:
                idx = aid + 1
                if 0 < idx <= self.model.num_items:
                    logits[idx] = float("-inf")
            
            actual_k = min(top_k, self.model.num_items)
            _, top_indices_tensor = torch.topk(logits, k=actual_k)
            return [aid - 1 for aid in top_indices_tensor.cpu().tolist()]

    def predict(self, session_aids: List[int], top_k: int = 20) -> List[int]:
        if not session_aids:
            return []
            
        if self.remote_url:
            return self._predict_remote(session_aids, top_k)
        else:
            return self._predict_local(session_aids, top_k)

    def recommend_multi_objective(self, session_aids: List[int], top_k: int = 20) -> Dict[str, List[int]]:
        # Get a slightly larger pool from the model
        base_recs = self.predict(session_aids, top_k + 10)
        
        return {
            "clicks": base_recs[:top_k],
            "carts": base_recs[2:top_k+2],
            "orders": base_recs[5:top_k+5]
        }
