# MedEvidenceAI • Assistive Clinical Research & Literature Copilot

A physician-led, non-prescriptive **Assistive Clinical Research & Literature Synthesis** system powered by **Gemini Flash 3.8 (`gemini-3.8-flash`)**. It extracts clinical context from **HL7 FHIR R4 Bundles** and queries **4 live open-source biomedical research APIs**—strictly filtered to **22 high-impact, peer-reviewed medical journals**—to present trial outcomes, cohort parallels, and subgroup analyses for independent physician evaluation.

---

## Inquiry Modes & Customizable Journal Whitelist
Inside the Point-of-Care Workstation, physicians can switch between two **Radio Button** query modes:
1. **With FHIR Context (`POST /api/synthesize`):** Select an HL7 FHIR R4 patient cohort (or import/fetch an external FHIR R4 Bundle/URL). `MedEvidenceAI` automatically generates a patient-specific clinical literature query from the patient's demographics, SNOMED/ICD-10 conditions, abnormal LOINC labs/vitals, medications, and allergies, then synthesizes matching trial outcomes.
2. **Direct Query Without FHIR Context (`POST /api/general-question` / `POST /api/condition-research`):** Enter any **plain query** on a medical condition or clinical topic (e.g., *Acute ischemic stroke*, *research articles on HFpEF*, or *guidelines for infective endocarditis*) to independently retrieve and synthesize peer-reviewed research articles and registered ClinicalTrials.gov (`NCT...`) trials without FHIR context.
3. **Customizable Reputed Journals (`GET/POST/DELETE /api/journals`):** View, add, remove, or reset the active peer-reviewed medical journals from the header Journals modal anytime.

---

## Core Governance & Assistive Role
* **Physician-in-the-Loop Authority:** Does **not** issue medical orders, prescriptions, or autonomous directives.
* **Evidence & Cohort Synthesis:** Presents published hazard ratios, confidence intervals, inclusion/exclusion criteria, pharmacokinetic parameters, and diagnostic evaluation frameworks from peer-reviewed literature.

---

## Live Open-Source Biomedical Research APIs Integrated
1. **NCBI PubMed Entrez E-Utilities API** (`eutils.ncbi.nlm.nih.gov`) — Live search & XML abstract retrieval restricted via `[Journal]` filter to 22 whitelisted medical journals (*NEJM*, *The Lancet*, *JAMA*, *BMJ*, *Annals of Internal Medicine*, *Circulation*, *JACC*, *European Heart Journal*, *AJRCCM*, *Intensive Care Medicine*, *Kidney International*, etc.).
2. **Europe PMC Open Research REST API** (`www.ebi.ac.uk/europepmc/webservices/rest/search`) — Open-access full-text biomedical literature and citation metrics (`citedByCount`).
3. **OpenAlex Scholarly Research API** (`api.openalex.org/works`) — Global scholarly research index providing citation impact metrics and open-access links.
4. **NIH ClinicalTrials.gov REST API v2** (`clinicaltrials.gov/api/v2/studies`) — Live registry of active, recruiting, and completed interventional clinical trials (`NCT...`) matching the patient's FHIR conditions.

---

## How to Run

```bash
git clone https://github.com/Sivaram0606/MedEvidenceAI.git
cd MedEvidenceAI
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Open **`http://127.0.0.1:8000/`** in your browser.
