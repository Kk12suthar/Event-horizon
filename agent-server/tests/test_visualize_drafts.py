from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

AGENT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = AGENT_ROOT.parent
sys.path.insert(0, str(AGENT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

from tools import visualize_tools


SELECTED = {
    "id": "prepared-table-id",
    "name": "prepared_sales",
    "revision": 3,
}
SNAPSHOT = {"charts": []}
SCHEMA = {
    "columns": [
        {"name": "region", "type": "text"},
        {"name": "revenue", "type": "numeric"},
    ]
}


class VisualizeDraftTests(unittest.TestCase):
    @patch.object(visualize_tools, "upsert_artifact", side_effect=AssertionError("draft must not persist"))
    @patch.object(visualize_tools, "aggregate")
    @patch.object(visualize_tools, "_selected", return_value=(SELECTED, SNAPSHOT))
    def test_create_chart_returns_transient_artifact(self, _selected, aggregate, _upsert) -> None:
        aggregate.return_value = {"rows": [{"label": "North", "value": 42}]}

        result = visualize_tools.create_chart(
            folder_id="folder-id",
            user_id="user-id",
            session_id="session-id",
            chart_type="bar",
            x_field="region",
            y_field="revenue",
            aggregation="sum",
        )

        self.assertFalse(result["persisted"])
        self.assertEqual(result["artifact"]["status"], "draft")
        self.assertEqual(result["artifact"]["sourceTableId"], SELECTED["id"])
        self.assertEqual(result["artifact"]["transformRevision"], 3)
        self.assertEqual(result["artifact"]["data"], [{"label": "North", "value": 42.0}])

    @patch.object(visualize_tools, "upsert_artifact", side_effect=AssertionError("draft must not persist"))
    @patch.object(visualize_tools, "execute_select")
    @patch.object(visualize_tools, "_schema", return_value=SCHEMA)
    @patch.object(visualize_tools, "_selected", return_value=(SELECTED, SNAPSHOT))
    def test_create_kpi_returns_transient_artifact(self, _selected, _schema, execute_select, _upsert) -> None:
        execute_select.return_value = {"rows": [{"value": 1200}]}

        result = visualize_tools.create_kpi(
            folder_id="folder-id",
            user_id="user-id",
            session_id="session-id",
            title="Total revenue",
            value_field="revenue",
            aggregation="sum",
        )

        self.assertFalse(result["persisted"])
        self.assertEqual(result["artifact"]["type"], "kpi")
        self.assertEqual(result["artifact"]["status"], "draft")
        self.assertEqual(result["artifact"]["data"][0]["value"], 1200.0)


if __name__ == "__main__":
    unittest.main()
