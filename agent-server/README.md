# EventHorizon Agent Server

LangGraph-based agent runtime for the general EventHorizon workspace.

This is the active AI runtime. It serves transform chat, dashboard chat, report generation, model runtime configuration, and folder-scoped data-tool access. The server keeps the frontend-facing SSE event contract domain-neutral and avoids process-mining assumptions such as variants, PQL, BPMN, `case_id`, `activity`, `timestamp`, or `transform_data_<folder_id>`.

## Run

```powershell
cd C:\Users\kixlo\Desktop\EventHorizon\agent-server
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8010 --reload
```

Set the frontend to use it:

```text
VITE_AGENT_URL=http://127.0.0.1:8010
```

If `VITE_AGENT_URL` is absent, the frontend uses `http://127.0.0.1:8010` by default.

## Routes

- `GET /health`
- `GET /health/live`
- `GET /agent/model-config`
- `PUT /agent/model-config`
- `GET /agent/folder-status/{folder_id}`
- `POST /agent/dashboard/activate`
- `GET /agent/dashboard/exist/{session_id}`
- `POST /agent/chat/stream`
- `POST /agent/dashboard/stream`
- `POST /report/chat/stream?folder_id=...`
- `GET /reports/download/{folder_id}/{report_id}/{format}`

## SSE Events

The server emits normalized events that the current frontend understands:

- `stream_start`
- `agent_start`
- `status`
- `function_request`
- `function_response`
- `agent_thinking`
- `final_response`
- `completion`
- `error`
