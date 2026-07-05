"""
ELK.js Layout Service - Python adapter for ELK functionality
This service coordinates with the Node.js ELK process for layout computation
"""

import asyncio
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional

from ..models.graph_models import (
    ProcessData, GraphStructure, ActivityNode, ProcessEdge, 
    LayoutType, LayoutOptions, LayoutResult, ProcessVariant
)

class LayoutService:
    """
    Service for computing graph layouts using ELK.js
    Coordinates between Python backend and Node.js ELK process
    """
    
    def __init__(self):
        self.elk_script_path = Path(__file__).parent / "elk_worker.js"
        
    async def convert_to_graph(self, process_data: ProcessData) -> GraphStructure:
        """
        Convert process mining data to graph structure
        """
        nodes = {}
        edges = {}
        
        # Extract all unique activities and transitions
        for variant in process_data.data:
            activities = variant.activities
            frequency = variant.frequency
            
            # Add nodes
            for activity in activities:
                node_id = self._sanitize_id(activity)
                if node_id not in nodes:
                    nodes[node_id] = ActivityNode(
                        id=node_id,
                        label=activity,
                        frequency=0,
                        is_start=False,
                        is_end=False
                    )
                nodes[node_id].frequency += frequency
            
            # Mark start and end nodes
            if activities:
                start_id = self._sanitize_id(activities[0])
                end_id = self._sanitize_id(activities[-1])
                nodes[start_id].is_start = True
                nodes[end_id].is_end = True
            
            # Add edges (transitions)
            for i in range(len(activities) - 1):
                source = activities[i]
                target = activities[i + 1]
                edge_key = f"{source}→{target}"
                edge_id = self._sanitize_id(edge_key)
                
                if edge_id not in edges:
                    edges[edge_id] = ProcessEdge(
                        id=edge_id,
                        source=self._sanitize_id(source),
                        target=self._sanitize_id(target),
                        label=edge_key,
                        frequency=0
                    )
                edges[edge_id].frequency += frequency
        
        return GraphStructure(
            nodes=list(nodes.values()),
            edges=list(edges.values())
        )
    
    async def compute_layout(
        self, 
        graph: GraphStructure, 
        layout_type: LayoutType,
        layout_options: Optional[LayoutOptions] = None
    ) -> LayoutResult:
        """
        Compute graph layout using ELK.js via Node.js subprocess
        """
        # Prepare ELK graph structure
        elk_graph = self._create_elk_graph(graph, layout_type, layout_options)
        
        # Write input to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(elk_graph, f)
            input_file = f.name
        
        try:
            # Run ELK layout computation
            result = await self._run_elk_process(input_file)
            
            # Parse result
            layout_result = LayoutResult(**result)
            return layout_result
            
        finally:
            # Clean up temporary file
            Path(input_file).unlink(missing_ok=True)
    
    async def generate_svg(self, graph: GraphStructure, layout: LayoutResult) -> str:
        """
        Generate SVG representation of the laid-out graph
        """
        # Calculate dimensions
        padding = 20
        svg_width = layout.width + 2 * padding
        svg_height = layout.height + 2 * padding
        
        # Start SVG
        svg_parts = [
            f'<svg width="{svg_width}" height="{svg_height}" ',
            f'viewBox="0 0 {svg_width} {svg_height}" ',
            'xmlns="http://www.w3.org/2000/svg">',
            '<defs>',
            '<marker id="arrowhead" markerWidth="10" markerHeight="10" ',
            'refX="8" refY="3" orient="auto" markerUnits="strokeWidth">',
            '<polygon points="0,0 0,6 9,3" fill="#666" />',
            '</marker>',
            '</defs>',
            f'<g transform="translate({padding}, {padding})">'
        ]
        
        # Calculate edge thickness scaling
        max_edge_freq = max((edge.frequency for edge in graph.edges), default=1)
        
        # Render edges
        for layout_edge in layout.edges:
            edge_data = next((e for e in graph.edges if e.id == layout_edge["id"]), None)
            if edge_data and "sections" in layout_edge and layout_edge["sections"]:
                section = layout_edge["sections"][0]
                thickness = max(1, (edge_data.frequency / max_edge_freq) * 6)
                
                # Build path
                path_data = f'M {section["startPoint"]["x"]} {section["startPoint"]["y"]}'
                
                if "bendPoints" in section:
                    for point in section["bendPoints"]:
                        path_data += f' L {point["x"]} {point["y"]}'
                
                path_data += f' L {section["endPoint"]["x"]} {section["endPoint"]["y"]}'
                
                svg_parts.extend([
                    f'<g class="edge" data-edge-id="{edge_data.id}">',
                    f'<path d="{path_data}" stroke="#666" stroke-width="{thickness}" ',
                    'fill="none" marker-end="url(#arrowhead)" opacity="0.8">',
                    f'<title>Transition: {edge_data.label} (Frequency: {edge_data.frequency:,})</title>',
                    '</path>',
                    '</g>'
                ])
        
        # Render nodes
        for layout_node in layout.children:
            node_data = next((n for n in graph.nodes if n.id == layout_node["id"]), None)
            if node_data:
                x, y = layout_node["x"], layout_node["y"]
                width, height = layout_node["width"], layout_node["height"]
                
                # Determine colors
                if node_data.is_start:
                    fill, stroke = "#e8f5e8", "#4CAF50"
                elif node_data.is_end:
                    fill, stroke = "#ffebee", "#f44336"
                else:
                    fill, stroke = "#e3f2fd", "#1976d2"
                
                # Show full labels (no truncation)
                display_label = node_data.label
                
                svg_parts.extend([
                    f'<g class="node" data-node-id="{node_data.id}">',
                    f'<rect x="{x}" y="{y}" width="{width}" height="{height}" ',
                    f'rx="6" fill="{fill}" stroke="{stroke}" stroke-width="2"/>',
                    f'<text x="{x + width/2}" y="{y + height/2}" ',
                    'text-anchor="middle" dominant-baseline="middle" ',
                    'font-size="12" font-family="Arial, sans-serif" font-weight="500">',
                    display_label,
                    '</text>',
                    f'<title>{node_data.label}\nFrequency: {node_data.frequency:,}',
                    f'{"(Start Activity)" if node_data.is_start else ""}',
                    f'{"(End Activity)" if node_data.is_end else ""}</title>',
                    '</g>'
                ])
        
        # Close SVG
        svg_parts.extend(['</g>', '</svg>'])
        
        return ''.join(svg_parts)
    
    async def generate_highlight_data(
        self, 
        variant: ProcessVariant, 
        layout_type: LayoutType,
        process_data: ProcessData
    ) -> Dict[str, Any]:
        """
        Generate highlighting data for a specific variant based on layout type
        """
        activities = variant.activities
        
        if layout_type == LayoutType.GRAPH:
            # Full graph highlighting - match by activity labels
            highlighted_nodes = [self._sanitize_id(activity) for activity in activities]
            highlighted_edges = []
            
            for i in range(len(activities) - 1):
                edge_id = self._sanitize_id(f"{activities[i]}→{activities[i + 1]}")
                highlighted_edges.append(edge_id)
                
        elif layout_type == LayoutType.SIMPLIFIED:
            # Simplified tree - find variant index and build specific path
            top_variants = sorted(process_data.data, key=lambda x: x.frequency, reverse=True)
            variant_index = next((i for i, v in enumerate(top_variants) 
                                if v.activities == variant.activities), -1)
            
            if variant_index >= 0:
                highlighted_nodes = ["root_start"]
                highlighted_edges = []
                
                previous_node_id = "root_start"
                for act_index, activity in enumerate(activities):
                    node_id = f"{self._sanitize_id(activity)}_{variant_index}_{act_index}"
                    highlighted_nodes.append(node_id)
                    highlighted_edges.append(f"{previous_node_id}_to_{node_id}")
                    previous_node_id = node_id
            else:
                highlighted_nodes = [self._sanitize_id(activity) for activity in activities]
                highlighted_edges = []
                
        elif layout_type == LayoutType.TREE:
            # Hierarchical tree - path through levels
            highlighted_nodes = []
            highlighted_edges = []
            
            for level, activity in enumerate(activities):
                node_id = f"{self._sanitize_id(activity)}_L{level}"
                highlighted_nodes.append(node_id)
                
                if level < len(activities) - 1:
                    next_activity = activities[level + 1]
                    source_id = f"{self._sanitize_id(activity)}_L{level}"
                    target_id = f"{self._sanitize_id(next_activity)}_L{level + 1}"
                    edge_id = f"{source_id}_to_{target_id}"
                    highlighted_edges.append(edge_id)
        
        else:
            # Default: match by activity labels
            highlighted_nodes = [self._sanitize_id(activity) for activity in activities]
            highlighted_edges = []
        
        return {
            "layout_type": layout_type.value,
            "highlighted_nodes": highlighted_nodes,
            "highlighted_edges": highlighted_edges,
            "variant_activities": activities
        }
    
    def _sanitize_id(self, text: str) -> str:
        """Sanitize text for use as DOM ID"""
        import re
        return re.sub(r'[^a-zA-Z0-9]', '_', text).strip('_')
    
    def _create_elk_graph(
        self, 
        graph: GraphStructure, 
        layout_type: LayoutType,
        layout_options: Optional[LayoutOptions] = None
    ) -> Dict[str, Any]:
        """Create ELK-compatible graph structure"""
        
        # Default layout options
        elk_options = {
            "elk.algorithm": "layered",
            "elk.direction": "RIGHT",
            "elk.spacing.nodeNode": 80,
            "elk.layered.spacing.nodeNodeBetweenLayers": 100,
            "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
            "elk.layered.nodePlacement.strategy": "BRANDES_KOEPF",
            "elk.edge.routing": "POLYLINE"
        }
        
        # Adjust options based on layout type
        if layout_type in [LayoutType.TREE, LayoutType.SIMPLIFIED]:
            elk_options.update({
                "elk.direction": "DOWN",
                "elk.spacing.nodeNode": 80,
                "elk.layered.spacing.nodeNodeBetweenLayers": 120,
                "elk.edge.routing": "ORTHOGONAL"
            })
        
        # Override with custom options if provided
        if layout_options and layout_options.elk_options:
            elk_options.update(layout_options.elk_options)
        
        return {
            "id": "root",
            "layoutOptions": elk_options,
            "children": [
                {
                    "id": node.id,
                    "width": 160,
                    "height": 60,
                    "layoutOptions": {"elk.portConstraints": "FREE"}
                }
                for node in graph.nodes
            ],
            "edges": [
                {
                    "id": edge.id,
                    "sources": [edge.source],
                    "targets": [edge.target]
                }
                for edge in graph.edges
            ]
        }
    
    async def _run_elk_process(self, input_file: str) -> Dict[str, Any]:
        """
        Run ELK layout computation via Node.js subprocess
        """
        # For now, we'll create a simple mock response
        # In a real implementation, this would call the ELK.js Node process
        
        # Read input graph
        with open(input_file, 'r') as f:
            elk_graph = json.load(f)
        
        # Mock layout result (in production, this would come from ELK.js)
        return {
            "width": 800,
            "height": 600,
            "children": [
                {
                    "id": child["id"],
                    "x": i * 180 + 50,
                    "y": 100,
                    "width": child["width"],
                    "height": child["height"]
                }
                for i, child in enumerate(elk_graph["children"])
            ],
            "edges": [
                {
                    "id": edge["id"],
                    "sections": [{
                        "startPoint": {"x": 100, "y": 130},
                        "endPoint": {"x": 280, "y": 130},
                        "bendPoints": []
                    }]
                }
                for edge in elk_graph["edges"]
            ]
        }
