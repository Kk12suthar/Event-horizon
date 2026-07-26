import { useCallback, useEffect, useMemo } from 'react';
import {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  type Edge,
  type ReactFlowInstance,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import type {
  EdgeElement,
  PathElement,
  Rect,
  VisualDocument,
  VisualElement,
} from '@/types/visualDocument.generated';
import { VisualElementNode, type CanvasFlowNode, type CanvasNodeData } from './VisualElementNode';

interface VisualCanvasProps {
  document: VisualDocument;
  selectedIds: string[];
  onSelectionChange: (ids: string[]) => void;
  onElementRectChange: (elementId: string, rect: Rect) => void;
  onReady?: (instance: ReactFlowInstance<CanvasFlowNode, Edge>) => void;
}

const nodeTypes = { visual: VisualElementNode };

function pathRect(element: PathElement): Rect {
  const xs = element.points.map((point) => point.x);
  const ys = element.points.map((point) => point.y);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const maxX = Math.max(...xs);
  const maxY = Math.max(...ys);
  return { x: minX - 8, y: minY - 8, w: Math.max(16, maxX - minX + 16), h: Math.max(16, maxY - minY + 16) };
}

function isEdge(element: VisualElement): element is EdgeElement {
  return element.type === 'edge';
}

function isPath(element: VisualElement): element is PathElement {
  return element.type === 'path';
}

function toFlowNode(
  element: Exclude<VisualElement, EdgeElement>,
  selectedIds: string[],
  onElementRectChange: (elementId: string, rect: Rect) => void,
): CanvasFlowNode | null {
  const rect = isPath(element) ? pathRect(element) : 'rect' in element ? element.rect : null;
  if (!rect) return null;
  return {
    id: element.id,
    type: 'visual',
    position: { x: rect.x, y: rect.y },
    width: rect.w,
    height: rect.h,
    initialWidth: rect.w,
    initialHeight: rect.h,
    selected: selectedIds.includes(element.id),
    draggable: !element.locked,
    selectable: true,
    hidden: Boolean(element.hidden),
    zIndex: element.z || 0,
    style: { width: rect.w, height: rect.h },
    data: {
      element,
      pathRect: isPath(element) ? rect : undefined,
      onResizeEnd: onElementRectChange,
    } satisfies CanvasNodeData,
  };
}

function toFlowEdge(element: EdgeElement): Edge {
  const marker =
    element.marker === 'none'
      ? undefined
      : {
          type: MarkerType.ArrowClosed,
          color: '#8A8A8A',
          width: 16,
          height: 16,
        };
  return {
    id: element.id,
    source: element.source_id,
    target: element.target_id,
    label: element.label || undefined,
    type:
      element.routing === 'straight'
        ? 'straight'
        : element.routing === 'bezier'
          ? 'default'
          : 'smoothstep',
    markerEnd: element.marker === 'arrow-both' ? marker : marker,
    markerStart: element.marker === 'arrow-both' ? marker : undefined,
    hidden: Boolean(element.hidden),
    zIndex: element.z || 0,
    animated: element.edge_kind === 'message' || element.edge_kind === 'rework',
    style: {
      stroke: element.edge_kind === 'conditional' ? '#C16E43' : '#707070',
      strokeWidth: element.style?.stroke_width === 'thick' ? 3 : element.style?.stroke_width === 'thin' ? 1 : 1.5,
      strokeDasharray: element.style?.stroke_dash === 'dashed' ? '7 5' : element.style?.stroke_dash === 'dotted' ? '2 4' : undefined,
    },
    labelStyle: { fill: '#B4B4B4', fontSize: 10 },
    labelBgStyle: { fill: '#111111', fillOpacity: 0.92 },
    labelBgPadding: [6, 4],
    labelBgBorderRadius: 4,
  };
}

function VisualCanvasInner({
  document,
  selectedIds,
  onSelectionChange,
  onElementRectChange,
  onReady,
}: VisualCanvasProps) {
  const visibleLayerIds = useMemo(
    () => new Set((document.layers || []).filter((layer) => layer.visible !== false).map((layer) => layer.id)),
    [document.layers],
  );
  const mappedNodes = useMemo(
    () =>
      (document.elements || [])
        .filter((element) => !isEdge(element) && visibleLayerIds.has(element.layer_id))
        .map((element) => toFlowNode(element as Exclude<VisualElement, EdgeElement>, selectedIds, onElementRectChange))
        .filter((node): node is CanvasFlowNode => node !== null),
    [document.elements, onElementRectChange, selectedIds, visibleLayerIds],
  );
  const mappedEdges = useMemo(
    () =>
      (document.elements || [])
        .filter((element): element is EdgeElement => isEdge(element) && visibleLayerIds.has(element.layer_id))
        .map(toFlowEdge),
    [document.elements, visibleLayerIds],
  );
  const [nodes, setNodes, onNodesChange] = useNodesState<CanvasFlowNode>(mappedNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(mappedEdges);

  useEffect(() => setNodes(mappedNodes), [mappedNodes, setNodes]);
  useEffect(() => setEdges(mappedEdges), [mappedEdges, setEdges]);

  const handleDragStop = useCallback(
    (_event: MouseEvent | TouchEvent, node: CanvasFlowNode) => {
      const element = node.data.element;
      if (element.type === 'path') return;
      const original = 'rect' in element ? element.rect : null;
      if (!original || (original.x === node.position.x && original.y === node.position.y)) return;
      onElementRectChange(element.id, {
        x: Math.round(node.position.x * 100) / 100,
        y: Math.round(node.position.y * 100) / 100,
        w: node.measured?.width || node.width || original.w,
        h: node.measured?.height || node.height || original.h,
      });
    },
    [onElementRectChange],
  );

  return (
    <div className="relative h-full w-full bg-[#050505]">
      <ReactFlow<CanvasFlowNode, Edge>
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeDragStop={handleDragStop}
        onSelectionChange={({ nodes: selectedNodes, edges: selectedEdges }) =>
          onSelectionChange([...selectedNodes.map((node) => node.id), ...selectedEdges.map((edge) => edge.id)])
        }
        onInit={onReady}
        minZoom={0.05}
        maxZoom={8}
        defaultViewport={{
          x: document.viewport?.x || 0,
          y: document.viewport?.y || 0,
          zoom: document.viewport?.zoom || 1,
        }}
        fitView={(document.elements || []).length > 0}
        fitViewOptions={{ padding: 0.2, maxZoom: 1.2 }}
        deleteKeyCode={null}
        selectionKeyCode="Shift"
        multiSelectionKeyCode={['Meta', 'Control']}
        panOnScroll
        zoomOnPinch
        zoomOnDoubleClick={false}
        colorMode="dark"
        proOptions={{ hideAttribution: true }}
        aria-label={`${document.metadata.title} visual canvas`}
      >
        <Background variant={BackgroundVariant.Dots} gap={24} size={1.1} color="#343434" />
        <Controls
          position="bottom-left"
          showInteractive={false}
          className="!overflow-hidden !rounded-lg !border !border-[#303030] !bg-[#111111] !shadow-xl [&_button]:!border-[#303030] [&_button]:!bg-[#111111] [&_button]:!fill-[#D4D4D8] hover:[&_button]:!bg-[#202020]"
        />
        <MiniMap
          position="bottom-right"
          pannable
          zoomable
          maskColor="rgba(0,0,0,.66)"
          nodeColor={(node) => node.selected ? '#C16E43' : '#505050'}
          className="!hidden !rounded-lg !border !border-[#303030] !bg-[#0D0D0D] sm:!block"
        />
      </ReactFlow>
      {!document.elements?.length && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="max-w-sm rounded-2xl border border-[#292929] bg-[#0B0B0B]/90 px-8 py-7 text-center shadow-2xl backdrop-blur">
            <div className="text-sm font-semibold text-[#F4F4F5]">An open canvas for the agent</div>
            <div className="mt-2 text-xs leading-relaxed text-[#8A8A8A]">
              Ask for a process map, decision tree, chart, timeline, Gantt, KPI board, or a mixed visual story.
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function VisualCanvas(props: VisualCanvasProps) {
  return <ReactFlowProvider><VisualCanvasInner {...props} /></ReactFlowProvider>;
}
