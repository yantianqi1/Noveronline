import * as d3 from "d3";

import { truncateNodeLabel } from "./storyGraphRenderModel.js";

const DEFAULT_EDGE_COLOR = "#c4b393";
const DEFAULT_EDGE_WIDTH = 1.6;
const EDGE_HIGHLIGHT_COLOR = "#E91E63";
const EDGE_HIGHLIGHT_WIDTH = 2.6;
const EDGE_SELECTED_WIDTH = 3;
const EDGE_LABEL_COLOR = "#7d6a4d";
const EDGE_LABEL_HIGHLIGHT_COLOR = "#E91E63";
const EDGE_LABEL_BG = "rgba(255, 255, 255, 0.78)";
const EDGE_LABEL_BG_HIGHLIGHT = "rgba(233, 30, 99, 0.14)";
const NODE_STROKE = "#ffffff";
const NODE_STROKE_HOVER = "#333333";
const NODE_STROKE_SELECTED = "#E91E63";
const NODE_STROKE_WIDTH = 2.5;
const NODE_SELECTED_WIDTH = 4;
const NODE_RADIUS = 10;
const DRAG_THRESHOLD = 3;

function curveControlPoint(edge) {
  const dx = edge.target.x - edge.source.x;
  const dy = edge.target.y - edge.source.y;
  const distance = Math.hypot(dx, dy) || 1;
  const offset = Math.max(35, distance * (0.25 + edge.pairTotal * 0.05));

  return {
    x: (edge.source.x + edge.target.x) / 2 + (-dy / distance) * edge.curvature * offset,
    y: (edge.source.y + edge.target.y) / 2 + (dx / distance) * edge.curvature * offset,
  };
}

export function buildEdgePath(edge) {
  if (edge.isSelfLoop) {
    const startX = edge.source.x + 8;
    const startY = edge.source.y - 4;
    const endX = edge.source.x + 8;
    const endY = edge.source.y + 4;
    return `M${startX},${startY} A${edge.loopRadius},${edge.loopRadius} 0 1,${edge.arcSweepFlag} ${endX},${endY}`;
  }

  if (edge.pairTotal <= 1) {
    return `M${edge.source.x},${edge.source.y} L${edge.target.x},${edge.target.y}`;
  }

  const control = curveControlPoint(edge);
  return `M${edge.source.x},${edge.source.y} Q${control.x},${control.y} ${edge.target.x},${edge.target.y}`;
}

export function getEdgeLabelPoint(edge) {
  if (edge.isSelfLoop) {
    return { x: edge.source.x + edge.loopRadius + 40, y: edge.source.y };
  }
  if (edge.pairTotal <= 1) {
    return {
      x: (edge.source.x + edge.target.x) / 2,
      y: (edge.source.y + edge.target.y) / 2,
    };
  }

  const control = curveControlPoint(edge);
  return {
    x: 0.25 * edge.source.x + 0.5 * control.x + 0.25 * edge.target.x,
    y: 0.25 * edge.source.y + 0.5 * control.y + 0.25 * edge.target.y,
  };
}

export function updateEdgeLabelBackgrounds(state) {
  if (!state.selections) {
    return;
  }

  state.selections.edgeLabelBackground.each(function updateBackground(edge, index) {
    const point = getEdgeLabelPoint(edge);
    const textBox = state.selections.edgeLabelText.nodes()[index]?.getBBox();
    if (!textBox) {
      return;
    }

    d3.select(this)
      .attr("x", point.x - textBox.width / 2 - 5)
      .attr("y", point.y - textBox.height / 2 - 3)
      .attr("width", textBox.width + 10)
      .attr("height", textBox.height + 6);
  });
}

export function updateNodeLabelVisibility(state) {
  if (!state.selections) {
    return;
  }

  state.selections.nodeLabel.attr("display", (node) =>
    state.visibleLabelNodeIds.has(node.id) ? null : "none",
  );
}

export function updateEdgeLabelVisibility(state) {
  if (!state.selections) {
    return;
  }

  const opacity = state.showEdgeLabels ? 1 : 0;
  const pointerEvents = state.showEdgeLabels ? "auto" : "none";

  state.selections.edgeLabelBackground
    .attr("opacity", opacity)
    .style("pointer-events", pointerEvents);
  state.selections.edgeLabelText.attr("opacity", opacity).style("pointer-events", pointerEvents);
}

export function applySelectionStyles(state) {
  if (!state.selections) {
    return;
  }

  const adjacentEdgeIds = state.model?.adjacencyByNodeId.get(state.selectedNodeId) || new Set();

  state.selections.node
    .attr("stroke", (node) => (node.id === state.selectedNodeId ? NODE_STROKE_SELECTED : NODE_STROKE))
    .attr("stroke-width", (node) =>
      node.id === state.selectedNodeId ? NODE_SELECTED_WIDTH : NODE_STROKE_WIDTH,
    );
  state.selections.edge
    .attr("stroke", (edge) => {
      if (edge.id === state.selectedEdgeId || adjacentEdgeIds.has(edge.id)) {
        return EDGE_HIGHLIGHT_COLOR;
      }
      return DEFAULT_EDGE_COLOR;
    })
    .attr("stroke-width", (edge) => {
      if (edge.id === state.selectedEdgeId) {
        return EDGE_SELECTED_WIDTH;
      }
      return adjacentEdgeIds.has(edge.id) ? EDGE_HIGHLIGHT_WIDTH : DEFAULT_EDGE_WIDTH;
    });
  state.selections.edgeLabelBackground.attr("fill", (edge) =>
    edge.id === state.selectedEdgeId ? EDGE_LABEL_BG_HIGHLIGHT : EDGE_LABEL_BG,
  );
  state.selections.edgeLabelText.attr("fill", (edge) =>
    edge.id === state.selectedEdgeId ? EDGE_LABEL_HIGHLIGHT_COLOR : EDGE_LABEL_COLOR,
  );
}

function createNodeDrag(state) {
  return d3
    .drag()
    .on("start", (event, node) => {
      node.dragStartX = event.x;
      node.dragStartY = event.y;
      node.dragMoved = false;
      node.fx = node.x;
      node.fy = node.y;
    })
    .on("drag", (event, node) => {
      const distance = Math.hypot(event.x - node.dragStartX, event.y - node.dragStartY);
      if (!node.dragMoved && distance > DRAG_THRESHOLD) {
        node.dragMoved = true;
        state.simulation?.alphaTarget(0.3).restart();
      }
      if (node.dragMoved) {
        node.fx = event.x;
        node.fy = event.y;
      }
    })
    .on("end", (_event, node) => {
      if (node.dragMoved) {
        state.simulation?.alphaTarget(0);
      }
      node.fx = null;
      node.fy = null;
    });
}

function handleNodeHover(event, node, state) {
  if (node.id !== state.selectedNodeId) {
    d3.select(event.currentTarget).attr("stroke", NODE_STROKE_HOVER);
  }
}

function handleNodeLeave(event, node, state) {
  if (node.id !== state.selectedNodeId) {
    d3.select(event.currentTarget).attr("stroke", NODE_STROKE);
  }
}

function createEdgeSelections(edgeLayer, labelLayer, edges, onEdgeSelect) {
  const edge = edgeLayer
    .selectAll("path")
    .data(edges, (item) => item.id)
    .join("path")
    .attr("fill", "none")
    .attr("stroke", DEFAULT_EDGE_COLOR)
    .attr("stroke-width", DEFAULT_EDGE_WIDTH)
    .style("cursor", "pointer")
    .on("click", onEdgeSelect);
  const edgeLabelBackground = labelLayer
    .append("g")
    .selectAll("rect")
    .data(edges, (item) => item.id)
    .join("rect")
    .attr("rx", 4)
    .attr("ry", 4)
    .style("cursor", "pointer")
    .on("click", onEdgeSelect);
  const edgeLabelText = labelLayer
    .append("g")
    .selectAll("text")
    .data(edges, (item) => item.id)
    .join("text")
    .text((edgeItem) => edgeItem.raw.name || "关系")
    .attr("font-size", 11)
    .attr("text-anchor", "middle")
    .attr("dominant-baseline", "middle")
    .style("cursor", "pointer")
    .on("click", onEdgeSelect);

  return { edge, edgeLabelBackground, edgeLabelText };
}

function createNodeSelections(layer, nodes, state, onNodeSelect) {
  const node = layer
    .selectAll("circle")
    .data(nodes, (item) => item.id)
    .join("circle")
    .attr("r", NODE_RADIUS)
    .attr("fill", (nodeItem) => nodeItem.color)
    .attr("stroke", NODE_STROKE)
    .attr("stroke-width", NODE_STROKE_WIDTH)
    .style("cursor", "pointer")
    .call(createNodeDrag(state))
    .on("mouseenter", (event, nodeItem) => handleNodeHover(event, nodeItem, state))
    .on("mouseleave", (event, nodeItem) => handleNodeLeave(event, nodeItem, state))
    .on("click", onNodeSelect);
  const nodeLabel = layer
    .selectAll("text")
    .data(nodes, (item) => item.id)
    .join("text")
    .text((nodeItem) => truncateNodeLabel(nodeItem.raw.name))
    .attr("font-size", 12)
    .attr("fill", "#2d2418")
    .attr("font-weight", 500)
    .style("pointer-events", "none");

  return { node, nodeLabel };
}

export function createSelections(state) {
  const edgeLayer = state.viewport.append("g").attr("class", "story-graph-edges");
  const labelLayer = state.viewport.append("g").attr("class", "story-graph-edge-labels");
  const nodeLayer = state.viewport.append("g").attr("class", "story-graph-nodes");
  const handleEdgeSelect = (event, edge) => {
    event.stopPropagation();
    state.onEdgeSelect(edge.raw);
  };
  const handleNodeSelect = (event, node) => {
    event.stopPropagation();
    if (node.dragMoved) {
      node.dragMoved = false;
      return;
    }
    state.onNodeSelect(node.raw);
  };
  const edgeSelections = createEdgeSelections(
    edgeLayer,
    labelLayer,
    state.model.edges,
    handleEdgeSelect,
  );
  const nodeSelections = createNodeSelections(nodeLayer, state.model.nodes, state, handleNodeSelect);

  state.selections = {
    ...edgeSelections,
    ...nodeSelections,
  };
}
