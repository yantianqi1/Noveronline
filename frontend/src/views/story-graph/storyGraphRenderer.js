import * as d3 from "d3";

import { buildRenderableGraphData } from "./storyGraphRenderModel.js";
import {
  applySelectionStyles,
  buildEdgePath,
  createSelections,
  getEdgeLabelPoint,
  updateEdgeLabelBackgrounds,
  updateEdgeLabelVisibility,
  updateNodeLabelVisibility,
} from "./storyGraphRendererElements.js";

function readContainerSize(container) {
  return {
    width: Math.max(container?.clientWidth || 0, 0),
    height: Math.max(container?.clientHeight || 0, 0),
  };
}

function stopSimulation(state) {
  if (state.simulation) {
    state.simulation.stop();
    state.simulation = null;
  }
}

function resetScene(state) {
  stopSimulation(state);
  d3.select(state.svg).selectAll("*").remove();
  state.model = null;
  state.selections = null;
  state.viewport = null;
  state.zoomBehavior = null;
}

function buildViewport(state, svgSelection) {
  const viewport = svgSelection.append("g").attr("class", "story-graph-viewport");

  svgSelection
    .append("rect")
    .attr("width", state.width)
    .attr("height", state.height)
    .attr("fill", "transparent")
    .lower()
    .on("click", () => state.onCanvasSelect());

  state.zoomBehavior = d3
    .zoom()
    .extent([
      [0, 0],
      [state.width, state.height],
    ])
    .scaleExtent([0.1, 4])
    .on("zoom", (event) => {
      state.zoomTransform = event.transform;
      viewport.attr("transform", event.transform);
    });
  svgSelection.call(state.zoomBehavior);
  svgSelection.call(state.zoomBehavior.transform, state.zoomTransform);
  state.viewport = viewport;
}

function buildScene(state) {
  const svgSelection = d3
    .select(state.svg)
    .attr("width", state.width)
    .attr("height", state.height)
    .attr("viewBox", `0 0 ${state.width} ${state.height}`);

  buildViewport(state, svgSelection);
  createSelections(state);
}

function updateTickedElements(state) {
  state.selections.edge.attr("d", buildEdgePath);
  state.selections.edgeLabelText.each(function updateEdgeLabel(edge) {
    const point = getEdgeLabelPoint(edge);
    d3.select(this).attr("x", point.x).attr("y", point.y);
  });
  updateEdgeLabelBackgrounds(state);
  state.selections.node.attr("cx", (node) => node.x).attr("cy", (node) => node.y);
  state.selections.nodeLabel.attr("x", (node) => node.x + 14).attr("y", (node) => node.y + 4);
}

function startSimulation(state) {
  state.simulation = d3
    .forceSimulation(state.model.nodes)
    .force("link", d3.forceLink(state.model.edges).id((node) => node.id).distance((edge) => edge.linkDistance))
    .force("charge", d3.forceManyBody().strength(-400))
    .force("collide", d3.forceCollide(50))
    .force("center", d3.forceCenter(state.width / 2, state.height / 2))
    .force("x", d3.forceX(state.width / 2).strength(0.04))
    .force("y", d3.forceY(state.height / 2).strength(0.04))
    .on("tick", () => updateTickedElements(state));
}

function syncRenderedState(state) {
  updateNodeLabelVisibility(state);
  updateEdgeLabelVisibility(state);
  applySelectionStyles(state);
}

function rebuild(state) {
  resetScene(state);
  if (!state.data || !state.width || !state.height) {
    return;
  }

  state.model = buildRenderableGraphData(state.data);
  if (!state.model.nodes.length) {
    return;
  }

  buildScene(state);
  startSimulation(state);
  syncRenderedState(state);
}

function createResizeObserver(state) {
  return new ResizeObserver(() => {
    const nextSize = readContainerSize(state.container);
    if (nextSize.width === state.width && nextSize.height === state.height) {
      return;
    }
    state.width = nextSize.width;
    state.height = nextSize.height;
    rebuild(state);
  });
}

export function createStoryGraphRenderer({
  container,
  svg,
  onNodeSelect,
  onEdgeSelect,
  onCanvasSelect,
}) {
  const size = readContainerSize(container);
  const state = {
    container,
    svg,
    onNodeSelect,
    onEdgeSelect,
    onCanvasSelect,
    width: size.width,
    height: size.height,
    data: null,
    model: null,
    simulation: null,
    selections: null,
    viewport: null,
    zoomBehavior: null,
    zoomTransform: d3.zoomIdentity,
    showEdgeLabels: false,
    visibleLabelNodeIds: new Set(),
    selectedNodeId: null,
    selectedEdgeId: null,
  };
  const resizeObserver = createResizeObserver(state);

  resizeObserver.observe(container);

  return {
    setGraphData(data) {
      state.data = data;
      state.width = readContainerSize(container).width;
      state.height = readContainerSize(container).height;
      rebuild(state);
    },
    setShowEdgeLabels(value) {
      state.showEdgeLabels = value;
      updateEdgeLabelVisibility(state);
    },
    setVisibleLabelNodeIds(nodeIds = new Set()) {
      state.visibleLabelNodeIds = new Set(nodeIds);
      updateNodeLabelVisibility(state);
    },
    setSelection({ selectedNodeId = null, selectedEdgeId = null } = {}) {
      state.selectedNodeId = selectedNodeId;
      state.selectedEdgeId = selectedEdgeId;
      applySelectionStyles(state);
    },
    destroy() {
      resizeObserver.disconnect();
      resetScene(state);
    },
  };
}
