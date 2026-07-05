"""
Data models for process mining graphs and ELK.js integration with time-based analysis
"""

from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Union
from enum import Enum
from datetime import datetime

class LayoutType(str, Enum):
    """Available layout algorithms"""
    TREE = "tree"
    SIMPLIFIED = "simplified" 
    GRAPH = "graph"
    LAYERED = "layered"
    FORCE = "force"

class ActivityNode(BaseModel):
    """Process activity node"""
    id: str
    label: str
    frequency: int = 0
    is_start: bool = False
    is_end: bool = False
    level: Optional[int] = None

class ProcessEdge(BaseModel):
    """Process transition edge"""
    id: str
    source: str
    target: str
    label: Optional[str] = None
    frequency: int = 0

# Time-based statistics models
class OutlierAnalysis(BaseModel):
    """Outlier detection analysis"""
    outlier_count: int = 0
    outlier_percentage: float = 0.0
    outlier_bounds: Optional[Dict[str, float]] = None

class Percentiles(BaseModel):
    """Statistical percentiles"""
    p25: float = 0.0
    p50: float = 0.0  # median
    p75: float = 0.0
    p90: float = 0.0
    p95: float = 0.0
    p99: float = 0.0

class CaseDurations(BaseModel):
    """Enhanced case duration statistics"""
    min_duration_seconds: float = 0.0
    max_duration_seconds: float = 0.0
    avg_duration_seconds: float = 0.0
    median_duration_seconds: float = 0.0
    std_duration_seconds: float = 0.0
    total_cases: int = 0
    percentiles: Optional[Percentiles] = None
    outlier_analysis: Optional[OutlierAnalysis] = None

class ActivityTransition(BaseModel):
    """Activity transition timing statistics"""
    min_transition_seconds: Optional[float] = None
    max_transition_seconds: Optional[float] = None
    avg_transition_seconds: float = 0.0
    median_transition_seconds: Optional[float] = None
    std_transition_seconds: Optional[float] = None
    occurrences: Optional[int] = None
    percentiles: Optional[Percentiles] = None
    outlier_analysis: Optional[OutlierAnalysis] = None

class AdvancedTimeStatistics(BaseModel):
    """Advanced time-based process statistics"""
    enhanced_case_durations: CaseDurations
    enhanced_activity_transitions: Dict[str, ActivityTransition] = {}

class ProcessVariant(BaseModel):
    """Single process variant with time statistics"""
    variant: str
    activities: List[str]
    frequency: int
    percentage: Optional[float] = None
    cases: Optional[List[str]] = None
    advanced_time_statistics: Optional[AdvancedTimeStatistics] = None

# Bottleneck and efficiency analysis models
class BottleneckActivity(BaseModel):
    """Bottleneck analysis for an activity"""
    activity: str
    avg_waiting_time_seconds: float
    frequency: int
    bottleneck_score: float
    percentiles: Optional[Percentiles] = None
    outliers: Optional[OutlierAnalysis] = None

class BottleneckAnalysis(BaseModel):
    """Process bottleneck analysis"""
    bottleneck_ranking: List[BottleneckActivity] = []
    detailed_analysis: Optional[Dict[str, BottleneckActivity]] = None

class EfficiencyAnalysis(BaseModel):
    """Process efficiency metrics"""
    process_efficiency_percentage: float = 0.0
    avg_total_cycle_time_seconds: Optional[float] = None
    avg_estimated_value_added_time_seconds: Optional[float] = None
    avg_waiting_time_seconds: Optional[float] = None
    waste_percentage: float = 0.0

class ThroughputAnalysis(BaseModel):
    """Daily throughput metrics"""
    min: int = 0
    max: int = 0
    avg: float = 0.0
    std: float = 0.0

class WIPAnalysis(BaseModel):
    """Work-in-progress analysis"""
    max_concurrent_cases: int = 0
    avg_concurrent_cases: float = 0.0
    min_concurrent_cases: int = 0

class ThroughputMetrics(BaseModel):
    """Throughput and WIP metrics"""
    throughput_analysis: Dict[str, ThroughputAnalysis] = {}
    wip_analysis: Optional[WIPAnalysis] = None

class TimeRange(BaseModel):
    """Log time range information"""
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    total_duration_days: Optional[int] = None
    total_events: Optional[int] = None

class ActivityPatterns(BaseModel):
    """Temporal activity patterns"""
    hourly_activity_distribution: Dict[str, Dict[str, int]] = {}
    daily_activity_distribution: Dict[str, Dict[str, int]] = {}

class PeakHours(BaseModel):
    """Peak activity identification"""
    busiest_hour: Optional[int] = None
    busiest_day: Optional[str] = None

class EnhancedTemporalAnalysis(BaseModel):
    """Enhanced temporal pattern analysis"""
    log_time_range: Optional[TimeRange] = None
    activity_patterns: Optional[ActivityPatterns] = None
    peak_hours: Optional[PeakHours] = None

class AdvancedTimeAnalysis(BaseModel):
    """Complete advanced time analysis"""
    enhanced_case_statistics: Optional[Dict[str, Any]] = None
    throughput_metrics: Optional[ThroughputMetrics] = None
    bottleneck_analysis: Optional[BottleneckAnalysis] = None
    efficiency_analysis: Optional[EfficiencyAnalysis] = None
    enhanced_temporal_analysis: Optional[EnhancedTemporalAnalysis] = None

class ProcessData(BaseModel):
    """Complete process mining dataset with time analysis"""
    success: bool = True
    data: List[ProcessVariant]
    metadata: Optional[Dict[str, Any]] = None
    advanced_time_analysis: Optional[AdvancedTimeAnalysis] = None

class GraphStructure(BaseModel):
    """Graph structure with nodes and edges"""
    nodes: List[ActivityNode]
    edges: List[ProcessEdge]

class LayoutOptions(BaseModel):
    """ELK layout configuration options"""
    algorithm: str = "layered"
    direction: str = "RIGHT"
    node_spacing: float = 80
    layer_spacing: float = 100
    edge_spacing: float = 20
    elk_options: Optional[Dict[str, Any]] = None

class GraphLayoutRequest(BaseModel):
    """Request for graph layout computation"""
    processData: ProcessData
    layoutType: LayoutType = LayoutType.TREE
    layoutOptions: Optional[LayoutOptions] = None

class LayoutResult(BaseModel):
    """ELK layout computation result"""
    width: float
    height: float
    children: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]

class GraphLayoutResponse(BaseModel):
    """Response from graph layout computation"""
    success: bool
    graph: GraphStructure
    layout: LayoutResult
    svg: Optional[str] = None
    statistics: Optional[Dict[str, Any]] = None

class ExportOptions(BaseModel):
    """Options for graph export"""
    format: str = "svg"  # svg, png, pdf
    width: Optional[int] = None
    height: Optional[int] = None
    include_statistics: bool = False

class VariantAnalysis(BaseModel):
    """Analysis of process variants with time metrics"""
    id: int
    activities: List[str]
    frequency: int
    percentage: float
    length: int
    unique_activities: int
    path: str
    avg_duration_seconds: Optional[float] = None
    median_duration_seconds: Optional[float] = None
    min_duration_seconds: Optional[float] = None
    max_duration_seconds: Optional[float] = None
    efficiency_score: Optional[float] = None

class ProcessStatistics(BaseModel):
    """Enhanced process mining statistics"""
    total_variants: int
    total_cases: int
    total_nodes: int
    total_edges: int
    avg_variant_length: float
    max_variant_length: int
    min_variant_length: int
    start_activities: int
    end_activities: int
    # Time-based statistics
    avg_case_duration_seconds: Optional[float] = None
    median_case_duration_seconds: Optional[float] = None
    process_efficiency_percentage: Optional[float] = None
    total_bottlenecks: Optional[int] = None
    peak_hour: Optional[int] = None
    peak_day: Optional[str] = None

class HighlightRequest(BaseModel):
    """Request to highlight specific variant"""
    variant_id: int
    layout_type: LayoutType

class TimeAnalysisRequest(BaseModel):
    """Request for time-based analysis"""
    process_data: ProcessData
    analysis_type: str = "comprehensive"  # comprehensive, bottleneck, efficiency, temporal
    include_outliers: bool = True
    time_unit: str = "seconds"  # seconds, minutes, hours, days

class BottleneckAnalysisResponse(BaseModel):
    """Response for bottleneck analysis"""
    success: bool
    bottlenecks: List[BottleneckActivity]
    recommendations: List[str] = []
    efficiency_score: float = 0.0

class TemporalAnalysisResponse(BaseModel):
    """Response for temporal pattern analysis"""
    success: bool
    peak_hours: Dict[str, int]
    peak_days: Dict[str, int]
    activity_patterns: Dict[str, Dict[str, Any]]
    recommendations: List[str] = []
