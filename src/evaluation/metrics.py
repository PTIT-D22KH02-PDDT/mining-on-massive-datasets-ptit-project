from typing import Dict, List, Tuple

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


def hit_rate_at_k(predictions: List[int], ground_truth: List[int], k: int) -> float:
    """
    Calculate Hit Rate@K - whether at least one prediction is correct.

    Args:
        predictions: List of predicted item IDs
        ground_truth: List of actual item IDs
        k: Number of top predictions to consider

    Returns:
        1.0 if hit, 0.0 otherwise
    """
    if not ground_truth:
        return 0.0

    pred_k = predictions[:k]
    return 1.0 if set(pred_k) & set(ground_truth) else 0.0


def precision_at_k(predictions: List[int], ground_truth: List[int], k: int) -> float:
    """
    Calculate Precision@K.

    Args:
        predictions: List of predicted item IDs
        ground_truth: List of actual item IDs
        k: Number of top predictions to consider

    Returns:
        Precision@K score
    """
    if not predictions or k == 0:
        return 0.0

    pred_k = predictions[:k]
    hits = len(set(pred_k) & set(ground_truth))
    return hits / k


def weighted_recall_at_k(
    predictions: List[int],
    ground_truth: List[int],
    ground_truth_types: List[str],
    k: int,
    weights: Dict[str, float] = None,
) -> float:
    """
    Calculate Weighted Recall@K with OTTO weights.

    Args:
        predictions: List of predicted item IDs
        ground_truth: List of actual item IDs
        ground_truth_types: List of event types for ground truth items
        k: Number of top predictions to consider
        weights: Dict with weights for each type (default: clicks=0.1, carts=0.3, orders=0.6)

    Returns:
        Weighted Recall@K score
    """
    if not ground_truth:
        return 0.0

    if weights is None:
        weights = {"clicks": 0.1, "carts": 0.3, "orders": 0.6}

    pred_k = set(predictions[:k])
    weighted_hits = 0.0
    total_weight = 0.0

    for item, etype in zip(ground_truth, ground_truth_types):
        w = weights.get(etype, 0.1)
        total_weight += w
        if item in pred_k:
            weighted_hits += w

    return weighted_hits / total_weight if total_weight > 0 else 0.0


def evaluate_session(
    predictions: List[int],
    ground_truth: List[int],
    ground_truth_types: List[str] = None,
    ks: List[int] = None,
) -> Dict[str, float]:
    """
    Evaluate a single session across multiple metrics and K values.

    Args:
        predictions: List of predicted item IDs in rank order
        ground_truth: List of actual item IDs
        ground_truth_types: List of event types for ground truth items
        ks: List of K values to evaluate at

    Returns:
        Dictionary of metric names to scores
    """
    if ks is None:
        ks = [5, 10, 20]

    results = {}

    for k in ks:
        results[f"recall@{k}"] = recall_at_k(predictions, ground_truth, k)
        results[f"mrr@{k}"] = mrr_at_k(predictions, ground_truth, k)
        results[f"ndcg@{k}"] = ndcg_at_k(predictions, ground_truth, k)
        results[f"hit_rate@{k}"] = hit_rate_at_k(predictions, ground_truth, k)
        results[f"precision@{k}"] = precision_at_k(predictions, ground_truth, k)

        if ground_truth_types is not None:
            results[f"weighted_recall@{k}"] = weighted_recall_at_k(
                predictions, ground_truth, ground_truth_types, k
            )

    return results


def evaluate_batch(
    predictions_list: List[List[int]],
    ground_truth_list: List[List[int]],
    ground_truth_types_list: List[List[str]] = None,
    ks: List[int] = None,
) -> Dict[str, float]:
    """
    Evaluate a batch of sessions and return average metrics.

    Args:
        predictions_list: List of prediction lists for each session
        ground_truth_list: List of ground truth lists for each session
        ground_truth_types_list: List of ground truth types for each session
        ks: List of K values to evaluate at

    Returns:
        Dictionary of average metric scores
    """
    if ks is None:
        ks = [5, 10, 20]

    all_results = []

    for i, (preds, gt) in enumerate(zip(predictions_list, ground_truth_list)):
        gt_types = None
        if ground_truth_types_list is not None:
            gt_types = ground_truth_types_list[i]
        all_results.append(evaluate_session(preds, gt, gt_types, ks))

    avg_results = {}
    for key in all_results[0].keys():
        avg_results[key] = sum(r[key] for r in all_results) / len(all_results)

    return avg_results
