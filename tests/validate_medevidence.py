"""
Validation Suite for MedEvidenceAI.

Usage:
  # Fast offline unit, schema & REST contract checks (<1s):
  .venv/bin/python tests/validate_medevidence.py

  # Full end-to-end validation including live PubMed/EuropePMC/OpenAlex/CT.gov + Gemini calls:
  .venv/bin/python tests/validate_medevidence.py --live
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Callable, List, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient

from backend.agent_orchestrator import (
    ClinicalSynthesisOutput,
    _build_curated_clinical_synthesis,
    _build_dynamic_literature_fallback,
    _build_general_question_queries,
    _extract_biomedical_search_terms,
    _generate_pico_queries,
    _infer_pub_type_from_plain_query,
)
from backend.fhir_parser import parse_fhir_bundle
from backend.main import app
from backend.pubmed_journal_tool import (
    VERIFIED_LANDMARK_LITERATURE,
    _match_journal_metadata,
    _parse_pubmed_xml,
    build_pubmed_journal_filter_clause,
    get_active_journals,
    reset_journals,
)
from backend.sample_fhir_bundles import SAMPLE_FHIR_CASES


SAMPLE_PUBMED_XML = """<?xml version="1.0" ?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>31535829</PMID>
      <Article>
        <Journal>
          <Title>The New England Journal of Medicine</Title>
          <ISOAbbreviation>N Engl J Med</ISOAbbreviation>
          <JournalIssue><PubDate><Year>2019</Year></PubDate></JournalIssue>
        </Journal>
        <ArticleTitle>Dapagliflozin in Patients with Heart Failure (DAPA-HF).</ArticleTitle>
        <Abstract><AbstractText Label="RESULTS">HR 0.74 (P&lt;0.001).</AbstractText></Abstract>
        <AuthorList><Author><LastName>McMurray</LastName><Initials>JJV</Initials></Author></AuthorList>
        <PublicationTypeList><PublicationType>Randomized Controlled Trial</PublicationType></PublicationTypeList>
      </Article>
      <MedlineJournalInfo><MedlineTA>N Engl J Med</MedlineTA></MedlineJournalInfo>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList><ArticleId IdType="doi">10.1056/NEJMoa1911303</ArticleId></ArticleIdList>
    </PubmedData>
  </PubmedArticle>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>99999999</PMID>
      <Article>
        <Journal>
          <Title>Unverified Predatory Medical Weekly</Title>
          <JournalIssue><PubDate><Year>2025</Year></PubDate></JournalIssue>
        </Journal>
        <ArticleTitle>Should Be Blocked By Journal Whitelist.</ArticleTitle>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>
"""


def run_checks(include_live: bool = False) -> int:
    client = TestClient(app)
    results: List[Tuple[str, str, str]] = []

    def check(name: str, fn: Callable[[], str]) -> None:
        t0 = time.perf_counter()
        try:
            detail = fn()
            ms = (time.perf_counter() - t0) * 1000
            results.append(("PASS", name, f"{detail} ({ms:.1f} ms)"))
        except Exception as exc:
            ms = (time.perf_counter() - t0) * 1000
            results.append(("FAIL", name, f"{type(exc).__name__}: {exc} ({ms:.1f} ms)"))

    # 1. Agent 1A: FHIR Parser & Safety Alerts
    def test_fhir_parser_all_cases() -> str:
        assert len(SAMPLE_FHIR_CASES) == 4, "Expected 4 sample FHIR cases"
        total_alerts = 0
        for cid, case in SAMPLE_FHIR_CASES.items():
            parsed = parse_fhir_bundle(case["fhir_bundle"])
            assert parsed["patient"]["name"] != "Unknown Patient", f"Missing patient name in {cid}"
            assert parsed["resource_counts"]["conditions"] >= 1, f"No conditions in {cid}"
            assert parsed["auto_generated_query"], f"Empty auto query in {cid}"
            assert len(parsed["auto_suggested_questions"]) >= 2, f"Missing suggested chips in {cid}"
            total_alerts += len(parsed["safety_alerts"])
        return f"4/4 FHIR bundles parsed, {total_alerts} total subgroup safety alerts derived"

    check("Agent 1A • parse_fhir_bundle() on all 4 cohorts", test_fhir_parser_all_cases)

    def test_single_patient_fhir() -> str:
        single_pat = {
            "resourceType": "Patient",
            "id": "pat-demo",
            "name": [{"given": ["Jane"], "family": "Doe"}],
            "gender": "female",
            "birthDate": "1980-05-15",
        }
        parsed = parse_fhir_bundle(single_pat)
        assert parsed["patient"]["name"] == "Jane Doe"
        assert parsed["patient"]["gender"] == "Female"
        return f"Parsed standalone Patient '{parsed['patient']['name']}' (age {parsed['patient']['age']})"

    check("Agent 1A • Standalone FHIR Patient resource fallback", test_single_patient_fhir)

    # 2. Agent 1B: Query Formulation & Intent Inference
    def test_query_formulation() -> str:
        terms = _extract_biomedical_search_terms("Research articles on acute pericarditis management")
        assert terms == ["acute", "pericarditis"], f"Unexpected terms: {terms}"
        assert _infer_pub_type_from_plain_query("RCTs on SGLT2 inhibitors") == "rct"
        assert _infer_pub_type_from_plain_query("Clinical guidelines for sepsis") == "guideline"
        assert _infer_pub_type_from_plain_query("Meta-analysis of DOAC bleeding") == "review"
        queries, ct_kw, _, pub_t = _build_general_question_queries(
            "Tenecteplase vs alteplase in acute ischemic stroke RCTs"
        )
        assert any("Tenecteplase OR alteplase" in q for q in queries), f"Comparator missing: {queries}"
        assert pub_t == "rct"
        parsed_hf = parse_fhir_bundle(SAMPLE_FHIR_CASES["patient-cardio-ckd"]["fhir_bundle"])
        pico_q, _ = _generate_pico_queries(parsed_hf, parsed_hf["auto_generated_query"])
        assert len(pico_q) == 3
        return f"Stopwords stripped, comparator clause built ({queries[0]}), 3 PICO queries generated"

    check("Agent 1B • Biomedical term extraction, comparators & PICO builder", test_query_formulation)

    # 3. Agent 2: Journal Whitelist Gatekeeper & XML Parser
    def test_journal_whitelist_and_xml() -> str:
        reset_journals()
        active = get_active_journals()
        assert len(active) == 22
        clause = build_pubmed_journal_filter_clause(active)
        assert '"N Engl J Med"[Journal]' in clause
        assert _match_journal_metadata("N Engl J Med") is not None
        assert _match_journal_metadata("Predatory Open Journal") is None
        parsed_xml = _parse_pubmed_xml(SAMPLE_PUBMED_XML, active)
        assert len(parsed_xml) == 1 and parsed_xml[0]["pmid"] == "31535829"
        return "22 journals active; PubMed XML parser accepted NEJM & blocked unwhitelisted journal"

    check("Agent 2  • Journal whitelist gatekeeper & PubMed XML parser", test_journal_whitelist_and_xml)

    # 4. Agents 3 & 4: Deterministic Fallback & Pydantic Schema Validation
    def test_synthesis_schemas() -> str:
        for cid, case in SAMPLE_FHIR_CASES.items():
            parsed = parse_fhir_bundle(case["fhir_bundle"])
            curated = _build_curated_clinical_synthesis(
                parsed_fhir=parsed,
                physician_question=case["default_question"],
                articles=VERIFIED_LANDMARK_LITERATURE[:4],
            )
            validated = ClinicalSynthesisOutput.model_validate(curated)
            assert len(validated.key_clinical_takeaways) >= 3, f"Missing takeaways for {cid}"
        dyn = _build_dynamic_literature_fallback(
            subject_label="Heart Failure",
            articles=[
                {
                    **VERIFIED_LANDMARK_LITERATURE[0],
                    "pubmed_url": "https://pubmed.ncbi.nlm.nih.gov/31535829/",
                    "doi_url": "https://doi.org/10.1056/NEJMoa1911303",
                }
            ],
            clinical_trials=[],
        )
        ClinicalSynthesisOutput.model_validate(dyn)
        return "All 4 curated case syntheses + dynamic fallback conform to ClinicalSynthesisOutput"

    check("Agent 3/4 • ClinicalSynthesisOutput Pydantic schema validation", test_synthesis_schemas)

    # 5. FastAPI REST Contract Checks
    def test_rest_endpoints() -> str:
        assert client.get("/").status_code == 200
        h = client.get("/api/health").json()
        assert h["status"] == "healthy" and h["whitelisted_journals"] == 22

        add_r = client.post("/api/journals", json={"name": "Stroke"})
        assert add_r.status_code == 200 and add_r.json()["count"] == 23
        del_r = client.delete("/api/journals/stroke")
        assert del_r.status_code == 200 and del_r.json()["count"] == 22
        client.post("/api/journals/reset")

        cases_r = client.get("/api/cases")
        assert cases_r.status_code == 200 and len(cases_r.json()["cases"]) == 4

        bad_pf = client.post("/api/parse-fhir", json={})
        assert bad_pf.status_code == 400
        good_pf = client.post(
            "/api/parse-fhir",
            json={"fhir_bundle": SAMPLE_FHIR_CASES["patient-cardio-ckd"]["fhir_bundle"]},
        )
        assert good_pf.status_code == 200
        return "GET /, /api/health, /api/cases, /api/journals CRUD, and /api/parse-fhir verified"

    check("FastAPI  • Core REST endpoints & journal CRUD contracts", test_rest_endpoints)

    # 6. Regression Check: /api/condition-research with physician_question
    def test_condition_research_with_question_bug() -> str:
        resp = client.post(
            "/api/condition-research",
            json={
                "condition": "Lupus Nephritis",
                "physician_question": "belimumab vs voclosporin",
                "selected_journals": [],
            },
        )
        assert resp.status_code == 200, f"HTTP {resp.status_code}"
        return "Condition research with physician_question succeeded"

    check(
        "BugCheck • POST /api/condition-research with physician_question",
        test_condition_research_with_question_bug,
    )

    # 7. Optional Live Multi-API + Gemini Flash 3.8 Checks
    if include_live:
        def test_live_fhir_synthesis() -> str:
            resp = client.post("/api/synthesize", json={"case_id": "patient-cardio-ckd"})
            assert resp.status_code == 200
            body = resp.json()
            ClinicalSynthesisOutput.model_validate(body["synthesis"])
            return (
                f"engine='{body['engine_mode']}', "
                f"articles={len(body['retrieved_articles'])}, "
                f"trials={len(body['clinical_trials'])}"
            )

        check("LIVE E2E • POST /api/synthesize (FHIR Mode)", test_live_fhir_synthesis)

        def test_live_direct_query() -> str:
            resp = client.post(
                "/api/general-question",
                json={"physician_question": "Tenecteplase vs alteplase in acute ischemic stroke"},
            )
            assert resp.status_code == 200
            body = resp.json()
            ClinicalSynthesisOutput.model_validate(body["synthesis"])
            apis = ", ".join(f"{k.split()[0]}={v}" for k, v in body.get("api_status_map", {}).items())
            return f"articles={len(body['retrieved_articles'])}, trials={len(body['clinical_trials'])} [{apis}]"

        check("LIVE E2E • POST /api/general-question (Direct Mode)", test_live_direct_query)

    # Print formatted report
    print("\n" + "=" * 88)
    print(f" MedEvidenceAI Validation Report ({'LIVE + OFFLINE' if include_live else 'FAST OFFLINE MODE'})")
    print("=" * 88)
    failed = 0
    for status, name, detail in results:
        icon = "[PASS]" if status == "PASS" else "[FAIL]"
        if status != "PASS":
            failed += 1
        print(f" {icon} {name}\n        -> {detail}")
    print("=" * 88)
    print(f" Summary: {len(results) - failed}/{len(results)} checks passed, {failed} failed.")
    print("=" * 88 + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate MedEvidenceAI functions and API endpoints.")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Also run live network queries against PubMed, Europe PMC, OpenAlex, ClinicalTrials.gov, and Gemini.",
    )
    args = parser.parse_args()
    sys.exit(run_checks(include_live=args.live))
