"""
Time-based process mining analysis API endpoints
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
import asyncio
import json

from ..models.graph_models import (
    ProcessData, TimeAnalysisRequest, BottleneckAnalysisResponse,
    TemporalAnalysisResponse, AdvancedTimeAnalysis, VariantAnalysis,
    ProcessStatistics, BottleneckActivity, EfficiencyAnalysis
)
from ..services.time_analysis_service import TimeAnalysisService

router = APIRouter()

# Initialize time analysis service
time_service = TimeAnalysisService()

@router.post("/analyze-comprehensive", response_model=AdvancedTimeAnalysis)
async def analyze_comprehensive_time_metrics(request: TimeAnalysisRequest):
    """
    Perform comprehensive time-based process mining analysis
    """
    try:
        analysis = time_service.perform_comprehensive_analysis(
            request.process_data, 
            request.time_unit
        )
        
        return analysis
        
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Comprehensive analysis failed: {str(e)}"
        )

@router.post("/analyze-bottlenecks", response_model=BottleneckAnalysisResponse)
async def analyze_bottlenecks(request: TimeAnalysisRequest):
    """
    Analyze process bottlenecks and provide recommendations
    """
    try:
        bottleneck_analysis = time_service.analyze_bottlenecks(request.process_data)
        efficiency_analysis = time_service.analyze_efficiency(request.process_data)
        
        recommendations = time_service.generate_recommendations(
            bottleneck_analysis.bottleneck_ranking,
            efficiency_analysis
        )
        
        return BottleneckAnalysisResponse(
            success=True,
            bottlenecks=bottleneck_analysis.bottleneck_ranking,
            recommendations=recommendations,
            efficiency_score=efficiency_analysis.process_efficiency_percentage
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Bottleneck analysis failed: {str(e)}"
        )

@router.post("/analyze-temporal", response_model=TemporalAnalysisResponse)
async def analyze_temporal_patterns(request: TimeAnalysisRequest):
    """
    Analyze temporal patterns and peak activity times
    """
    try:
        temporal_analysis = time_service.analyze_temporal_patterns(request.process_data)
        
        # Extract peak information
        peak_hours = {}
        peak_days = {}
        activity_patterns = {}
        
        if temporal_analysis.activity_patterns:
            activity_patterns = {
                "hourly": temporal_analysis.activity_patterns.hourly_activity_distribution,
                "daily": temporal_analysis.activity_patterns.daily_activity_distribution
            }
        
        if temporal_analysis.peak_hours:
            if temporal_analysis.peak_hours.busiest_hour is not None:
                peak_hours["busiest_hour"] = temporal_analysis.peak_hours.busiest_hour
            if temporal_analysis.peak_hours.busiest_day:
                peak_days["busiest_day"] = temporal_analysis.peak_hours.busiest_day
        
        # Generate temporal recommendations
        recommendations = []
        if temporal_analysis.peak_hours:
            if temporal_analysis.peak_hours.busiest_hour:
                recommendations.append(
                    f"Peak activity occurs at {temporal_analysis.peak_hours.busiest_hour}:00. "
                    "Consider load balancing during this time."
                )
            if temporal_analysis.peak_hours.busiest_day:
                recommendations.append(
                    f"Highest activity on {temporal_analysis.peak_hours.busiest_day}s. "
                    "Ensure adequate staffing on this day."
                )
        
        return TemporalAnalysisResponse(
            success=True,
            peak_hours=peak_hours,
            peak_days=peak_days,
            activity_patterns=activity_patterns,
            recommendations=recommendations
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Temporal analysis failed: {str(e)}"
        )

@router.post("/analyze-efficiency", response_model=EfficiencyAnalysis)
async def analyze_process_efficiency(request: TimeAnalysisRequest):
    """
    Analyze process efficiency and waste metrics
    """
    try:
        efficiency_analysis = time_service.analyze_efficiency(request.process_data)
        return efficiency_analysis
        
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Efficiency analysis failed: {str(e)}"
        )

@router.post("/analyze-variants-time", response_model=List[VariantAnalysis])
async def analyze_variants_with_time_metrics(process_data: ProcessData):
    """
    Analyze process variants with enhanced time metrics
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
                
                # Calculate efficiency score based on duration and transitions
                if avg_duration and avg_duration > 0:
                    # Simple efficiency score: shorter duration = higher efficiency
                    max_possible_duration = max(
                        v.advanced_time_statistics.enhanced_case_durations.avg_duration_seconds 
                        for v in process_data.data 
                        if v.advanced_time_statistics and v.advanced_time_statistics.enhanced_case_durations.avg_duration_seconds > 0
                    )
                    if max_possible_duration > 0:
                        efficiency_score = ((max_possible_duration - avg_duration) / max_possible_duration) * 100
            
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
        
        # Sort by frequency (most common first)
        variants.sort(key=lambda x: x.frequency, reverse=True)
        
        return variants
        
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Variant time analysis failed: {str(e)}"
        )

@router.post("/statistics-enhanced", response_model=ProcessStatistics)
async def compute_enhanced_statistics(process_data: ProcessData):
    """
    Compute enhanced process mining statistics with time metrics
    """
    try:
        # Calculate basic statistics
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
        
        # Get efficiency and temporal data
        efficiency_analysis = time_service.analyze_efficiency(process_data)
        temporal_analysis = time_service.analyze_temporal_patterns(process_data)
        bottleneck_analysis = time_service.analyze_bottlenecks(process_data)
        
        statistics = ProcessStatistics(
            total_variants=len(variants),
            total_cases=total_cases,
            total_nodes=len(all_activities),
            total_edges=sum(len(v.activities) - 1 for v in variants if len(v.activities) > 1),
            avg_variant_length=round(sum(variant_lengths) / len(variant_lengths), 1),
            max_variant_length=max(variant_lengths),
            min_variant_length=min(variant_lengths),
            start_activities=len(start_activities),
            end_activities=len(end_activities),
            # Time-based statistics
            avg_case_duration_seconds=avg_case_duration,
            median_case_duration_seconds=median_case_duration,
            process_efficiency_percentage=efficiency_analysis.process_efficiency_percentage,
            total_bottlenecks=len(bottleneck_analysis.bottleneck_ranking),
            peak_hour=temporal_analysis.peak_hours.busiest_hour if temporal_analysis.peak_hours else None,
            peak_day=temporal_analysis.peak_hours.busiest_day if temporal_analysis.peak_hours else None
        )
        
        return statistics
        
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Enhanced statistics computation failed: {str(e)}"
        )

@router.get("/health")
async def health_check():
    """Health check endpoint for time analysis service"""
    return {
        "status": "healthy",
        "pm4py_available": time_service.pm4py_available,
        "service": "time_analysis"
    }
