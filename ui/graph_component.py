"""Obsidian-style force-directed graph renderer (vis-network).

Takes the {nodes, edges} from science.graph and renders an interactive,
draggable, physics-simulated network inside Streamlit via components.html.
Dark glowing aesthetic to match the Obsidian graph look.

vis-network is loaded from CDN, so the browser needs internet. For an
air-gapped regulatory deployment, vendor the library locally instead.
"""
import json
import streamlit.components.v1 as components


_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
  <style>
    html, body {{ margin: 0; padding: 0; background: #1a2332; }}
    #net {{ width: 100%; height: {height}px; background:
        radial-gradient(circle at 50% 40%, #22304a 0%, #161e2b 100%); border-radius: 12px; }}
    #legend {{ position: absolute; top: 12px; left: 14px; font-family: Arial, sans-serif;
        font-size: 11px; color: #cdd6e3; background: rgba(20,28,43,0.7);
        padding: 8px 12px; border-radius: 8px; line-height: 1.6; }}
    .dot {{ display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:5px; }}
  </style>
</head>
<body>
  <div id="net"></div>
  <div id="legend">
    <strong>Lagoon Causal Graph</strong><br>
    <span class="dot" style="background:#27ae60"></span>Low &nbsp;
    <span class="dot" style="background:#f39c12"></span>Moderate &nbsp;
    <span class="dot" style="background:#e67e22"></span>High &nbsp;
    <span class="dot" style="background:#e74c3c"></span>Severe<br>
    <span class="dot" style="background:#9b59b6"></span>Nutrient source &nbsp;
    <span class="dot" style="background:#27ae60"></span>⚙ Intervention
  </div>
  <script>
    const nodes = new vis.DataSet({nodes_json});
    const edges = new vis.DataSet({edges_json});
    const container = document.getElementById('net');
    const data = {{ nodes: nodes, edges: edges }};
    const options = {{
      nodes: {{
        shape: 'dot',
        font: {{ color: '#e8edf4', size: 14, face: 'Arial', multi: false,
                 strokeWidth: 3, strokeColor: '#0f1622' }},
        borderWidth: 0,
        shadow: {{ enabled: true, color: 'rgba(0,0,0,0.5)', size: 12, x: 0, y: 0 }},
      }},
      edges: {{
        color: {{ opacity: 0.55 }},
        smooth: {{ type: 'continuous' }},
        arrows: {{ to: {{ enabled: true, scaleFactor: 0.5 }} }},
      }},
      physics: {{
        solver: 'forceAtlas2Based',
        forceAtlas2Based: {{ gravitationalConstant: -55, centralGravity: 0.012,
                             springLength: 110, springConstant: 0.08, damping: 0.5 }},
        stabilization: {{ iterations: 180 }},
      }},
      interaction: {{ hover: true, tooltipDelay: 120, dragNodes: true,
                      navigationButtons: false, zoomView: true }},
    }};
    new vis.Network(container, data, options);
  </script>
</body>
</html>
"""


def render_lagoon_graph(graph: dict, height: int = 560):
    """Render the causal graph. `graph` is {nodes, edges} from science.graph."""
    html = _TEMPLATE.format(
        height=height,
        nodes_json=json.dumps(graph["nodes"]),
        edges_json=json.dumps(graph["edges"]),
    )
    components.html(html, height=height + 10, scrolling=False)
