# Agent (Person 3)

The run loop, the seven tools, the scripted agent, the Deep Agents planner and the verifier.

| File | What it does |
|---|---|
| `run.py` | Starts, cancels and resets runs; sets the run mode; writes `status.json`; feeds live failures into the health registry |
| `tools.py` | The seven tools (thin wrappers over the owners' functions) |
| `providers.py` | Plain import list of the owners' canonical functions; no fallbacks |
| `scripted.py` | Fixed-order agent, no model calls |
| `deep.py` | Deep Agents planner, planner-call logging, `ping` |
| `subagents.py`, `prompts.py` | Subagent definitions and prompts |
| `verify.py` | Ten consistency checks run by the verifier |

## Installed versions (pinned in `backend/requirements.txt`)

Tested together on Windows with Python 3.14.7:

```
deepagents==0.7.38
langchain==1.5.0
langchain-core==1.8.0
langgraph==1.2.22
langchain-aws==1.9.3
boto3==1.44.3
botocore==1.44.3
```

## The exact `create_deep_agent` call (deepagents 0.7.38)

```python
from deepagents import FilesystemPermission, create_deep_agent
from deepagents.backends import FilesystemBackend

create_deep_agent(
    model=model,                      # ChatBedrockConverse(temperature=0) or ChatOpenAI for openrouter/ ids
    tools=[],                         # the planner only delegates
    system_prompt=PLANNER_PROMPT,     # 0.7.x name (not "instructions")
    subagents=[{"name": ..., "description": ..., "system_prompt": ..., "tools": [StructuredTool, ...]}],
    backend=FilesystemBackend(root_dir=audits/<sid>, virtual_mode=True),
    permissions=[
        FilesystemPermission(operations=["write"], paths=["/agent/**"], mode="allow"),
        FilesystemPermission(operations=["write"], paths=["/**"], mode="deny"),
    ],
    name="planner",
)
```

Subagent dicts take tool objects (not names). The four subagents are `exterior_analyst`, `walker`,
`retrofit_planner` and `verifier`. The planner's files are real files under `audits/<sid>/agent/`
(todo list in `agent/todo.md`, report draft in `agent/report.md`); writes anywhere else are refused.
The `todo` event carries the todo items in `data.todo`.

## Planner model

`WATTWALK_PLANNER_MODEL_ID` in `.env`:

- a Bedrock model id that supports tool use through Converse (needs AWS credentials and model access in
  `AWS_REGION`), or
- `openrouter/<model>` for a free OpenRouter model (needs `OPENROUTER_API_KEY` and `pip install langchain-openai`).
  Pick one that supports tool calling, for example `openrouter/thinkingmachines/inkling-2-small:free`.

Check the model before a run:

```bash
cd backend
python -m wattwalk.agent.deep ping
```

It makes one call with a trivial tool bound and prints `OK: tool call returned`, or why it failed.

## Planner call logging

`PlannerCallLogger` (a LangChain callback) appends one `ModelCall` per chat-model call: `kind` and
`model_tier` are `planner`, `image_px` is null, tokens come from the response's usage metadata when the
provider reports them, and `agent` is the subagent that made the call (from LangChain's `lc_agent_name`
metadata) or `planner`. `model_call_summary.calls_planner` is therefore non-zero in Deep Agents runs.

## Failures

If the planner model fails mid-run (after the model client's own retries), the run fails with the error;
it never switches to scripted mode inside a run. The user can start a new run in scripted mode
(`WATTWALK_AGENT_MODE=scripted`).

## Tests

- `backend/tests/agent/test_agent.py::test_deep_agents_delegates_to_all_subagents` and
  `test_deep_agents.py` offline tests: always run, using a scripted fake chat model.
- `test_deep_agents.py::test_deep_agents_live_fixture`: runs only with a planner model id and credentials;
  otherwise it is skipped with the reason.
