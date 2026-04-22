"""
Elasticsearch Integration
- Index mapping for need_records (geo_point, keyword, float fields)
- Heatmap aggregation queries
- Ward-level urgency aggregations
- Resource gap detection
"""
import logging
from typing import Optional
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

try:
    from elasticsearch import AsyncElasticsearch
    ES_AVAILABLE = True
except ImportError:
    ES_AVAILABLE = False
    logger.warning("elasticsearch not installed — geo queries disabled")

NEEDS_INDEX = "nexus_needs"
WARDS_INDEX = "nexus_ward_stats"

# ── Index mappings ────────────────────────────────────────────
NEEDS_MAPPING = {
    "mappings": {
        "properties": {
            "need_id":           {"type": "keyword"},
            "tenant_id":         {"type": "keyword"},
            "household_id":      {"type": "keyword"},
            "ward_id":           {"type": "keyword"},
            "category":          {"type": "keyword"},
            "subcategory":       {"type": "keyword"},
            "status":            {"type": "keyword"},
            "source_type":       {"type": "keyword"},
            "language_detected": {"type": "keyword"},
            # Geo
            "location":          {"type": "geo_point"},
            # Scoring
            "urgency_score":     {"type": "float"},
            "severity_score":    {"type": "float"},
            "nlp_confidence":    {"type": "float"},
            "beneficiary_count": {"type": "integer"},
            # Vulnerability flags
            "has_child":         {"type": "boolean"},
            "has_elderly":       {"type": "boolean"},
            "has_disabled":      {"type": "boolean"},
            "has_pregnant":      {"type": "boolean"},
            # Text
            "description": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            # Dates
            "ingested_at":       {"type": "date"},
            "reported_at":       {"type": "date"},
            "updated_at":        {"type": "date"},
        }
    },
    "settings": {
        "number_of_shards":   1,
        "number_of_replicas": 0,
        "refresh_interval":   "5s",
    }
}

WARD_STATS_MAPPING = {
    "mappings": {
        "properties": {
            "tenant_id":              {"type": "keyword"},
            "ward_id":                {"type": "keyword"},
            "centroid":               {"type": "geo_point"},
            "avg_urgency_score":      {"type": "float"},
            "max_urgency_score":      {"type": "float"},
            "total_needs_open":       {"type": "integer"},
            "active_tasks_count":     {"type": "integer"},
            "coverage_ratio":         {"type": "float"},
            "is_resource_desert":     {"type": "boolean"},
            "chronic_household_count":{"type": "integer"},
            "category_breakdown":     {"type": "object"},
            "computed_at":            {"type": "date"},
        }
    }
}


# ── ES client factory ─────────────────────────────────────────
_es_client: Optional["AsyncElasticsearch"] = None

def get_es_client(url: str = "http://localhost:9200") -> Optional["AsyncElasticsearch"]:
    global _es_client
    if not ES_AVAILABLE:
        return None
    if _es_client is None:
        _es_client = AsyncElasticsearch([url])
    return _es_client


async def ensure_indexes(es_url: str = "http://localhost:9200") -> None:
    """Create ES indexes if they do not exist. Call at service startup."""
    es = get_es_client(es_url)
    if not es:
        return
    try:
        if not await es.indices.exists(index=NEEDS_INDEX):
            await es.indices.create(index=NEEDS_INDEX, body=NEEDS_MAPPING)
            logger.info(f"Created ES index: {NEEDS_INDEX}")
        if not await es.indices.exists(index=WARDS_INDEX):
            await es.indices.create(index=WARDS_INDEX, body=WARD_STATS_MAPPING)
            logger.info(f"Created ES index: {WARDS_INDEX}")
    except Exception as e:
        logger.error(f"ES index creation failed: {e}")


# ── Index a need record ───────────────────────────────────────
async def index_need(need: dict, es_url: str = "http://localhost:9200") -> None:
    """Upsert a need record into Elasticsearch."""
    es = get_es_client(es_url)
    if not es:
        return
    try:
        doc = {
            "need_id":           str(need.get("need_id", "")),
            "tenant_id":         str(need.get("tenant_id", "")),
            "household_id":      str(need.get("household_id", "")) if need.get("household_id") else None,
            "ward_id":           need.get("ward_id"),
            "category":          need.get("category"),
            "subcategory":       need.get("subcategory"),
            "status":            need.get("status", "unverified"),
            "source_type":       need.get("source_type"),
            "language_detected": need.get("language_detected"),
            "urgency_score":     need.get("urgency_score", 0.5),
            "severity_score":    need.get("severity_score", 0.5),
            "nlp_confidence":    need.get("nlp_confidence", 0.0),
            "beneficiary_count": need.get("beneficiary_count", 1),
            "description":       need.get("description", ""),
            "ingested_at":       need.get("ingested_at"),
            "reported_at":       need.get("reported_at"),
            "updated_at":        need.get("updated_at"),
        }

        # Vulnerability flags flatten
        vf = need.get("vulnerability_flags", {})
        doc["has_child"]    = vf.get("has_child",    False)
        doc["has_elderly"]  = vf.get("has_elderly",  False)
        doc["has_disabled"] = vf.get("has_disabled", False)
        doc["has_pregnant"] = vf.get("has_pregnant", False)

        # Geo point
        lat = need.get("latitude")
        lon = need.get("longitude")
        if lat is not None and lon is not None:
            doc["location"] = {"lat": lat, "lon": lon}

        await es.index(
            index=NEEDS_INDEX,
            id=str(need["need_id"]),
            document=doc,
        )
    except Exception as e:
        logger.error(f"ES index_need failed: {e}")


# ── Heatmap aggregation ───────────────────────────────────────
async def get_heatmap_data(
    tenant_id: str,
    category: Optional[str] = None,
    status_filter: list[str] = None,
    hours_back: int = 168,   # 7 days default
    geo_precision: int = 7,  # geohash precision (~153m cells)
    es_url: str = "http://localhost:9200",
) -> dict:
    """
    Geo-grid aggregation for heatmap visualization.
    Returns geohash buckets with avg urgency and count.
    """
    es = get_es_client(es_url)
    if not es:
        return {"buckets": [], "error": "elasticsearch_unavailable"}

    must_clauses = [
        {"term": {"tenant_id": tenant_id}},
        {"range": {"ingested_at": {
            "gte": f"now-{hours_back}h"
        }}},
    ]
    if category:
        must_clauses.append({"term": {"category": category}})
    if status_filter:
        must_clauses.append({"terms": {"status": status_filter}})

    query = {
        "query": {"bool": {"must": must_clauses}},
        "aggs": {
            "heatmap_grid": {
                "geohash_grid": {
                    "field":     "location",
                    "precision": geo_precision,
                },
                "aggs": {
                    "avg_urgency":   {"avg":   {"field": "urgency_score"}},
                    "max_urgency":   {"max":   {"field": "urgency_score"}},
                    "category_breakdown": {
                        "terms": {"field": "category", "size": 10}
                    },
                }
            },
            "urgency_percentiles": {
                "percentiles": {
                    "field": "urgency_score",
                    "percents": [25, 50, 75, 90, 95],
                }
            }
        },
        "size": 0,   # aggregation only
    }

    try:
        response = await es.search(index=NEEDS_INDEX, body=query)
        buckets = []
        for b in response["aggregations"]["heatmap_grid"]["buckets"]:
            buckets.append({
                "geohash":     b["key"],
                "count":       b["doc_count"],
                "avg_urgency": b["avg_urgency"]["value"],
                "max_urgency": b["max_urgency"]["value"],
                "categories":  {
                    cat["key"]: cat["doc_count"]
                    for cat in b["category_breakdown"]["buckets"]
                },
            })
        percentiles = response["aggregations"]["urgency_percentiles"]["values"]
        return {"buckets": buckets, "percentiles": percentiles, "total": len(buckets)}
    except Exception as e:
        logger.error(f"ES heatmap query failed: {e}")
        return {"buckets": [], "error": str(e)}


# ── Ward urgency aggregation ──────────────────────────────────
async def get_ward_urgency(
    tenant_id: str,
    ward_ids: Optional[list[str]] = None,
    es_url: str = "http://localhost:9200",
) -> list[dict]:
    """Per-ward urgency stats for coordinator dashboard."""
    es = get_es_client(es_url)
    if not es:
        return []

    must = [
        {"term": {"tenant_id": tenant_id}},
        {"terms": {"status": ["unverified","verified","assigned","in_progress"]}},
    ]
    if ward_ids:
        must.append({"terms": {"ward_id": ward_ids}})

    query = {
        "query": {"bool": {"must": must}},
        "aggs": {
            "by_ward": {
                "terms": {"field": "ward_id", "size": 200},
                "aggs": {
                    "avg_urgency":       {"avg": {"field": "urgency_score"}},
                    "max_urgency":       {"max": {"field": "urgency_score"}},
                    "total_beneficiaries":{"sum": {"field": "beneficiary_count"}},
                    "by_category": {"terms": {"field": "category", "size": 10}},
                }
            }
        },
        "size": 0,
    }

    try:
        resp = await es.search(index=NEEDS_INDEX, body=query)
        return [
            {
                "ward_id":             b["key"],
                "open_needs":          b["doc_count"],
                "avg_urgency":         b["avg_urgency"]["value"],
                "max_urgency":         b["max_urgency"]["value"],
                "total_beneficiaries": b["total_beneficiaries"]["value"],
                "category_breakdown":  {c["key"]: c["doc_count"]
                                        for c in b["by_category"]["buckets"]},
            }
            for b in resp["aggregations"]["by_ward"]["buckets"]
        ]
    except Exception as e:
        logger.error(f"ES ward urgency failed: {e}")
        return []


# ── Resource gap detection ────────────────────────────────────
async def detect_resource_deserts(
    tenant_id: str,
    urgency_quartile_threshold: float = 0.70,
    es_url: str = "http://localhost:9200",
) -> list[dict]:
    """
    Identify wards where urgency density is high but no active tasks exist.
    Queries the pre-calculated aggregates in WARDS_INDEX for consistency.
    """
    es = get_es_client(es_url)
    if not es:
        return []

    # Use WARDS_INDEX instead of NEEDS_INDEX to benefit from synced DB logic
    query = {
        "query": {
            "bool": {
                "must": [
                    {"term": {"tenant_id": tenant_id}},
                    {"term": {"is_resource_desert": True}}
                ],
                "filter": [
                    {"range": {"avg_urgency_score": {"gte": urgency_quartile_threshold}}}
                ]
            }
        },
        "sort": [{"avg_urgency_score": {"order": "desc"}}],
        "size": 50
    }

    try:
        resp = await es.search(index=WARDS_INDEX, body=query)
        return [
            {**hit["_source"], "ward_id": hit["_source"].get("ward_id")}
            for hit in resp["hits"]["hits"]
        ]
    except Exception as e:
        logger.error(f"ES desert detection failed: {e}")
        return []


# ── Full-text search ──────────────────────────────────────────
async def search_needs(
    tenant_id: str,
    query_text: str,
    category: Optional[str] = None,
    ward_id: Optional[str] = None,
    min_urgency: float = 0.0,
    limit: int = 20,
    es_url: str = "http://localhost:9200",
) -> list[dict]:
    """Multilingual full-text search across need descriptions."""
    es = get_es_client(es_url)
    if not es:
        return []

    must = [{"term": {"tenant_id": tenant_id}}]
    if category:
        must.append({"term": {"category": category}})
    if ward_id:
        must.append({"term": {"ward_id": ward_id}})
    if min_urgency > 0:
        must.append({"range": {"urgency_score": {"gte": min_urgency}}})

    query = {
        "query": {
            "bool": {
                "must": must,
                "should": [
                    {"match": {"description": {"query": query_text, "boost": 2.0}}},
                ],
                "minimum_should_match": 1,
            }
        },
        "sort": [
            {"_score":        {"order": "desc"}},
            {"urgency_score": {"order": "desc"}},
        ],
        "size": limit,
    }

    try:
        resp = await es.search(index=NEEDS_INDEX, body=query)
        return [
            {**hit["_source"], "_score": hit["_score"]}
            for hit in resp["hits"]["hits"]
        ]
    except Exception as e:
        logger.error(f"ES search_needs failed: {e}")
        return []