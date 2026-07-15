import json
import logging
import os

from google.cloud import compute_v1
from google.cloud import pubsub_v1


PROJECT_ID = os.environ["TARGET_PROJECT_ID"]
SUBSCRIPTION_PROJECT_ID = os.environ["SUBSCRIPTION_PROJECT_ID"]
SUBSCRIPTION_ID = os.environ["SUBSCRIPTION_ID"]
STOP_AT_FRACTION = float(os.getenv("STOP_AT_FRACTION", "0.90"))
VM_LABEL_KEY = os.getenv("VM_LABEL_KEY", "app")
VM_LABEL_VALUE = os.getenv("VM_LABEL_VALUE", "eventhorizon")


def _spend_fraction(payload: dict) -> float:
    budget_amount = float(payload.get("budgetAmount") or 0)
    cost_amount = float(payload.get("costAmount") or 0)
    actual_fraction = cost_amount / budget_amount if budget_amount > 0 else 0
    threshold_fraction = float(payload.get("alertThresholdExceeded") or 0)
    return max(actual_fraction, threshold_fraction)


def _stop_eventhorizon_vms() -> list[str]:
    instances = compute_v1.InstancesClient()
    stopped = []

    for zone_scope, scoped_list in instances.aggregated_list(project=PROJECT_ID):
        for instance in scoped_list.instances or []:
            if instance.labels.get(VM_LABEL_KEY) != VM_LABEL_VALUE:
                continue
            if instance.status in {"STOPPED", "STOPPING", "TERMINATED"}:
                continue

            zone = instance.zone.rsplit("/", 1)[-1]
            instances.stop(project=PROJECT_ID, zone=zone, instance=instance.name)
            stopped.append(f"{zone}/{instance.name}")

    return stopped


def poll_budget(_request):
    subscriber = pubsub_v1.SubscriberClient()
    subscription = subscriber.subscription_path(
        SUBSCRIPTION_PROJECT_ID,
        SUBSCRIPTION_ID,
    )
    response = subscriber.pull(
        request={"subscription": subscription, "max_messages": 20},
        timeout=15,
    )

    ack_ids = []
    highest_fraction = 0.0
    stopped = []

    for received in response.received_messages:
        ack_ids.append(received.ack_id)
        try:
            payload = json.loads(received.message.data.decode("utf-8"))
            highest_fraction = max(highest_fraction, _spend_fraction(payload))
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
            logging.exception("Discarding malformed budget notification")

    if highest_fraction >= STOP_AT_FRACTION:
        stopped = _stop_eventhorizon_vms()
        logging.critical(
            "Budget guard triggered at %.2f%%; stop requested for %s",
            highest_fraction * 100,
            stopped,
        )

    if ack_ids:
        subscriber.acknowledge(
            request={"subscription": subscription, "ack_ids": ack_ids}
        )

    return {
        "messages": len(response.received_messages),
        "highest_fraction": highest_fraction,
        "stopped": stopped,
    }, 200
