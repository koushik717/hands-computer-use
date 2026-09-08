from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict

from hands.record.golden import lookup_regular_share
from hands.replay.engine import replay
from hands.schema.artifact import Capability
from hands.schema.policy import load_policy


class InvokeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    member_id: str
    target: str | None = None


def create_catalog_app(default_target: str) -> FastAPI:
    app = FastAPI(title="Hands capability catalog")
    policy = load_policy()
    store: dict[str, Capability] = {}
    cap = lookup_regular_share(default_target, policy)
    store[cap.name] = cap

    @app.get("/v1/capabilities")
    def list_caps():
        return [
            {
                "name": c.name,
                "description": c.description,
                "parameters": [p.model_dump() for p in c.parameters],
                "outputs": [{"name": o.name, "type": o.type} for o in c.outputs],
                "approval": c.approval,
            }
            for c in store.values()
        ]

    @app.post("/v1/capabilities/{name}/invoke")
    async def invoke(name: str, body: InvokeBody):
        cap = store.get(name)
        if cap is None:
            raise HTTPException(404, "unknown capability")
        result = await replay(
            cap,
            {"member_id": body.member_id},
            start_url=body.target or cap.entry.url or default_target,
        )
        return result.model_dump()

    return app
