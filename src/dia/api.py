"""HTTP API for the intake desk."""

from __future__ import annotations

import json

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from dia.delivery.service import Desk

MAX_UPLOAD = 25 * 1024 * 1024


def create_app(desk: Desk | None = None) -> FastAPI:
    app = FastAPI(title="drawing-intake-agents")
    state = {"desk": desk}

    def get() -> Desk:
        if state["desk"] is None:
            state["desk"] = Desk()
        return state["desk"]

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.post("/api/drawings")
    async def submit(
        file: UploadFile = File(...), customer: str | None = Form(None), previous: str | None = Form(None)
    ):
        data = await file.read()
        if not data or len(data) > MAX_UPLOAD:
            raise HTTPException(413 if data else 400, "empty file or larger than 25 MB")
        try:
            job = get().submit(data, file.filename or "upload", customer, previous)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        return job.summary()

    @app.get("/api/drawings/{job_id}")
    def show(job_id: str):
        job = get().jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "no such drawing")
        return job.summary()

    @app.post("/api/drawings/{job_id}/approve")
    def approve(job_id: str, values: dict[str, str]):
        if job_id not in get().jobs:
            raise HTTPException(404, "no such drawing")
        try:
            return get().approve(job_id, values).summary()
        except KeyError as e:
            raise HTTPException(422, str(e)) from e

    @app.post("/api/drawings/{job_id}/export")
    def export(job_id: str):
        if job_id not in get().jobs:
            raise HTTPException(404, "no such drawing")
        return get().export(job_id)

    @app.post("/api/customers/{customer}/onboard")
    async def onboard(customer: str, files: list[UploadFile] = File(...), values: str = Form(...)):
        known = json.loads(values)
        if len(known) != len(files):
            raise HTTPException(422, "one set of values per file")
        examples = [(await f.read(), f.filename or "x", t) for f, t in zip(files, known, strict=True)]
        prof = get().onboard(customer, examples)
        return {"customer": customer, "labels": prof.labels}

    return app


app = create_app()
