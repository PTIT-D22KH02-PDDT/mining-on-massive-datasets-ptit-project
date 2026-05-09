"""
SASRec Kaggle Host - Run this on Kaggle to provide remote inference.
This script starts a FastAPI server that hosts the SASRec model.
You can use ngrok to expose this to your local machine.
"""

import os
import torch
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Tuple, Dict
import uvicorn

# --- Copy of SASRec Model Definition (Keep in sync with sasrec_recommender.py) ---
from torch import nn, tile, logical_and, logical_or, diag
from torch.nn import Dropout
import pytorch_lightning as py_light

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

# --- Inference Logic ---

class InferenceEngine:
    def __init__(self, checkpoint_path, device="cuda" if torch.cuda.is_available() else "cpu"):
        self.device = device
        print(f"Loading model from {checkpoint_path} on {device}...")
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
    def predict(self, session_aids: List[int], top_k: int = 20):
        if not session_aids:
            return []
        item_indices, mask = self._prepare_sequence(session_aids)
        x_hat = self.model.forward(item_indices, mask)
        last_hidden = x_hat[:, -1, :]
        logits = multiply_head_with_embedding(last_hidden, self.model.output_embedding.weight).squeeze(0)
        logits[0] = float("-inf")
        
        # Exclude clicked
        for aid in session_aids:
            idx = aid + 1
            if 0 < idx <= self.num_items:
                logits[idx] = float("-inf")
                
        actual_k = min(top_k, self.num_items)
        _, top_indices_tensor = torch.topk(logits, k=actual_k)
        return [aid - 1 for aid in top_indices_tensor.cpu().tolist()]

# --- FastAPI App ---

app = FastAPI()
engine = None

class RecommendRequest(BaseModel):
    session_aids: List[int]
    top_k: int = 20

@app.on_event("startup")
def load_model():
    global engine
    ckpt = "/kaggle/input/models/sandaria/sasrec/pytorch/otto-dataset/1/sasrec-otto-epoch4-recall_cutoff_200.308.ckpt"
    if not os.path.exists(ckpt):
        # Fallback for testing
        ckpt = "sasrec-otto.ckpt"
    engine = InferenceEngine(ckpt)

@app.post("/recommend")
async def recommend(req: RecommendRequest):
    if engine is None:
        raise HTTPException(status_code=500, detail="Model not loaded")
    
    try:
        aids = engine.predict(req.session_aids, req.top_k)
        return {"recommendations": aids}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000)
