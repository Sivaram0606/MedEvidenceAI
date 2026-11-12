"""
FastAPI Backend for the Point-of-Care Literature Synthesis & FHIR Clinical Decision Support System.
Serves the Physician Web UI and provides REST endpoints for FHIR R4 ingestion,
Reputed Medical Journal verification, and 4-Agent Clinical Synthesis.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.sample_fhir_bundles import SAMPLE_FHIR_CASES
from backend.fhir_parser import parse_fhir_bundle, fetch_external_fhir_bundle
from backend.pubmed_journal_tool import (
    DEFAULT_MEDICAL_JOURNALS,
    SUGGESTED_EXTRA_JOURNALS,
    get_active_journals,
    add_journal,
    remove_journal,
    reset_journals,
)
from backend.agent_orchestrator import (
    run_point_of_care_agent_pipeline,
    run_general_question_pipeline,
    run_condition_research_pipeline,
)

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="MedEvidenceAI • Point-of-Care FHIR & Reputed Journal Agentic System",
    version="1.3.0",
    description="Multi-Agent Assistive Clinical Literature Synthesis supporting HL7 FHIR R4 auto-generated patient queries, standalone general clinical questions, and physician-customizable medical journal coverage.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ParseFhirRequest(BaseModel):
    fhir_bundle: Optional[Dict[str, Any]] = None
    fhir_url: Optional[str] = None


class AddJournalRequest(BaseModel):
    name: str
    abbrev: Optional[str] = None
    short: Optional[str] = None
    category: Optional[str] = None


class SynthesizeRequest(BaseModel):
    case_id: Optional[str] = None
    fhir_bundle: Optional[Dict[str, Any]] = None
    physician_question: Optional[str] = ""
    selected_journals: Optional[List[Dict[str, Any]]] = None


class GeneralQuestionRequest(BaseModel):
    physician_question: str
    selected_journals: Optional[List[Dict[str, Any]]] = None


class ConditionResearchRequest(BaseModel):
    condition: str
    physician_question: Optional[str] = ""
    pub_type_filter: Optional[str] = "all"
    selected_journals: Optional[List[Dict[str, Any]]] = None


def _build_journals_payload(extra_fields: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    active = get_active_journals()
    active_ids = {j["id"] for j in active}
    available_suggestions = [s for s in SUGGESTED_EXTRA_JOURNALS if s["id"] not in active_ids]
    removed_defaults = [d for d in DEFAULT_MEDICAL_JOURNALS if d["id"] not in active_ids]
    payload: Dict[str, Any] = {
        "count": len(active),
        "default_count": len(DEFAULT_MEDICAL_JOURNALS),
        "journals": active,
        "suggested_journals": removed_defaults + available_suggestions,
    }
    if extra_fields:
        payload.update(extra_fields)
    return payload


@app.get("/api/health")
async def health_check() -> Dict[str, Any]:
    return {
        "status": "healthy",
        "service": "MedEvidenceAI Point-of-Care Agentic System",
        "whitelisted_journals": len(get_active_journals()),
        "sample_cases": len(SAMPLE_FHIR_CASES),
        "workflows": ["fhir_patient", "condition_research", "general_question"],
    }


@app.get("/api/journals")
async def list_whitelisted_journals() -> Dict[str, Any]:
    return _build_journals_payload()


@app.post("/api/journals")
async def add_whitelisted_journal(req: AddJournalRequest) -> Dict[str, Any]:
    if not req.name or not req.name.strip():
        raise HTTPException(status_code=400, detail="Journal name cannot be empty.")
    try:
        outcome = add_journal(
            name=req.name,
            abbrev=req.abbrev,
            short=req.short,
            category=req.category,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _build_journals_payload({
        "added_journal": outcome["journal"],
        "already_exists": outcome["already_exists"],
    })


@app.delete("/api/journals/{journal_id}")
async def delete_whitelisted_journal(journal_id: str) -> Dict[str, Any]:
    remove_journal(journal_id)
    return _build_journals_payload({"removed_id": journal_id})


@app.post("/api/journals/reset")
async def reset_whitelisted_journals() -> Dict[str, Any]:
    reset_journals()
    return _build_journals_payload({"reset": True})


@app.get("/api/cases")
async def list_sample_cases() -> Dict[str, Any]:
    cases_out = []
    for cid, cdata in SAMPLE_FHIR_CASES.items():
        parsed = parse_fhir_bundle(cdata["fhir_bundle"])
        cases_out.append({
            "case_id": cid,
            "title": cdata["title"],
            "specialty": cdata["specialty"],
            "auto_generated_query": parsed["auto_generated_query"],
            "default_question": cdata["default_question"],
            "suggested_questions": cdata["suggested_questions"],
            "fhir_bundle": cdata["fhir_bundle"],
            "parsed_fhir": parsed,
        })
    return {"cases": cases_out}


@app.post("/api/parse-fhir")
async def parse_custom_fhir(req: ParseFhirRequest) -> Dict[str, Any]:
    bundle = req.fhir_bundle
    if req.fhir_url:
        try:
            bundle = await fetch_external_fhir_bundle(req.fhir_url)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to fetch FHIR R4 resource from URL '{req.fhir_url}': {exc}",
            )
    if not bundle or not isinstance(bundle, dict):
        raise HTTPException(status_code=400, detail="Valid HL7 FHIR R4 JSON Bundle or Patient resource is required.")

    parsed = parse_fhir_bundle(bundle)
    return {
        "status": "success",
        "fhir_bundle": bundle,
        "parsed_fhir": parsed,
        "auto_generated_query": parsed["auto_generated_query"],
        "suggested_questions": parsed["auto_suggested_questions"],
    }


@app.post("/api/synthesize")
async def run_synthesis(req: SynthesizeRequest) -> Dict[str, Any]:
    bundle = req.fhir_bundle
    if not bundle and req.case_id:
        case_obj = SAMPLE_FHIR_CASES.get(req.case_id)
        if not case_obj:
            raise HTTPException(status_code=404, detail=f"Sample case '{req.case_id}' not found.")
        bundle = case_obj["fhir_bundle"]

    if not bundle:
        raise HTTPException(status_code=400, detail="Either case_id or fhir_bundle must be provided.")

    question_text = (req.physician_question or "").strip()
    if not question_text:
        parsed_preview = parse_fhir_bundle(bundle)
        question_text = parsed_preview["auto_generated_query"]

    result = await run_point_of_care_agent_pipeline(
        fhir_bundle=bundle,
        physician_question=question_text,
        selected_journals=req.selected_journals,
    )
    return result


@app.post("/api/general-question")
async def run_general_question(req: GeneralQuestionRequest) -> Dict[str, Any]:
    if not req.physician_question or not req.physician_question.strip():
        raise HTTPException(status_code=400, detail="General clinical question cannot be empty.")

    result = await run_general_question_pipeline(
        physician_question=req.physician_question.strip(),
        selected_journals=req.selected_journals,
    )
    return result


@app.post("/api/condition-research")
async def run_condition_research(req: ConditionResearchRequest) -> Dict[str, Any]:
    if not req.condition or not req.condition.strip():
        raise HTTPException(status_code=400, detail="Clinical condition or research topic cannot be empty.")

    result = await run_condition_research_pipeline(
        condition=req.condition.strip(),
        physician_question=(req.physician_question or "").strip(),
        pub_type_filter=(req.pub_type_filter or "all").strip(),
        selected_journals=req.selected_journals,
    )
    return result


from fastapi.responses import RedirectResponse, Response

MEDICAL_FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    '<rect width="32" height="32" rx="8" fill="#0d9488"/>'
    '<path d="M16 7v18M7 16h18" stroke="#ffffff" stroke-width="3.5" stroke-linecap="round"/>'
    '</svg>'
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/favicon.ico", include_in_schema=False)
@app.get("/dev-ui/adk_favicon.svg", include_in_schema=False)
async def serve_favicon() -> Response:
    return Response(content=MEDICAL_FAVICON_SVG, media_type="image/svg+xml")


@app.get("/dev-ui", include_in_schema=False)
@app.get("/dev-ui/", include_in_schema=False)
async def redirect_dev_ui() -> RedirectResponse:
    return RedirectResponse(url="/")


@app.get("/")
async def serve_index() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "index.html"))

