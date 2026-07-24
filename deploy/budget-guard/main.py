import base64
import json
import logging
import os

import functions_framework


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("eventhorizon.budget_guard")


def _payload(cloud_event) -> dict:
    try:
        encoded = cloud_event.data.get("message", {}).get("data", "")
        if not encoded:
            return {}
        return json.loads(base64.b64decode(encoded).decode("utf-8"))
    except (TypeError, ValueError, json.JSONDecodeError):
        logger.exception("Ignoring malformed budget notification")
        return {}


def _stop_vm(project: str, zone: str, instance: str) -> None:
    from google.cloud import compute_v1

    client = compute_v1.InstancesClient()
    current = client.get(project=project, zone=zone, instance=instance)
    if current.status in {"STOPPED", "STOPPING", "TERMINATED"}:
        logger.info("VM %s is already %s", instance, current.status)
        return
    client.stop(project=project, zone=zone, instance=instance)
    logger.warning("Budget guard stopped VM %s in %s", instance, zone)


@functions_framework.cloud_event
def enforce_budget(cloud_event) -> None:
    payload = _payload(cloud_event)
    cost = float(payload.get("costAmount") or 0)
    budget = float(payload.get("budgetAmount") or 0)
    project = os.environ["TARGET_PROJECT"]
    zone = os.environ["TARGET_ZONE"]
    instance = os.environ["TARGET_INSTANCE"]
    stop_fraction = float(os.getenv("STOP_AT_FRACTION", "0.90"))

    if budget <= 0:
        logger.warning("Ignoring budget update without a positive budget amount")
        return
    spent_fraction = cost / budget
    logger.info("Budget update received: cost=%s budget=%s fraction=%s", cost, budget, spent_fraction)
    if spent_fraction >= stop_fraction:
        _stop_vm(project, zone, instance)
