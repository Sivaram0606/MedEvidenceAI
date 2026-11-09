"""
FastAPI Backend for the Point-of-Care Literature Synthesis & FHIR Clinical Decision Support System.
Serves the Physician Web UI and provides REST endpoints for FHIR R4 ingestion,
Reputed Medical Journal verification, and 4-Agent Clinical Synthesis.
"""

from pathlib import Path
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.sample_fhir_bundles import SAMPLE_FHIR_CASES
from backend.fhir_parser import parse_fhir_bundle, fetch_external_fhir_bundle
from backend.pubmed_journal_tool import REPUTED_MEDICAL_JOURNALS
from backend.agent_orchestrator import run_point_of_care_agent_pipeline

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="MedEvidence AI • Point-of-Care FHIR & Reputed Journal Agentic System",
    version="1.0.0",
    description="Multi-Agent Clinical Decision Support & Literature Synthesis strictly grounded in HL7 FHIR R4 patient data and high-impact peer-reviewed medical journals.",
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


class SynthesizeRequest(BaseModel):
    case_id: Optional[str] = None
    fhir_bundle: Optional[Dict[str, Any]] = None
    physician_question: str


@app.get("/api/health")
async def health_check() -> Dict[str, Any]:
    return {
        "status": "healthy",
        "service": "MedEvidence Point-of-Care Agentic System",
        "whitelisted_journals": len(REPUTED_MEDICAL_JOURNALS),
        "sample_cases": len(SAMPLE_FHIR_CASES),
    }


@app.get("/api/journals")
async def list_whitelisted_journals() -> Dict[str, Any]:
    return {
        "count": len(REPUTED_MEDICAL_JOURNALS),
        "journals": REPUTED_MEDICAL_JOURNALS,
    }


@app.get("/api/cases")
async def list_sample_cases() -> Dict[str, Any]:
    cases_out = []
    for cid, cdata in SAMPLE_FHIR_CASES.items():
        parsed = parse_fhir_bundle(cdata["fhir_bundle"])
        cases_out.append({
            "case_id": cid,
            "title": cdata["title"],
            "specialty": cdata["specialty"],
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

    if not req.physician_question.strip():
        raise HTTPException(status_code=400, detail="Physician clinical question cannot be empty.")

    result = await run_point_of_care_agent_pipeline(
        fhir_bundle=bundle,
        physician_question=req.physician_question.strip(),
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

