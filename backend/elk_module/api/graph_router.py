"""
Graph API endpoints for layout computation and analysis
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
import asyncio
import json

from ..models.graph_models import (
    ProcessData, GraphLayoutRequest, GraphLayoutResponse,
    VariantAnalysis, ProcessStatistics, HighlightRequest,
    LayoutType, GraphStructure, ActivityNode, ProcessEdge
)
from ..elk_adapters.layout_service import LayoutService

router = APIRouter()

# Initialize layout service
layout_service = LayoutService()

@router.post("/layout", response_model=GraphLayoutResponse)
async def compute_layout(request: GraphLayoutRequest):
    """
    Compute graph layout using ELK.js algorithms
    """
    try:
        # Convert process data to graph structure
        graph = await layout_service.convert_to_graph(request.process_data)
        
        # Compute layout
        layout_result = await layout_service.compute_layout(
            graph, 
            request.layout_type,
            request.layout_options
        )
        
        # Generate SVG if requested
        svg = await layout_service.generate_svg(graph, layout_result)
        
        # Calculate statistics
        statistics = calculate_statistics(graph, request.process_data)
        
        return GraphLayoutResponse(
            success=True,
            graph=graph,
            layout=layout_result,
            svg=svg,
            statistics=statistics
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Layout computation failed: {str(e)}")

@router.post("/analyze-variants", response_model=List[VariantAnalysis])
async def analyze_variants(process_data: ProcessData):
    """
    Analyze process variants and return statistics with time metrics
    """
    try:
        variants = []
        total_cases = sum(variant.frequency for variant in process_data.data)
        
        for i, variant in enumerate(process_data.data):
            # Extract time metrics if available
            avg_duration = None
            median_duration = None
            min_duration = None
            max_duration = None
            efficiency_score = None
            
            if variant.advanced_time_statistics:
                duration_stats = variant.advanced_time_statistics.enhanced_case_durations
                avg_duration = duration_stats.avg_duration_seconds
                median_duration = duration_stats.median_duration_seconds
                min_duration = duration_stats.min_duration_seconds
                max_duration = duration_stats.max_duration_seconds
                
                # Calculate efficiency score based on duration
                if avg_duration and avg_duration > 0:
                    # Simple efficiency score: shorter duration = higher efficiency
                    all_durations = [
                        v.advanced_time_statistics.enhanced_case_durations.avg_duration_seconds 
                        for v in process_data.data 
                        if v.advanced_time_statistics and v.advanced_time_statistics.enhanced_case_durations.avg_duration_seconds > 0
                    ]
                    if all_durations:
                        max_duration_in_process = max(all_durations)
                        if max_duration_in_process > 0:
                            efficiency_score = ((max_duration_in_process - avg_duration) / max_duration_in_process) * 100
            
            analysis = VariantAnalysis(
                id=i + 1,
                activities=variant.activities,
                frequency=variant.frequency,
                percentage=round((variant.frequency / total_cases) * 100, 2),
                length=len(variant.activities),
                unique_activities=len(set(variant.activities)),
                path=" → ".join(variant.activities),
                avg_duration_seconds=avg_duration,
                median_duration_seconds=median_duration,
                min_duration_seconds=min_duration,
                max_duration_seconds=max_duration,
                efficiency_score=efficiency_score
            )
            variants.append(analysis)
        
        # Sort by frequency
        variants.sort(key=lambda x: x.frequency, reverse=True)
        
        return variants
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Variant analysis failed: {str(e)}")

@router.post("/statistics", response_model=ProcessStatistics)
async def compute_statistics(process_data: ProcessData):
    """
    Compute comprehensive process mining statistics with time metrics
    """
    try:
        # Convert to graph structure to get node/edge counts
        graph = await layout_service.convert_to_graph(process_data)
        
        # Calculate variant statistics
        variants = process_data.data
        total_cases = sum(v.frequency for v in variants)
        variant_lengths = [len(v.activities) for v in variants]
        
        # Calculate activity statistics
        all_activities = set()
        start_activities = set()
        end_activities = set()
        
        for variant in variants:
            all_activities.update(variant.activities)
            if variant.activities:
                start_activities.add(variant.activities[0])
                end_activities.add(variant.activities[-1])
        
        # Calculate time-based statistics
        case_durations = []
        for variant in variants:
            if variant.advanced_time_statistics:
                duration_stats = variant.advanced_time_statistics.enhanced_case_durations
                if duration_stats.avg_duration_seconds > 0:
                    case_durations.extend([duration_stats.avg_duration_seconds] * variant.frequency)
        
        avg_case_duration = sum(case_durations) / len(case_durations) if case_durations else None
        median_case_duration = sorted(case_durations)[len(case_durations)//2] if case_durations else None
        
        # Extract advanced analysis if available
        process_efficiency = None
        total_bottlenecks = None
        peak_hour = None
        peak_day = None
        
        if process_data.advanced_time_analysis:
            if process_data.advanced_time_analysis.efficiency_analysis:
                process_efficiency = process_data.advanced_time_analysis.efficiency_analysis.process_efficiency_percentage
            
            if process_data.advanced_time_analysis.bottleneck_analysis:
                total_bottlenecks = len(process_data.advanced_time_analysis.bottleneck_analysis.bottleneck_ranking)
            
            if (process_data.advanced_time_analysis.enhanced_temporal_analysis and 
                process_data.advanced_time_analysis.enhanced_temporal_analysis.peak_hours):
                peak_hour = process_data.advanced_time_analysis.enhanced_temporal_analysis.peak_hours.busiest_hour
                peak_day = process_data.advanced_time_analysis.enhanced_temporal_analysis.peak_hours.busiest_day
        
        statistics = ProcessStatistics(
            total_variants=len(variants),
            total_cases=total_cases,
            total_nodes=len(graph.nodes),
            total_edges=len(graph.edges),
            avg_variant_length=round(sum(variant_lengths) / len(variant_lengths), 1),
            max_variant_length=max(variant_lengths),
            min_variant_length=min(variant_lengths),
            start_activities=len(start_activities),
            end_activities=len(end_activities),
            # Time-based statistics
            avg_case_duration_seconds=avg_case_duration,
            median_case_duration_seconds=median_case_duration,
            process_efficiency_percentage=process_efficiency,
            total_bottlenecks=total_bottlenecks,
            peak_hour=peak_hour,
            peak_day=peak_day
        )
        
        return statistics
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Statistics computation failed: {str(e)}")

@router.post("/highlight")
async def highlight_variant(request: HighlightRequest, process_data: ProcessData):
    """
    Generate highlighting information for a specific variant
    """
    try:
        # Find the variant
        if request.variant_id > len(process_data.data) or request.variant_id < 1:
            raise HTTPException(status_code=404, detail="Variant not found")
        
        variant = process_data.data[request.variant_id - 1]
        
        # Generate highlighting data based on layout type
        highlight_data = await layout_service.generate_highlight_data(
            variant, request.layout_type, process_data
        )
        
        return {
            "success": True,
            "variant_id": request.variant_id,
            "variant": variant,
            "highlight_data": highlight_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Highlighting failed: {str(e)}")

def calculate_statistics(graph: GraphStructure, process_data: ProcessData) -> dict:
    """Calculate basic graph statistics"""
    return {
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
        "variant_count": len(process_data.data),
        "total_frequency": sum(node.frequency for node in graph.nodes),
        "max_node_frequency": max((node.frequency for node in graph.nodes), default=0),
        "max_edge_frequency": max((edge.frequency for edge in graph.edges), default=0)
    }
