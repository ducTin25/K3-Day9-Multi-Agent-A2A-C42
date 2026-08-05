"""Delivery tools and timestamp comparison for DeliveryAgent (Member 4 / TV4)."""

import csv
import os
from typing import Any, Dict, List, Optional


def get_delivery_timeline(order_id: str, data_dir: Optional[str] = None, repository: Any = None) -> Dict[str, Any]:
    """Retrieve delivery timestamps for a given order_id.
    
    Returns:
        dict containing order_id, delivered_carrier_at, delivered_customer_at, estimated_delivery_at.
    """
    if repository and hasattr(repository, "get_delivery_timeline"):
        return repository.get_delivery_timeline(order_id)
        
    if data_dir is None:
        data_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data")
        
    orders_csv = os.path.join(data_dir, "olist_orders_dataset.csv")
    if os.path.exists(orders_csv):
        with open(orders_csv, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("order_id") == order_id:
                    deliv_carr = row.get("order_delivered_carrier_date")
                    deliv_cust = row.get("order_delivered_customer_date")
                    est_deliv = row.get("order_estimated_delivery_date")
                    return {
                        "order_id": order_id,
                        "delivered_carrier_at": deliv_carr if deliv_carr else None,
                        "delivered_customer_at": deliv_cust if deliv_cust else None,
                        "estimated_delivery_at": est_deliv if est_deliv else None,
                    }

    return {
        "order_id": order_id,
        "delivered_carrier_at": None,
        "delivered_customer_at": None,
        "estimated_delivery_at": None,
    }


def get_shipping_limits(order_id: str, data_dir: Optional[str] = None, repository: Any = None) -> List[Dict[str, Any]]:
    """Retrieve item shipping limits and seller info for a given order_id.
    
    Returns:
        List of dicts containing order_item_id, seller_id, shipping_limit_date.
    """
    if repository and hasattr(repository, "get_shipping_limits"):
        return repository.get_shipping_limits(order_id)
        
    if data_dir is None:
        data_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data")
        
    items_csv = os.path.join(data_dir, "olist_order_items_dataset.csv")
    items = []
    if os.path.exists(items_csv):
        with open(items_csv, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("order_id") == order_id:
                    item_id_raw = row.get("order_item_id")
                    limit = row.get("shipping_limit_date")
                    items.append({
                        "order_item_id": int(item_id_raw) if item_id_raw else 1,
                        "seller_id": row.get("seller_id", ""),
                        "shipping_limit_date": limit if limit else None,
                    })
    return items


def compare_delivery_timestamps(
    order_id: str,
    delivery_timeline: Dict[str, Any],
    shipping_limits: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Compare delivery timestamps against estimated delivery date and seller shipping limits.
    
    Constructs DeliveryFacts contract output.
    """
    deliv_cust = delivery_timeline.get("delivered_customer_at")
    est_deliv = delivery_timeline.get("estimated_delivery_at")
    deliv_carr = delivery_timeline.get("delivered_carrier_at")
    
    warnings = []
    seller_violations = []
    evidence_ids = [f"order:{order_id}"]
    
    if not deliv_cust or not est_deliv:
        if not deliv_cust:
            warnings.append("Missing delivered_customer_at timestamp")
        if not est_deliv:
            warnings.append("Missing estimated_delivery_at timestamp")
            
        return {
            "order_id": order_id,
            "delivered_customer_at": deliv_cust,
            "estimated_delivery_at": est_deliv,
            "delivered_carrier_at": deliv_carr,
            "is_delivered_late": False,
            "seller_handoff_violations": [],
            "late_stage": "undetermined",
            "evidence_ids": sorted(list(set(evidence_ids))),
            "warnings": warnings,
        }
        
    # Compare timestamps (ISO strings compare correctly directly)
    is_delivered_late = str(deliv_cust) > str(est_deliv)
    
    if not is_delivered_late:
        late_stage = "not_late"
    else:
        # Check seller handoff violations
        if deliv_carr:
            for item in shipping_limits:
                limit = item.get("shipping_limit_date")
                if limit and str(deliv_carr) > str(limit):
                    item_id = item.get("order_item_id")
                    seller_id = item.get("seller_id")
                    seller_violations.append({
                        "order_item_id": item_id,
                        "seller_id": seller_id,
                        "shipping_limit_date": limit,
                        "delivered_carrier_at": deliv_carr,
                    })
                    if item_id is not None:
                        evidence_ids.append(f"item:{order_id}:{item_id}")
                    if seller_id:
                        evidence_ids.append(f"seller:{seller_id}")
                        
        if len(seller_violations) > 0:
            late_stage = "seller"
        else:
            late_stage = "logistics"
            
    return {
        "order_id": order_id,
        "delivered_customer_at": deliv_cust,
        "estimated_delivery_at": est_deliv,
        "delivered_carrier_at": deliv_carr,
        "is_delivered_late": is_delivered_late,
        "seller_handoff_violations": seller_violations,
        "late_stage": late_stage,
        "evidence_ids": sorted(list(set(evidence_ids))),
        "warnings": warnings,
    }
