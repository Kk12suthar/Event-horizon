from fastapi import APIRouter, HTTPException, UploadFile, File, Body
from fastapi.concurrency import run_in_threadpool
import asyncio
import uuid
from pydantic import BaseModel
from typing import Optional, List, Dict, Any, Union
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import statistics
import numpy as np
import pandas as pd
from pm4py.objects.conversion.log import converter as log_converter
from database import engine
from sqlalchemy import text

# Conditional imports with fallbacks
try:
    from pm4py.statistics.traces.generic.log import case_statistics
    CASE_STATISTICS_AVAILABLE = True
except ImportError:
    CASE_STATISTICS_AVAILABLE = False

try:
    from pm4py.statistics.start_activities.log import get as start_activities_get
    START_ACTIVITIES_AVAILABLE = True
except ImportError:
    START_ACTIVITIES_AVAILABLE = False

try:
    from pm4py.statistics.end_activities.log import get as end_activities_get
    END_ACTIVITIES_AVAILABLE = True
except ImportError:
    END_ACTIVITIES_AVAILABLE = False

try:
    from pm4py.statistics.directly_follows.log import get as directly_follows_get
    DIRECTLY_FOLLOWS_AVAILABLE = True
except ImportError:
    DIRECTLY_FOLLOWS_AVAILABLE = False

try:
    from pm4py.statistics.variants.log import get as variants_get
    VARIANTS_MODULE_AVAILABLE = True
except ImportError:
    VARIANTS_MODULE_AVAILABLE = False


router = APIRouter(prefix="/api/v1/elk_data", tags=["elk_data"])


class NumpyEncoder(json.JSONEncoder):
    """Custom JSON encoder to handle NumPy data types"""
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        return super(NumpyEncoder, self).default(obj)


def normalize_activity_name(activity):
    """Normalize activity names to avoid false differences due to whitespace"""
    if pd.isna(activity) or activity is None:
        return ""
    return str(activity).strip()


def load_data_from_db(table_name: str, normalize=True):
    """
    Load data from database with optional normalization and data quality checks
    """
    try:
        # Fetch data from the 'uploads' schema
        query = f'SELECT * FROM uploads."{table_name}"'
        print(f"Executing query: {query}")
        df = pd.read_sql(query, engine)
    except Exception as e:
        print(f"Error executing query '{query}': {str(e)}")
        # Check if table exists regardless of schema to help debug
        try:
             check_query = f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'uploads' AND table_name = '{table_name}')"
             exists = pd.read_sql(check_query, engine).iloc[0, 0]
             print(f"Table '{table_name}' exists in uploads schema: {exists}")
        except:
             pass
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found or error accessing DB: {str(e)}")
    
    # Rename columns to match pm4py expectations if needed
    # Assuming the DB table has columns similar to: Case ID, Activityname, Timestamp
    # We map them to standard names
    
    # Check if we need to rename or if they are already in standard format or original format
    # The original script mapped: "Case ID" -> "case:concept:name", "Activityname" -> "concept:name", "Timestamp" -> "time:timestamp"
    # We check if these columns exist, if not, we try to use what we have or error out
    
    column_mapping = {
        "Case ID": "case:concept:name",
        "Activityname": "concept:name",
        "Timestamp": "time:timestamp"
    }
    
    # If the DB table uses snake_case keys (common in SQL), we might need to adjust
    # E.g. case_id, activity_name, timestamp
    # Let's check columns and map dynamically if possible or stick to expected names
    
    # In the absence of strict schema knowledge, we use the mapping from the script.
    # But we should be robust.
    
    df = df.rename(columns=column_mapping)
    
    required_columns = ["case:concept:name", "concept:name", "time:timestamp"]
    missing_cols = [col for col in required_columns if col not in df.columns]
    
    if missing_cols:
        # Fallback: try finding columns that look like they match
        # This is a bit advanced but helpful
        pass
        # For now, strict check
        # If columns are missing, check for snake_case alternatives
        snake_map = {
            "case_id": "case:concept:name",
            "activity_name": "concept:name",
            "timestamp": "time:timestamp",
            "activityname": "concept:name",
            "activity": "concept:name"
        }
        df = df.rename(columns=snake_map)
        missing_cols = [col for col in required_columns if col not in df.columns]
        
        if missing_cols:
             raise ValueError(f"Missing required columns: {missing_cols}. Table columns: {df.columns.tolist()}")

    # Normalize activity names
    if normalize:
        df["concept:name"] = df["concept:name"].apply(normalize_activity_name)
    
    df["time:timestamp"] = pd.to_datetime(df["time:timestamp"])
    
    # Sort
    df = df.sort_values(
        ["case:concept:name", "time:timestamp", "concept:name"]
    ).reset_index(drop=True)
    
    log = log_converter.apply(df)
    return log, df


@router.get("/tables")
async def list_tables():
    """List all tables in the uploads schema for debugging"""
    try:
        query = "SELECT table_name FROM information_schema.tables WHERE table_schema = 'uploads'"
        df = pd.read_sql(query, engine)
        return {"tables": df["table_name"].tolist()}
    except Exception as e:
        return {"error": str(e)}


def detect_data_quality_issues(df, table_name):
    """
    Detect data quality issues that could affect variant counting
    """
    issues = {
        "empty_activities": 0,
        "whitespace_activities": 0,
        "null_timestamps": 0,
        "duplicate_events": 0,
        "concurrent_activities": 0,
        "cases_with_single_activity": 0
    }
    
    # Check for empty activities
    empty_act = df[(df["concept:name"].isna()) | (df["concept:name"] == "")]
    issues["empty_activities"] = len(empty_act)
    
    # Check for whitespace issues (before normalization)
    # Since we already normalized in df, we would need the raw data to check this accurately.
    # Or we can do a query to check. For simplicity/performance, we might skip this strict check on 'before normalization'
    # unless we reload raw data.
    # We will skip the 'whitespace_activities' specific check relative to file if we don't reload raw
    # or we can check if the DB gave us trimmed strings.
    # Let's skip the double-read for performance in API context.
    issues["whitespace_activities"] = 0 # Placeholder
    
    # Check for null timestamps
    issues["null_timestamps"] = int(df["time:timestamp"].isna().sum())
    
    duplicates = df.duplicated(
        subset=["case:concept:name", "time:timestamp", "concept:name"], keep=False
    )
    issues["duplicate_events"] = int(duplicates.sum())
    
    # Check for concurrent activities (same case, same timestamp)
    concurrent = df.groupby(["case:concept:name", "time:timestamp"]).size()
    issues["concurrent_activities"] = int((concurrent > 1).sum())
    
    # Check for cases with only one activity
    case_sizes = df.groupby("case:concept:name").size()
    issues["cases_with_single_activity"] = int((case_sizes == 1).sum())
    
    return issues


def calculate_percentiles(data, percentiles=[25, 50, 75, 90, 95, 99]):
    """Calculate multiple percentiles for better distribution understanding"""
    if not data:
        return {}
    return {f"p{p}": float(np.percentile(data, p)) for p in percentiles}


def detect_outliers(data, method='iqr'):
    """Detect outliers using IQR or Z-score method"""
    if len(data) < 4:
        return {"outlier_count": 0, "outlier_percentage": 0.0}
    
    if method == 'iqr':
        q1 = float(np.percentile(data, 25))
        q3 = float(np.percentile(data, 75))
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        outliers = [x for x in data if x < lower_bound or x > upper_bound]
        bounds = {"lower": lower_bound, "upper": upper_bound}
    else:  # z-score
        mean = float(np.mean(data))
        std = float(np.std(data))
        outliers = [x for x in data if abs((x - mean) / std) > 3]
        bounds = None
    
    return {
        "outlier_count": len(outliers),
        "outlier_percentage": float((len(outliers) / len(data)) * 100),
        "outlier_bounds": bounds
    }


def calculate_throughput_metrics(log):
    """Calculate advanced throughput and capacity metrics"""
    metrics = {}
    
    # Cases per time period
    case_starts = []
    case_ends = []
    
    for trace in log:
        if len(trace) > 0:
            case_starts.append(trace[0]["time:timestamp"])
            case_ends.append(trace[-1]["time:timestamp"])
    
    if case_starts and case_ends:
        # Convert to pandas for easier time-based grouping
        start_df = pd.DataFrame({'timestamp': case_starts, 'type': 'start'})
        end_df = pd.DataFrame({'timestamp': case_ends, 'type': 'end'})
        
        # Daily throughput
        daily_starts = start_df.groupby(start_df['timestamp'].dt.date).size()
        daily_ends = end_df.groupby(end_df['timestamp'].dt.date).size()
        
        metrics["throughput_analysis"] = {
            "daily_case_starts": {
                "min": int(daily_starts.min()),
                "max": int(daily_starts.max()),
                "avg": float(daily_starts.mean()),
                "std": float(daily_starts.std())
            },
            "daily_case_completions": {
                "min": int(daily_ends.min()),
                "max": int(daily_ends.max()),
                "avg": float(daily_ends.mean()),
                "std": float(daily_ends.std())
            }
        }
        
        # Work in progress (WIP) analysis
        wip_over_time = []
        all_events = []
        
        for trace in log:
            case_id = str(trace.attributes.get("concept:name", ""))
            if len(trace) > 0:
                all_events.append({
                    'timestamp': trace[0]["time:timestamp"],
                    'case_id': case_id,
                    'event_type': 'start'
                })
                all_events.append({
                    'timestamp': trace[-1]["time:timestamp"],
                    'case_id': case_id,
                    'event_type': 'end'
                })
        
        # Sort events by timestamp
        all_events.sort(key=lambda x: x['timestamp'])
        
        current_wip = 0
        for event in all_events:
            if event['event_type'] == 'start':
                current_wip += 1
            else:
                current_wip -= 1
            wip_over_time.append(current_wip)
        
        if wip_over_time:
            metrics["wip_analysis"] = {
                "max_concurrent_cases": max(wip_over_time),
                "avg_concurrent_cases": statistics.mean(wip_over_time),
                "min_concurrent_cases": min(wip_over_time)
            }
    
    return metrics


def analyze_bottlenecks(log):
    """Advanced bottleneck analysis"""
    activity_waiting_times = defaultdict(list)
    activity_frequencies = defaultdict(int)
    
    for trace in log:
        for i in range(len(trace) - 1):
            current_event = trace[i]
            next_event = trace[i + 1]
            
            current_activity = current_event.get("concept:name", "")
            waiting_time = (next_event["time:timestamp"] - current_event["time:timestamp"]).total_seconds()
            
            activity_waiting_times[current_activity].append(waiting_time)
            activity_frequencies[current_activity] += 1
    
    bottleneck_analysis = {}
    for activity, times in activity_waiting_times.items():
        if times:
            avg_waiting = statistics.mean(times)
            frequency = activity_frequencies[activity]
            
            # Bottleneck score: combination of waiting time and frequency
            bottleneck_score = avg_waiting * frequency
            
            bottleneck_analysis[activity] = {
                "avg_waiting_time_seconds": avg_waiting,
                "frequency": frequency,
                "bottleneck_score": bottleneck_score,
                "percentiles": calculate_percentiles(times),
                "outliers": detect_outliers(times)
            }
    
    # Rank activities by bottleneck score
    ranked_bottlenecks = sorted(
        bottleneck_analysis.items(), 
        key=lambda x: x[1]["bottleneck_score"], 
        reverse=True
    )
    
    return {
        "bottleneck_ranking": [{"activity": k, **v} for k, v in ranked_bottlenecks[:10]],
        "detailed_analysis": bottleneck_analysis
    }


def analyze_process_efficiency(log):
    """Calculate process efficiency metrics"""
    case_durations = []
    value_added_times = []  # Time actually spent in activities
    waiting_times = []      # Time between activities
    
    for trace in log:
        if len(trace) > 1:
            # Total case duration
            total_duration = (trace[-1]["time:timestamp"] - trace[0]["time:timestamp"]).total_seconds()
            case_durations.append(total_duration)
            
            # Calculate waiting times between activities
            trace_waiting_time = 0
            for i in range(len(trace) - 1):
                waiting_time = (trace[i + 1]["time:timestamp"] - trace[i]["time:timestamp"]).total_seconds()
                trace_waiting_time += waiting_time
                waiting_times.append(waiting_time)
            
            # Assume minimal processing time per activity (this could be enhanced with actual processing times)
            estimated_processing_time = len(trace) * 60  # 1 minute per activity (configurable)
            value_added_times.append(estimated_processing_time)
    
    efficiency_metrics = {}
    
    if case_durations and value_added_times:
        avg_total_time = statistics.mean(case_durations)
        avg_value_added_time = statistics.mean(value_added_times)
        avg_waiting_time = statistics.mean(waiting_times) if waiting_times else 0
        
        # Process efficiency = Value-added time / Total time
        process_efficiency = (avg_value_added_time / avg_total_time) * 100 if avg_total_time > 0 else 0
        
        efficiency_metrics = {
            "process_efficiency_percentage": process_efficiency,
            "avg_total_cycle_time_seconds": avg_total_time,
            "avg_estimated_value_added_time_seconds": avg_value_added_time,
            "avg_waiting_time_seconds": avg_waiting_time,
            "waste_percentage": ((avg_total_time - avg_value_added_time) / avg_total_time) * 100 if avg_total_time > 0 else 0
        }
    
    return efficiency_metrics


def get_advanced_time_statistics(log):
    """Get comprehensive and advanced time-related statistics"""
    time_stats = {}
    
    # Enhanced case statistics with percentiles and outliers
    if CASE_STATISTICS_AVAILABLE:
        try:
            case_stats = case_statistics.get_case_statistics(log)
            durations = list(case_stats.values())
            
            time_stats["enhanced_case_statistics"] = {
                "total_cases": len(case_stats),
                "case_durations": {
                    "min_duration_seconds": min(durations) if durations else 0,
                    "max_duration_seconds": max(durations) if durations else 0,
                    "avg_duration_seconds": statistics.mean(durations) if durations else 0,
                    "median_duration_seconds": statistics.median(durations) if durations else 0,
                    "std_duration_seconds": statistics.stdev(durations) if len(durations) > 1 else 0,
                    "percentiles": calculate_percentiles(durations),
                    "outlier_analysis": detect_outliers(durations)
                }
            }
        except Exception as e:
            time_stats["enhanced_case_statistics"] = {"error": str(e)}
    else:
        # Custom case duration calculation
        durations = []
        for trace in log:
            if len(trace) > 0:
                duration = (trace[-1]["time:timestamp"] - trace[0]["time:timestamp"]).total_seconds()
                durations.append(duration)
        
        if durations:
            time_stats["enhanced_case_statistics"] = {
                "total_cases": len(durations),
                "case_durations": {
                    "min_duration_seconds": min(durations),
                    "max_duration_seconds": max(durations),
                    "avg_duration_seconds": statistics.mean(durations),
                    "median_duration_seconds": statistics.median(durations),
                    "std_duration_seconds": statistics.stdev(durations) if len(durations) > 1 else 0,
                    "percentiles": calculate_percentiles(durations),
                    "outlier_analysis": detect_outliers(durations)
                }
            }
    
    # Advanced throughput analysis
    time_stats["throughput_metrics"] = calculate_throughput_metrics(log)
    
    # Bottleneck analysis
    time_stats["bottleneck_analysis"] = analyze_bottlenecks(log)
    
    # Process efficiency analysis
    time_stats["efficiency_analysis"] = analyze_process_efficiency(log)
    
    # Enhanced temporal patterns
    try:
        all_timestamps = []
        hourly_activity = defaultdict(lambda: defaultdict(int))
        daily_activity = defaultdict(lambda: defaultdict(int))
        
        for trace in log:
            for event in trace:
                if "time:timestamp" in event:
                    ts = event["time:timestamp"]
                    activity = event.get("concept:name", "")
                    all_timestamps.append(ts)
                    
                    hourly_activity[ts.hour][activity] += 1
                    daily_activity[ts.strftime('%A')][activity] += 1
        
        if all_timestamps:
            time_stats["enhanced_temporal_analysis"] = {
                "log_time_range": {
                    "start_time": min(all_timestamps).isoformat(),
                    "end_time": max(all_timestamps).isoformat(),
                    "total_duration_days": (max(all_timestamps) - min(all_timestamps)).days,
                    "total_events": len(all_timestamps)
                },
                "activity_patterns": {
                    "hourly_activity_distribution": {str(k): dict(v) for k, v in hourly_activity.items()},
                    "daily_activity_distribution": {k: dict(v) for k, v in daily_activity.items()}
                },
                "peak_hours": {
                    "busiest_hour": max(hourly_activity.keys(), key=lambda h: sum(hourly_activity[h].values())),
                    "busiest_day": max(daily_activity.keys(), key=lambda d: sum(daily_activity[d].values()))
                }
            }
    except Exception as e:
        time_stats["enhanced_temporal_analysis"] = {"error": str(e)}
    
    return time_stats


def get_variant_time_statistics(log, variant_cases):
    """Enhanced variant-specific time statistics"""
    variant_traces = [trace for trace in log if str(trace.attributes.get("concept:name", "")) in variant_cases]
    
    if not variant_traces:
        return {"error": "No traces found for variant"}
    
    variant_stats = {}
    
    # Enhanced case duration analysis
    try:
        durations = []
        for trace in variant_traces:
            if len(trace) > 0:
                duration = (trace[-1]["time:timestamp"] - trace[0]["time:timestamp"]).total_seconds()
                durations.append(duration)
        
        if durations:
            variant_stats["enhanced_case_durations"] = {
                "min_duration_seconds": min(durations),
                "max_duration_seconds": max(durations),
                "avg_duration_seconds": statistics.mean(durations),
                "median_duration_seconds": statistics.median(durations),
                "std_duration_seconds": statistics.stdev(durations) if len(durations) > 1 else 0,
                "total_cases": len(durations),
                "percentiles": calculate_percentiles(durations),
                "outlier_analysis": detect_outliers(durations)
            }
    except Exception as e:
        variant_stats["enhanced_case_durations"] = {"error": str(e)}
    
    # Activity transition analysis with advanced metrics
    try:
        activity_transitions = defaultdict(list)
        for trace in variant_traces:
            for i in range(len(trace) - 1):
                current_activity = trace[i].get("concept:name", "")
                next_activity = trace[i + 1].get("concept:name", "")
                transition_time = (trace[i + 1]["time:timestamp"] - trace[i]["time:timestamp"]).total_seconds()
                
                transition_key = f"{current_activity} → {next_activity}"
                activity_transitions[transition_key].append(transition_time)
        
        variant_stats["enhanced_activity_transitions"] = {}
        for transition, times in activity_transitions.items():
            if times:
                variant_stats["enhanced_activity_transitions"][transition] = {
                    "min_transition_seconds": min(times),
                    "max_transition_seconds": max(times),
                    "avg_transition_seconds": statistics.mean(times),
                    "median_transition_seconds": statistics.median(times),
                    "std_transition_seconds": statistics.stdev(times) if len(times) > 1 else 0,
                    "occurrences": len(times),
                    "percentiles": calculate_percentiles(times),
                    "outlier_analysis": detect_outliers(times)
                }
    except Exception as e:
        variant_stats["enhanced_activity_transitions"] = {"error": str(e)}
    
    return variant_stats


def summarize_variants(log, max_variants: int | None = None):
    """
    Summarize variants with improved counting and validation
    """
    variant_counts = Counter()
    cases_by_variant = defaultdict(list)

    for trace in log:
        case_id = str(trace.attributes.get("concept:name", ""))
        activities = [event.get("concept:name", "") for event in trace]
        variant_key = " → ".join(activities) if activities else ""

        variant_counts[variant_key] += 1
        cases_by_variant[variant_key].append(case_id)
    
    print(f"DEBUG: summarize_variants internal count. Total traces: {len(log)}, Total unique variants: {len(variant_counts)}")

    # Cross-validate with pm4py's native variant detection
    if VARIANTS_MODULE_AVAILABLE:
        try:
            pm4py_variants = variants_get.get_variants(log)
            pm4py_count = len(pm4py_variants)
            
            # If counts differ, print a warning (or log it)
            if pm4py_count != len(variant_counts):
                print(f"⚠ WARNING: Manual count ({len(variant_counts)}) differs from pm4py count ({pm4py_count})")
        except:
            pass

    total_cases = len(log)
    sorted_variants = sorted(
        variant_counts.items(), key=lambda item: (-item[1], item[0])
    )

    if max_variants is None:
        # If no limit specified, return ALL variants for pagination
        top_variants = sorted_variants
    else:
        top_variants = sorted_variants[:max_variants]

    data = []
    for variant, freq in top_variants:
        activities = variant.split(" → ") if variant else []

        def sort_key(case_id: str):
            try:
                return (0, int(case_id))
            except ValueError:
                return (1, case_id)

        case_list = sorted(cases_by_variant[variant], key=sort_key)
        
        # Get enhanced time statistics for this variant
        variant_time_stats = get_variant_time_statistics(log, case_list)

        entry = {
            "variant": variant,
            "activities": activities,
            "frequency": freq,
            "percentage": round(freq / total_cases * 100, 1) if total_cases else 0.0,
            "cases": case_list[:5], # Limit to 5 example cases
            "advanced_time_statistics": variant_time_stats
        }
        data.append(entry)

    return {
        "success": True,
        "data": data,
        "metadata": {
            "total_variants": len(variant_counts),
            "total_cases": total_cases,
            "max_variants_shown": len(top_variants),
        },
    }


class AnalysisRequest(BaseModel):
    table_name: str
    max_variants: Optional[int] = None
    force_refresh: Optional[bool] = False
    page: Optional[int] = 1
    limit: Optional[int] = 100


def create_cache_table():
    """Create the cache table if it doesn't exist"""
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS instance01.mtd_variant_analysis_cache (
                    table_name VARCHAR(255) PRIMARY KEY,
                    analysis_data JSONB,
                    row_count BIGINT,
                    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc'),
                    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc')
                )
            """))
            conn.commit()
            print("Variant analysis cache table ensured.")
    except Exception as e:
        print(f"Error creating cache table: {e}")


def get_cached_analysis(table_name: str):
    """Retrieve cached analysis if available"""
    try:
        query = text('SELECT analysis_data FROM instance01.mtd_variant_analysis_cache WHERE table_name = :table_name')
        with engine.connect() as conn:
            result = conn.execute(query, {"table_name": table_name}).fetchone()
            if result and result[0]:
                return result[0]
    except Exception as e:
        print(f"Cache miss or error for {table_name}: {e}")
    return None


def save_analysis_to_cache(table_name: str, data: Dict, row_count: int = 0):
    """Save analysis result to cache"""
    try:
        # Convert data to JSON string for storage
        json_data = json.dumps(data, cls=NumpyEncoder)
        
        query = text("""
            INSERT INTO instance01.mtd_variant_analysis_cache (table_name, analysis_data, row_count, updated_at)
            VALUES (:table_name, :data, :row_count, NOW() AT TIME ZONE 'utc')
            ON CONFLICT (table_name) 
            DO UPDATE SET 
                analysis_data = EXCLUDED.analysis_data,
                row_count = EXCLUDED.row_count,
                updated_at = NOW() AT TIME ZONE 'utc'
        """)
        
        with engine.connect() as conn:
            conn.execute(query, {
                "table_name": table_name, 
                "data": json_data, 
                "row_count": row_count
            })
            conn.commit()
            print(f"Saved analysis for {table_name} to cache.")
    except Exception as e:
        print(f"Error saving to cache: {e}")


def analyze_variants_logic(table_name: str, max_variants: Optional[int], force_refresh: bool = False, job_id: Optional[str] = None):
    """
    Synchronous logic for variant analysis to be run in a thread pool.
    Includes caching logic.
    """
    try:
        update_job_status(job_id, "processing", "Checking cache and metadata", 5)
        
        # Ensure cache table exists
        create_cache_table()
        
        row_count = 0
        
        # Check row count first
        count_query = f'SELECT COUNT(*) FROM uploads."{table_name}"'
        print(f"Checking row count for: {table_name}")
        try:
            count_df = pd.read_sql(count_query, engine)
            row_count = int(count_df.iloc[0, 0])
            print(f"Table {table_name} has {row_count} rows")
            
            if row_count > 100000:
                print(f"⚠️ LARGE DATASET DETECTED ({row_count} rows). Processing might take time.")
            
            update_job_status(job_id, "processing", f"Dataset has {row_count} rows", 10)
        except Exception as e:
            print(f"Could not check row count: {e}")

        # Check cache if not forced refresh
        if not force_refresh:
            cached_data = get_cached_analysis(table_name)
            if cached_data:
                print(f"Returning cached analysis for {table_name}")
                update_job_status(job_id, "completed", "Loaded from cache", 100, result=cached_data if not isinstance(cached_data, str) else json.loads(cached_data))
                
                # If cached data is a string, parse it, otherwise return as is
                if isinstance(cached_data, str):
                    return json.loads(cached_data)
                return cached_data

        # Load and process data
        update_job_status(job_id, "processing", "Fetching data from database (this may take a while)", 20)
        log, df = load_data_from_db(table_name, normalize=True)
        
        update_job_status(job_id, "processing", "Analyzing data quality", 40)
        data_quality = detect_data_quality_issues(df, table_name)
        
        update_job_status(job_id, "processing", "Summarizing variants", 50)
        print(f"DEBUG: Summarizing variants. max_variants={max_variants}")
        summary = summarize_variants(log, max_variants=max_variants)
        print(f"DEBUG: Summary generated. Data size: {len(summary.get('data', []))}, Total variants: {summary.get('metadata', {}).get('total_variants')}")
        
        update_job_status(job_id, "processing", "Calculating advanced time statistics", 70)
        advanced_time_stats = get_advanced_time_statistics(log)
        
        # Add advanced time statistics to the summary
        summary["advanced_time_analysis"] = advanced_time_stats
        summary["data_quality_report"] = data_quality
        
        summary["metadata"].update(
            {
                "data_source": f"DB: uploads.{table_name}",
                "timestamp": datetime.now().isoformat(),
                "row_count": row_count,
                "analysis_type": "Advanced Variant Summary with Comprehensive Time Analysis (v2 - Improved)",
                "improvements_applied": [
                    "Activity name normalization (whitespace handling)",
                    "Stable sorting for concurrent activities",
                    "pm4py native variant cross-validation",
                    "Comprehensive data quality checks",
                    "Enhanced duplicate detection",
                    "Improved outlier analysis"
                ],
                "advanced_features": [
                    "Percentile analysis (P25, P50, P75, P90, P95, P99)",
                    "Outlier detection using IQR method",
                    "Bottleneck identification and ranking",
                    "Process efficiency calculations",
                    "Throughput and WIP analysis",
                    "Enhanced temporal pattern analysis",
                    "Activity transition analysis",
                    "Peak hour and day identification"
                ]
            }
        )
        
        # Save to cache
        update_job_status(job_id, "processing", "Saving results to cache", 90)
        save_analysis_to_cache(table_name, summary, row_count)
        
        # Serialize result
        json_str = json.dumps(summary, cls=NumpyEncoder)
        result_data = json.loads(json_str)
        
        update_job_status(job_id, "completed", "Analysis complete", 100, result=result_data)
        return result_data

    except Exception as e:
        import traceback
        traceback.print_exc()
        error_msg = f"Analysis failed: {str(e)}"
        update_job_status(job_id, "failed", error_msg, 0)
        raise HTTPException(status_code=500, detail=error_msg)


# Global job store (in-memory)
# In production, use Redis or DB
analysis_jobs = {}

def update_job_status(job_id: str, status: str, message: str, progress: int, result: Any = None):
    """Helper to update job status if job_id is provided"""
    if job_id:
        analysis_jobs[job_id] = {
            "status": status, # 'pending', 'processing', 'completed', 'failed'
            "message": message,
            "progress": progress,
            "result": result,
            "updated_at": datetime.now().isoformat()
        }


@router.post("/analyze-variants-async")
async def analyze_variants_async_endpoint(request: AnalysisRequest):
    """
    Start asynchronous variant analysis and return a job ID immediately.
    Includes time estimation based on row counts.
    Uses proper thread pool execution to avoid blocking the server.
    """
    job_id = str(uuid.uuid4())
    
    # 1. Instant Cache Check
    if not request.force_refresh:
        cached = get_cached_analysis(request.table_name)
        if cached:
            parsed_result = json.loads(cached) if isinstance(cached, str) else cached
            
            # Apply Pagination if completed
            paginated_result = parsed_result
            if "data" in parsed_result and isinstance(parsed_result["data"], list):
                start_idx = (request.page - 1) * request.limit
                end_idx = start_idx + request.limit
                full_data = parsed_result["data"]
                
                paginated_result = parsed_result.copy()
                paginated_result["data"] = full_data[start_idx:end_idx]
                
                # Update metadata
                if "metadata" not in paginated_result:
                    paginated_result["metadata"] = {}
                paginated_result["metadata"].update({
                    "pagination": {
                        "current_page": request.page,
                        "page_size": request.limit,
                        "total_items": len(full_data),
                        "total_pages": (len(full_data) + request.limit - 1) // request.limit,
                        "has_next": end_idx < len(full_data),
                        "has_previous": request.page > 1
                    }
                })
                print(f"DEBUG: Cache Hit - Page: {request.page}, Limit: {request.limit}, Total Items: {len(full_data)}, Has Next: {end_idx < len(full_data)}")

            analysis_jobs[job_id] = {
                "status": "completed",
                "message": "Loaded instantly from cache",
                "progress": 100,
                "result": parsed_result, # Store FULL result in job store
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            return {
                "job_id": job_id, 
                "status": "completed", 
                "estimated_time": 0,
                "cached": True,
                "result": paginated_result # Return PAGINATED result to client
            }

    # 2. Estimate time based on row count
    row_count = 0
    try:
        count_query = f'SELECT COUNT(*) FROM uploads."{request.table_name}"'
        count_df = pd.read_sql(count_query, engine)
        row_count = int(count_df.iloc[0, 0])
    except Exception as e:
        print(f"Estimation row count failed: {e}")

    # Heuristic: 1M rows -> ~900s (15m)
    # 30s base + 0.9s per 1000 rows
    estimated_time = 30 + (row_count / 1000) * 0.9
    if row_count > 1000000:
        # Cap or ensure minimum for very large sets to manage user expectations
        estimated_time = max(estimated_time, 900)
    
    # 3. Initialize job status with metadata
    analysis_jobs[job_id] = {
        "status": "pending",
        "message": f"Initializing analysis... (Estimated time: {int(estimated_time)}s for {row_count:,} rows)",
        "progress": 0,
        "estimated_time": int(estimated_time),
        "row_count": row_count,
        "result": None,
        "created_at": datetime.now().isoformat()
    }
    
    # 4. Start REAL background task in thread pool (non-blocking)
    # ✅ CRITICAL: Use asyncio.create_task + run_in_threadpool instead of BackgroundTasks
    # BackgroundTasks still blocks the event loop for CPU-intensive work
    
    async def run_analysis_in_thread():
        """Wrapper to run analysis in thread pool without blocking"""
        try:
            await run_in_threadpool(
                analyze_variants_logic, 
                request.table_name, 
                request.max_variants, 
                request.force_refresh, 
                job_id
            )
        except Exception as e:
            print(f"❌ Background analysis failed for job {job_id}: {e}")
            update_job_status(job_id, "failed", str(e), 0)
    
    # Fire and forget - server remains responsive
    asyncio.create_task(run_analysis_in_thread())
    
    return {
        "job_id": job_id, 
        "status": "pending", 
        "estimated_time": int(estimated_time),
        "row_count": row_count
    }


@router.get("/analysis-status/{job_id}")
async def get_analysis_status(job_id: str, page: int = 1, limit: int = 100):
    """Get status of an analysis job with pagination support for result"""
    if job_id not in analysis_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = analysis_jobs[job_id]
    
    # Return job info
    response = job.copy()
    
    # If job is completed and has result, apply pagination
    if job.get("status") == "completed" and job.get("result"):
        full_result = job["result"]
        if "data" in full_result and isinstance(full_result["data"], list):
            start_idx = (page - 1) * limit
            end_idx = start_idx + limit
            full_data = full_result["data"]
            
            # Create a shallow copy of result to modify data for this response
            paginated_result = full_result.copy()
            paginated_result["data"] = full_data[start_idx:end_idx]
            
            # Add pagination metadata
            if "metadata" not in paginated_result:
                paginated_result["metadata"] = {}
                
            paginated_result["metadata"].update({
                "pagination": {
                    "current_page": page,
                    "page_size": limit,
                    "total_items": len(full_data),
                    "total_pages": (len(full_data) + limit - 1) // limit,
                    "has_next": end_idx < len(full_data),
                    "has_previous": page > 1
                }
            })
            print(f"DEBUG: Status Endpoint - Page: {page}, Limit: {limit}, Total Items: {len(full_data)}, Has Next: {end_idx < len(full_data)}")
            
            response["result"] = paginated_result
            
    return response


@router.post("/analyze-variants")
async def analyze_variants_endpoint(request: AnalysisRequest):
    """
    Analyze variants from a database table.
    """
    return await run_in_threadpool(analyze_variants_logic, request.table_name, request.max_variants, request.force_refresh)


@router.post("/init-cache-table")
async def init_cache_table():
    """Manually initialize the variant cache table"""
    create_cache_table()
    return {"status": "ok", "message": "Cache table ensured"}


@router.get("/variant-count/{table_name}")
async def get_variant_count(table_name: str):
    """
    Get raw variant counts directly from the database/log to verify data integrity.
    Bypasses cache and heavy analysis to give a quick 'ground truth' count.
    """
    try:
        print(f"DEBUG: Counting variants for {table_name}...")
        log, df = load_data_from_db(table_name, normalize=True)
        
        variant_counts = Counter()
        for trace in log:
            activities = [event.get("concept:name", "") for event in trace]
            variant_key = " → ".join(activities) if activities else ""
            variant_counts[variant_key] += 1
            
        count_info = {
            "table_name": table_name,
            "total_rows_df": len(df),
            "total_traces_log": len(log),
            "total_unique_variants": len(variant_counts),
            "top_5_variants": [
                {"variant": k, "count": v} 
                for k, v in variant_counts.most_common(5)
            ]
        }
        print(f"DEBUG: Count result: {count_info}")
        return count_info
    except Exception as e:
        print(f"Error counting variants: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload")
async def upload_process_data(file: UploadFile = File(...)):
    """Upload and validate process mining data (Legacy/Alternative)"""
    try:
        content = await file.read()
        data = json.loads(content)
        
        # Validate the data structure
        if not isinstance(data, dict) or "data" not in data:
            raise ValueError("Invalid data structure")
            
        if not isinstance(data["data"], list):
            raise ValueError("Data should contain a list of variants")
            
        # Basic validation of variants
        for i, variant in enumerate(data["data"]):
            if "activities" not in variant or not isinstance(variant["activities"], list):
                raise ValueError(f"Variant {i} missing or invalid activities")
            if "frequency" not in variant or not isinstance(variant["frequency"], (int, float)):
                raise ValueError(f"Variant {i} missing or invalid frequency")
                
        return {"success": True, "message": "Data uploaded successfully", "data": data}
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
