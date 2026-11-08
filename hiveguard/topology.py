"""Communication topologies (DESIGN §5.4)."""
from __future__ import annotations

import networkx as nx
import numpy as np


def make_graph(name: str, n: int, seed: int) -> nx.Graph:
    if name == "ring":
        return nx.cycle_graph(n)
    if name == "small_world":
        return nx.connected_watts_strogatz_graph(n, 4, 0.1, tries=1000, seed=seed)
    if name == "scale_free":
        return nx.barabasi_albert_graph(n, 2, seed=seed)
    if name == "star":
        return nx.star_graph(n - 1)  # node 0 is the hub
    if name == "full":
        return nx.complete_graph(n)
    raise ValueError(name)


def adjacency(G: nx.Graph) -> np.ndarray:
    n = G.number_of_nodes()
    A = np.zeros((n, n), dtype=bool)
    for u, v in G.edges():
        A[u, v] = A[v, u] = True
    return A


def distances(G: nx.Graph) -> np.ndarray:
    n = G.number_of_nodes()
    D = np.full((n, n), 10**6, dtype=int)
    for u, row in nx.all_pairs_shortest_path_length(G):
        for v, d in row.items():
            D[u, v] = d
    return D


def betweenness(G: nx.Graph) -> np.ndarray:
    bc = nx.betweenness_centrality(G, normalized=True)
    return np.array([bc[i] for i in range(G.number_of_nodes())])


def hub_order(G: nx.Graph, candidates: int, seed: int) -> list[int]:
    """Candidate positions sorted by betweenness (desc), ties broken by a seeded shuffle."""
    bc = betweenness(G)[:candidates]
    jitter = np.random.default_rng(seed).random(candidates)
    return [int(i) for i in np.lexsort((jitter, -bc))]
