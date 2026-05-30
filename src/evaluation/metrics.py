from typing import List

import numpy as np


def recall_at_k(predictions: List[int], ground_truth: List[int], k: int) -> float:
    """
    Calculate Recall@K.

    Args:
        predictions: List of predicted item IDs
        ground_truth: List of actual item IDs
        k: Number of top predictions to consider

    Returns:
        Recall@K score
    """
    if not ground_truth:
        return 0.0

    pred_k = predictions[:k]
    hits = len(set(pred_k) & set(ground_truth))
    return hits / len(set(ground_truth))


def mrr_at_k(predictions: List[int], ground_truth: List[int], k: int) -> float:
    """
    Calculate Mean Reciprocal Rank@K.

    Args:
        predictions: List of predicted item IDs in rank order
        ground_truth: List of actual item IDs
        k: Number of top predictions to consider

    Returns:
        MRR@K score
    """
    if not ground_truth:
        return 0.0

    gt_set = set(ground_truth)
    for i, pred in enumerate(predictions[:k]):
        if pred in gt_set:
            return 1.0 / (i + 1)
    return 0.0


def ndcg_at_k(predictions: List[int], ground_truth: List[int], k: int) -> float:
    """
    Calculate Normalized Discounted Cumulative Gain@K.

    Args:
        predictions: List of predicted item IDs in rank order
        ground_truth: List of actual item IDs
        k: Number of top predictions to consider

    Returns:
        NDCG@K score
    """
    if not ground_truth:
        return 0.0

    gt_set = set(ground_truth)
    dcg = 0.0
    for i, pred in enumerate(predictions[:k]):
        if pred in gt_set:
            dcg += 1.0 / np.log2(i + 2)

    idcg = sum(1.0 / np.log2(i + 2) for i in range(min(len(ground_truth), k)))
    return dcg / idcg if idcg > 0 else 0.0
