"""Single-period inventory mechanics, vectorised over Monte Carlo runs.

Shapes used throughout: R runs, P products, C components, K sites.
Each site is a warehouse feeding one factory; component stock is held at the site.
"""
from __future__ import annotations

import numpy as np


def split_arrivals(arrivals: np.ndarray, inv: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Split pooled supplier receipts (R, C) across sites in proportion to each site's
    shortfall versus its target stock (C, K). With no shortfall, split by target.

    Returns (R, C, K); sums over K equal ``arrivals`` exactly.
    """
    deficit = np.maximum(target[None, :, :] - inv, 0.0)
    total = deficit.sum(axis=2, keepdims=True)
    by_target = np.broadcast_to(target / target.sum(axis=1, keepdims=True), deficit.shape)
    weights = np.where(total > 0, deficit / np.where(total > 0, total, 1.0), by_target)
    return arrivals[:, :, None] * weights


def produce(inv: np.ndarray, demand: np.ndarray, bom: np.ndarray):
    """Build as much of this month's demand as component stock allows.

    inv (R, C, K) component stock, demand (R, P, K) finished units, bom (P, C).
    Shortages are rationed proportionally: every product at a site gets the same
    build fraction, set by the scarcest component. Unbuilt demand is lost (no backlog).

    Returns (build_frac (R, K), consumption (R, C, K)).
    """
    need = np.einsum("rpk,pc->rck", demand, bom)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(need > 0, inv / need, np.inf)
    frac = np.clip(ratio.min(axis=1), 0.0, 1.0)
    frac = np.where(np.isinf(frac), 1.0, frac)
    consumption = need * frac[:, None, :]
    return frac, consumption


def order_up_to(inventory_position: np.ndarray, level: np.ndarray) -> np.ndarray:
    """Base-stock order quantity: raise inventory position to ``level`` (never negative)."""
    return np.maximum(level - inventory_position, 0.0)


def confirm_order(requested: np.ndarray, base: np.ndarray, fill: np.ndarray,
                  inflation_cap: float) -> np.ndarray:
    """Allocation rule. The supplier confirms ``fill`` x the request, but never more than
    ``inflation_cap`` x the customer's allocation base (so inflating orders helps only a little).
    """
    return fill * np.minimum(requested, inflation_cap * base)


def sample_discrete(u: np.ndarray, dist: dict[int, float]) -> np.ndarray:
    """Map uniform draws to a discrete distribution {value: prob} by inverse CDF."""
    values = np.array(sorted(dist))
    cdf = np.cumsum([dist[v] for v in values])
    cdf[-1] = 1.0
    return values[np.searchsorted(cdf, u, side="right").clip(max=len(values) - 1)]
