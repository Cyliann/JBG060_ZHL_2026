"""


Usage:
    python plot_road_network.py
    python plot_road_network.py roads_2025-12-24.mtx roads_2025-12-24_nodes.csv out.png

Needs: pip install networkx matplotlib scipy pandas
"""
import sys

import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
import scipy.io
from matplotlib.lines import Line2D

MTX = sys.argv[1] if len(sys.argv) > 1 else "roads_2025-12-24_new.mtx"
NODES = sys.argv[2] if len(sys.argv) > 2 else "roads_2025-12-24_nodes_new.csv"
OUT = sys.argv[3] if len(sys.argv) > 3 else "road_network_new.png"


A = scipy.io.mmread(MTX).tocsr()          
G = nx.from_scipy_sparse_array(A)          

names = pd.read_csv(NODES).sort_values("node_id")["name"].tolist()
G = nx.relabel_nodes(G, dict(enumerate(names)))   

edge_colours = "#5d6d7e"
edge_styles = "solid"
node_sizes = [40 + 25 * G.degree(n) for n in G.nodes]

pos = {}
x_offset = 0.0
for comp in sorted(nx.connected_components(G), key=len, reverse=True):
    sub = G.subgraph(comp)
    if len(sub) > 2:
        p = nx.kamada_kawai_layout(sub, weight=None)
    else:
        p = {n: (i * 0.5, 0) for i, n in enumerate(sub.nodes)}
    scale = max(1.0, len(sub) ** 0.5 / 3)
    xs = [xy[0] for xy in p.values()]
    width = (max(xs) - min(xs)) * scale if len(xs) > 1 else 0.5
    for n, (x, y) in p.items():
        pos[n] = ((x - min(xs)) * scale + x_offset, y * scale)
    x_offset += width + 1.0


fig, ax = plt.subplots(figsize=(22, 12))
nx.draw_networkx_edges(G, pos, ax=ax, edge_color=edge_colours,
                       style=edge_styles, width=2.2, alpha=0.9)
nx.draw_networkx_nodes(G, pos, ax=ax, node_size=node_sizes,
                       node_color="#dfe6ee", edgecolors="#34495e",
                       linewidths=0.8)
nx.draw_networkx_labels(G, pos, ax=ax, font_size=7)


ax.set_title(f"South Sudan road network:{G.number_of_nodes()} vertices, "
             f"{G.number_of_edges()} edges, "
             f"{nx.number_connected_components(G)} connected components",
             fontsize=14)
ax.axis("off")
plt.tight_layout()
plt.savefig(OUT, dpi=200)
print(f"saved {OUT}")
plt.show()
