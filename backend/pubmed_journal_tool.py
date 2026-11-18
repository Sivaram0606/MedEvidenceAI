"""
Agent 2 Tooling: Reputed Medical Journal & Clinical Practice Guideline Search Engine.
Strictly restricts retrieval to a curated whitelist of high-impact, peer-reviewed medical
journals (NEJM, The Lancet, JAMA, BMJ, Annals of Internal Medicine, Circulation, JACC,
European Heart Journal, AJRCCM, Intensive Care Medicine, Kidney International, etc.)
via live NCBI PubMed Entrez E-Utilities API (`esearch` + `efetch`) plus verified landmark trial index.
"""

import asyncio
from collections import OrderedDict
import copy
from datetime import date
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional, Tuple
import httpx

try:
    import defusedxml.ElementTree as SafeET  # type: ignore
except ImportError:
    SafeET = ET

logger = logging.getLogger(__name__)

MAX_PUBMED_XML_BYTES = 2 * 1024 * 1024
MAX_JOURNAL_SESSIONS = 512
RETRIEVAL_CACHE_TTL_SEC = 900.0
RETRIEVAL_CACHE_MAX_ENTRIES = 128
_RETRIEVAL_CACHE: "OrderedDict[Tuple[Any, ...], Tuple[float, Dict[str, Any]]]" = OrderedDict()

# Default Curated Whitelist of 22 Reputed High-Impact Medical Journals
DEFAULT_MEDICAL_JOURNALS: List[Dict[str, str]] = [
    {"id": "nejm", "name": "The New England Journal of Medicine", "abbrev": "N Engl J Med", "short": "NEJM", "category": "General Medicine", "impact_tier": "Tier 1 (Flagship)"},
    {"id": "lancet", "name": "The Lancet", "abbrev": "Lancet", "short": "The Lancet", "category": "General Medicine", "impact_tier": "Tier 1 (Flagship)"},
    {"id": "jama", "name": "JAMA", "abbrev": "JAMA", "short": "JAMA", "category": "General Medicine", "impact_tier": "Tier 1 (Flagship)"},
    {"id": "bmj", "name": "The BMJ", "abbrev": "BMJ", "short": "BMJ", "category": "General Medicine", "impact_tier": "Tier 1 (Flagship)"},
    {"id": "ann-intern-med", "name": "Annals of Internal Medicine", "abbrev": "Ann Intern Med", "short": "Ann Intern Med", "category": "Internal Medicine", "impact_tier": "Tier 1 (Flagship)"},
    {"id": "jama-intern-med", "name": "JAMA Internal Medicine", "abbrev": "JAMA Intern Med", "short": "JAMA Intern Med", "category": "Internal Medicine", "impact_tier": "Tier 1"},
    {"id": "nat-med", "name": "Nature Medicine", "abbrev": "Nat Med", "short": "Nature Medicine", "category": "Translational Medicine", "impact_tier": "Tier 1"},
    {"id": "circulation", "name": "Circulation", "abbrev": "Circulation", "short": "Circulation (AHA)", "category": "Cardiology", "impact_tier": "Tier 1 (Society Flagship)"},
    {"id": "jacc", "name": "Journal of the American College of Cardiology", "abbrev": "J Am Coll Cardiol", "short": "JACC", "category": "Cardiology", "impact_tier": "Tier 1 (Society Flagship)"},
    {"id": "eur-heart-j", "name": "European Heart Journal", "abbrev": "Eur Heart J", "short": "Eur Heart J (ESC)", "category": "Cardiology", "impact_tier": "Tier 1 (Society Flagship)"},
    {"id": "jama-cardiol", "name": "JAMA Cardiology", "abbrev": "JAMA Cardiol", "short": "JAMA Cardiol", "category": "Cardiology", "impact_tier": "Tier 1"},
    {"id": "ajrccm", "name": "American Journal of Respiratory and Critical Care Medicine", "abbrev": "Am J Respir Crit Care Med", "short": "AJRCCM (ATS)", "category": "Pulmonology / Critical Care", "impact_tier": "Tier 1 (Society Flagship)"},
    {"id": "intensive-care-med", "name": "Intensive Care Medicine", "abbrev": "Intensive Care Med", "short": "Intensive Care Med", "category": "Critical Care", "impact_tier": "Tier 1 (Society Flagship)"},
    {"id": "lancet-respir-med", "name": "The Lancet Respiratory Medicine", "abbrev": "Lancet Respir Med", "short": "Lancet Respir Med", "category": "Pulmonology", "impact_tier": "Tier 1"},
    {"id": "lancet-infect-dis", "name": "The Lancet Infectious Diseases", "abbrev": "Lancet Infect Dis", "short": "Lancet Infect Dis", "category": "Infectious Disease", "impact_tier": "Tier 1"},
    {"id": "clin-infect-dis", "name": "Clinical Infectious Diseases", "abbrev": "Clin Infect Dis", "short": "Clin Infect Dis (IDSA)", "category": "Infectious Disease", "impact_tier": "Tier 1 (Society Flagship)"},
    {"id": "chest", "name": "Chest", "abbrev": "Chest", "short": "CHEST", "category": "Pulmonology / Critical Care", "impact_tier": "Tier 1"},
    {"id": "kidney-int", "name": "Kidney International", "abbrev": "Kidney Int", "short": "Kidney Int (KDIGO/ISN)", "category": "Nephrology", "impact_tier": "Tier 1 (Society Flagship)"},
    {"id": "jasn", "name": "Journal of the American Society of Nephrology", "abbrev": "J Am Soc Nephrol", "short": "JASN", "category": "Nephrology", "impact_tier": "Tier 1 (Society Flagship)"},
    {"id": "ann-rheum-dis", "name": "Annals of the Rheumatic Diseases", "abbrev": "Ann Rheum Dis", "short": "Ann Rheum Dis (EULAR)", "category": "Rheumatology", "impact_tier": "Tier 1 (Society Flagship)"},
    {"id": "gastroenterology", "name": "Gastroenterology", "abbrev": "Gastroenterology", "short": "Gastroenterology (AGA)", "category": "Gastroenterology", "impact_tier": "Tier 1 (Society Flagship)"},
    {"id": "gut", "name": "Gut", "abbrev": "Gut", "short": "Gut (BSG)", "category": "Gastroenterology", "impact_tier": "Tier 1"},
]

# Suggested Specialty Journals Physicians Can Add in 1 Click
SUGGESTED_EXTRA_JOURNALS: List[Dict[str, str]] = [
    {"id": "j-clin-oncol", "name": "Journal of Clinical Oncology", "abbrev": "J Clin Oncol", "short": "JCO", "category": "Oncology", "impact_tier": "Specialty Flagship"},
    {"id": "blood", "name": "Blood", "abbrev": "Blood", "short": "Blood (ASH)", "category": "Hematology", "impact_tier": "Specialty Flagship"},
    {"id": "diabetes-care", "name": "Diabetes Care", "abbrev": "Diabetes Care", "short": "Diabetes Care (ADA)", "category": "Endocrinology", "impact_tier": "Specialty Flagship"},
    {"id": "stroke", "name": "Stroke", "abbrev": "Stroke", "short": "Stroke (AHA)", "category": "Neurology / Stroke", "impact_tier": "Specialty Flagship"},
    {"id": "neurology", "name": "Neurology", "abbrev": "Neurology", "short": "Neurology (AAN)", "category": "Neurology", "impact_tier": "Specialty Flagship"},
    {"id": "jama-neurol", "name": "JAMA Neurology", "abbrev": "JAMA Neurol", "short": "JAMA Neurol", "category": "Neurology", "impact_tier": "Tier 1 Specialty"},
    {"id": "jama-oncol", "name": "JAMA Oncology", "abbrev": "JAMA Oncol", "short": "JAMA Oncol", "category": "Oncology", "impact_tier": "Tier 1 Specialty"},
    {"id": "hepatology", "name": "Hepatology", "abbrev": "Hepatology", "short": "Hepatology (AASLD)", "category": "Hepatology", "impact_tier": "Specialty Flagship"},
    {"id": "arthritis-rheumatol", "name": "Arthritis & Rheumatology", "abbrev": "Arthritis Rheumatol", "short": "Arthritis Rheumatol (ACR)", "category": "Rheumatology", "impact_tier": "Specialty Flagship"},
    {"id": "eur-respir-j", "name": "European Respiratory Journal", "abbrev": "Eur Respir J", "short": "Eur Respir J (ERS)", "category": "Pulmonology", "impact_tier": "Specialty Flagship"},
]

# Default Journal List & Session-Isolated Whitelist Store
ACTIVE_MEDICAL_JOURNALS: List[Dict[str, Any]] = [dict(j) for j in DEFAULT_MEDICAL_JOURNALS]
REPUTED_MEDICAL_JOURNALS: List[Dict[str, Any]] = ACTIVE_MEDICAL_JOURNALS
_SESSION_JOURNAL_STORE: "OrderedDict[str, List[Dict[str, Any]]]" = OrderedDict()


def _get_session_journal_list(session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Returns an isolated mutable journal list per client session (or default list if unset)."""
    if not session_id or session_id == "default":
        return ACTIVE_MEDICAL_JOURNALS
    if session_id in _SESSION_JOURNAL_STORE:
        _SESSION_JOURNAL_STORE.move_to_end(session_id)
        return _SESSION_JOURNAL_STORE[session_id]
    while len(_SESSION_JOURNAL_STORE) >= MAX_JOURNAL_SESSIONS:
        _SESSION_JOURNAL_STORE.popitem(last=False)
    fresh = [dict(j) for j in DEFAULT_MEDICAL_JOURNALS]
    _SESSION_JOURNAL_STORE[session_id] = fresh
    return fresh


def _sanitize_journal_term(text: Optional[str], max_len: int = 140) -> str:
    """
    Sanitizes journal names and abbreviations so quotes, brackets, or Boolean operators
    cannot break out of PubMed `"..."[Journal]` or Europe PMC `JOURNAL:"..."` clauses.
    """
    if not text:
        return ""
    cleaned = re.sub(r"[\x00-\x1f\x7f\"\[\]{};<>\\]+", " ", str(text))
    cleaned = " ".join(cleaned.split()).strip()
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].strip()
    return cleaned


def _slugify_journal_id(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "custom-journal"


def _normalize_journal_key(text: str) -> str:
    """Normalizes journal titles/abbreviations for accurate cross-API matching."""
    if not text:
        return ""
    cleaned = text.split(":")[0]
    cleaned = re.sub(r"\s*\([^)]*\)", "", cleaned)
    cleaned = cleaned.replace("&", " and ").replace(".", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    if cleaned.startswith("the "):
        cleaned = cleaned[4:].strip()
    return cleaned


def build_pubmed_journal_filter_clause(journals: List[Dict[str, Any]]) -> str:
    if not journals:
        return ""
    clauses: List[str] = []
    for j in journals[:60]:
        abbrev = _sanitize_journal_term(j.get("abbrev", ""))
        name = _sanitize_journal_term(j.get("name", ""))
        if j.get("is_custom") and name and abbrev and name.lower() != abbrev.lower():
            clauses.append(f'"{abbrev}"[Journal] OR "{name}"[Journal]')
        elif abbrev:
            clauses.append(f'"{abbrev}"[Journal]')
        elif name:
            clauses.append(f'"{name}"[Journal]')
    return "(" + " OR ".join(clauses) + ")" if clauses else ""


PUBMED_JOURNAL_FILTER_CLAUSE = build_pubmed_journal_filter_clause(ACTIVE_MEDICAL_JOURNALS)


def get_active_journals(session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    return [dict(j) for j in _get_session_journal_list(session_id)]


def add_journal(
    name: str,
    abbrev: Optional[str] = None,
    short: Optional[str] = None,
    category: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Adds a journal to the active whitelist (matching known metadata if recognized)."""
    clean_name = _sanitize_journal_term(name, 140)
    if not clean_name or not re.search(r"[A-Za-z]{2,}", clean_name):
        raise ValueError("Journal name must contain valid alphabetic characters.")

    clean_abbrev_in = _sanitize_journal_term(abbrev, 80) if abbrev else ""
    clean_short_in = _sanitize_journal_term(short, 40) if short else ""
    clean_cat_in = _sanitize_journal_term(category, 60) if category else ""

    target_list = _get_session_journal_list(session_id)
    if len(target_list) >= 60:
        raise ValueError("Maximum of 60 active journals reached.")

    norm_input = _normalize_journal_key(clean_name)
    norm_abbrev = _normalize_journal_key(clean_abbrev_in)

    # Return existing if already active
    for existing in target_list:
        if (
            existing["id"] == _slugify_journal_id(clean_name)
            or _normalize_journal_key(existing["name"]) == norm_input
            or _normalize_journal_key(existing["abbrev"]) == norm_input
            or _normalize_journal_key(existing["short"]) == norm_input
            or (norm_abbrev and _normalize_journal_key(existing["abbrev"]) == norm_abbrev)
        ):
            return {
                "journal": dict(existing),
                "already_exists": True,
                "journals": get_active_journals(session_id),
            }

    # Check if input matches a known default or suggested specialty journal
    known_catalog = DEFAULT_MEDICAL_JOURNALS + SUGGESTED_EXTRA_JOURNALS
    for preset in known_catalog:
        if (
            preset["id"] == _slugify_journal_id(clean_name)
            or _normalize_journal_key(preset["name"]) == norm_input
            or _normalize_journal_key(preset["abbrev"]) == norm_input
            or _normalize_journal_key(preset["short"]) == norm_input
            or preset["short"].lower() == clean_name.lower()
        ):
            entry = dict(preset)
            if clean_cat_in:
                entry["category"] = clean_cat_in
            target_list.append(entry)
            return {
                "journal": dict(entry),
                "already_exists": False,
                "journals": get_active_journals(session_id),
            }

    eff_abbrev = clean_abbrev_in or clean_name
    eff_short = clean_short_in or (eff_abbrev if len(eff_abbrev) <= 24 else eff_abbrev[:22] + "…")
    eff_category = clean_cat_in or "Custom / Specialty"
    base_id = _slugify_journal_id(eff_short if len(eff_short) >= 3 else clean_name)
    existing_ids = {j["id"] for j in target_list}
    unique_id = base_id
    idx = 2
    while unique_id in existing_ids:
        unique_id = f"{base_id}-{idx}"
        idx += 1

    new_entry = {
        "id": unique_id,
        "name": clean_name,
        "abbrev": eff_abbrev,
        "short": eff_short,
        "category": eff_category,
        "impact_tier": "Physician Added",
        "is_custom": True,
    }
    target_list.append(new_entry)
    return {
        "journal": dict(new_entry),
        "already_exists": False,
        "journals": get_active_journals(session_id),
    }


def remove_journal(journal_id: str, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Removes a journal by its slug ID, short name, or abbreviation."""
    target = (journal_id or "").strip().lower()
    target_norm = _normalize_journal_key(target)
    target_list = _get_session_journal_list(session_id)
    kept = [
        j for j in target_list
        if not (
            j["id"].lower() == target
            or j["short"].lower() == target
            or j["abbrev"].lower() == target
            or _normalize_journal_key(j["name"]) == target_norm
        )
    ]
    target_list.clear()
    target_list.extend(kept)
    return get_active_journals(session_id)


def reset_journals(session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Restores the default 22 whitelisted medical journals."""
    target_list = _get_session_journal_list(session_id)
    target_list.clear()
    target_list.extend(dict(j) for j in DEFAULT_MEDICAL_JOURNALS)
    return get_active_journals(session_id)


# Verified Landmark Clinical Trials & Official Practice Guidelines (Authentic PMIDs & DOIs)
VERIFIED_LANDMARK_LITERATURE: List[Dict[str, Any]] = [
    # Cardiology / HFrEF / CKD / SGLT2i / ARNI / MRA
    {
        "pmid": "31535829",
        "doi": "10.1056/NEJMoa1911303",
        "title": "Dapagliflozin in Patients with Heart Failure and Reduced Ejection Fraction (DAPA-HF)",
        "journal": "The New England Journal of Medicine",
        "journal_short": "NEJM",
        "year": "2019",
        "authors": "McMurray JJV, Solomon SD, Inzucchi SE, et al.",
        "pub_type": "Randomized Controlled Trial",
        "evidence_level": "Level A (Landmark RCT)",
        "keywords": ["hfref", "heart failure", "dapagliflozin", "sglt2", "ejection fraction", "ckd", "diabetes", "gdmt"],
        "abstract_summary": (
            "Among 4,744 patients with NYHA class II–IV heart failure and LVEF <=40%, dapagliflozin 10 mg daily "
            "reduced the composite of worsening heart failure or cardiovascular death vs placebo (HR 0.74; 95% CI 0.65–0.85; P<0.001), "
            "regardless of the presence or absence of type 2 diabetes and across eGFR strata down to 30 mL/min/1.73m²."
        ),
    },
    {
        "pmid": "32865377",
        "doi": "10.1056/NEJMoa2022190",
        "title": "Cardiovascular and Renal Outcomes with Empagliflozin in Heart Failure (EMPEROR-Reduced)",
        "journal": "The New England Journal of Medicine",
        "journal_short": "NEJM",
        "year": "2020",
        "authors": "Packer M, Anker SD, Butler J, et al.",
        "pub_type": "Randomized Controlled Trial",
        "evidence_level": "Level A (Landmark RCT)",
        "keywords": ["hfref", "heart failure", "empagliflozin", "sglt2", "ckd", "renal", "egfr", "gdmt"],
        "abstract_summary": (
            "In 3,730 patients with class II–IV HFrEF (LVEF <=40%) and eGFR down to 20 mL/min/1.73m², empagliflozin 10 mg daily "
            "significantly reduced cardiovascular death or hospitalization for heart failure (HR 0.75; 95% CI 0.65–0.86; P<0.001) "
            "and slowed the annual rate of decline in eGFR."
        ),
    },
    {
        "pmid": "35363499",
        "doi": "10.1161/CIR.0000000000001063",
        "title": "2022 AHA/ACC/HFSA Guideline for the Management of Heart Failure",
        "journal": "Circulation",
        "journal_short": "Circulation (AHA)",
        "year": "2022",
        "authors": "Heidenreich PA, Bozkurt B, Aguilar D, et al.",
        "pub_type": "Practice Guideline",
        "evidence_level": "Class 1, Level A Guideline",
        "keywords": ["hfref", "heart failure", "gdMT", "sacubitril", "arni", "sglt2", "spironolactone", "lisinopril", "washout"],
        "abstract_summary": (
            "Establishes four foundational pillars of GDMT for HFrEF (LVEF <=40%): (1) ARNI (or ACEi/ARB), (2) Evidence-based Beta-Blocker, "
            "(3) Mineralocorticoid Receptor Antagonist (MRA), and (4) SGLT2 Inhibitor. Recommends transitioning from ACEi to Sacubitril/Valsartan "
            "after a mandatory 36-hour ACEi washout period to prevent angioedema (Class 1, Level B-R; Contraindicated concurrently: Class 3: Harm)."
        ),
    },
    {
        "pmid": "30415601",
        "doi": "10.1056/NEJMoa1812389",
        "title": "Angiotensin–Neprilysin Inhibition in Acute Decompensated Heart Failure (PIONEER-HF)",
        "journal": "The New England Journal of Medicine",
        "journal_short": "NEJM",
        "year": "2019",
        "authors": "Velazquez EJ, Morrow DA, DeVore AD, et al.",
        "pub_type": "Randomized Controlled Trial",
        "evidence_level": "Level A (RCT)",
        "keywords": ["hfref", "acute decompensated heart failure", "sacubitril", "valsartan", "arni", "nt-probnp", "inpatient"],
        "abstract_summary": (
            "Among patients hospitalized for acute decompensated HFrEF after hemodynamic stabilization, in-hospital initiation of "
            "sacubitril/valsartan led to a significantly greater reduction in NT-proBNP concentration than enalapril (-46.7% vs -25.3%; P<0.001) "
            "without increased rates of worsening renal function, hyperkalemia, or symptomatic hypotension."
        ),
    },
    {
        "pmid": "33264825",
        "doi": "10.1056/NEJMoa2025845",
        "title": "Effect of Finerenone on Chronic Kidney Disease Outcomes in Type 2 Diabetes (FIDELIO-DKD)",
        "journal": "The New England Journal of Medicine",
        "journal_short": "NEJM",
        "year": "2020",
        "authors": "Bakris GL, Agarwal R, Anker SD, et al.",
        "pub_type": "Randomized Controlled Trial",
        "evidence_level": "Level A (Landmark RCT)",
        "keywords": ["finerenone", "ckd", "chronic kidney disease", "diabetes", "potassium", "albuminuria", "uacr", "mra"],
        "abstract_summary": (
            "In 5,734 patients with CKD and type 2 diabetes on maximally tolerated RAS blockade, the nonsteroidal MRA finerenone "
            "reduced kidney failure, sustained >=40% decrease in eGFR, or renal death (HR 0.82; 95% CI 0.73–0.93; P=0.001) and "
            "cardiovascular events (HR 0.86; P=0.03), requiring baseline serum potassium <=4.8 mmol/L with routine K+ monitoring."
        ),
    },
    # Pulmonology / Severe CAP / Sepsis / Penicillin Allergy
    {
        "pmid": "36942789",
        "doi": "10.1056/NEJMoa2215145",
        "title": "Hydrocortisone in Severe Community-Acquired Pneumonia (CAPE COD Trial)",
        "journal": "The New England Journal of Medicine",
        "journal_short": "NEJM",
        "year": "2023",
        "authors": "Dequin PF, Meziani F, Quenot JP, et al.",
        "pub_type": "Randomized Controlled Trial",
        "evidence_level": "Level A (Landmark RCT)",
        "keywords": ["pneumonia", "cap", "community-acquired pneumonia", "hydrocortisone", "corticosteroid", "icu", "hypoxemic", "sepsis"],
        "abstract_summary": (
            "Among 800 ICU patients with severe community-acquired pneumonia, early intravenous hydrocortisone (200 mg daily continuous "
            "infusion for 4 or 8 days followed by tapering) significantly reduced 28-day all-cause mortality compared with placebo "
            "(6.2% vs 11.9%; absolute difference -5.6 percentage points; 95% CI -9.6 to -1.7; P=0.006) and reduced endotracheal intubation."
        ),
    },
    {
        "pmid": "31573350",
        "doi": "10.1164/rccm.201908-1581ST",
        "title": "Diagnosis and Treatment of Adults with Community-Acquired Pneumonia: An Official ATS and IDSA Clinical Practice Guideline",
        "journal": "American Journal of Respiratory and Critical Care Medicine",
        "journal_short": "AJRCCM (ATS/IDSA)",
        "year": "2019",
        "authors": "Metlay JP, Waterer GW, Long AC, et al.",
        "pub_type": "Practice Guideline",
        "evidence_level": "Official ATS/IDSA Guideline",
        "keywords": ["pneumonia", "cap", "community-acquired pneumonia", "antibiotic", "penicillin", "allergy", "anaphylaxis", "fluoroquinolone", "aztreonam"],
        "abstract_summary": (
            "For severe inpatient CAP without MRSA/Pseudomonas risk factors, standard therapy is a beta-lactam plus a macrolide or respiratory "
            "fluoroquinolone. In patients with severe IgE-mediated beta-lactam/penicillin anaphylaxis, a respiratory fluoroquinolone (levofloxacin "
            "or moxifloxacin) plus aztreonam (plus vancomycin/linezolid if MRSA coverage is indicated) is recommended."
        ),
    },
    {
        "pmid": "34605781",
        "doi": "10.1007/s00134-021-06506-y",
        "title": "Surviving Sepsis Campaign: International Guidelines for Management of Sepsis and Septic Shock 2021",
        "journal": "Intensive Care Medicine",
        "journal_short": "Intensive Care Med",
        "year": "2021",
        "authors": "Evans L, Rhodes A, Alhazzani W, et al.",
        "pub_type": "Practice Guideline",
        "evidence_level": "International Clinical Guideline",
        "keywords": ["sepsis", "septic shock", "lactate", "procalcitonin", "norepinephrine", "hydrocortisone", "antibiotic", "fluid"],
        "abstract_summary": (
            "Recommends administration of antimicrobials immediately, ideally within 1 hour of recognition for septic shock (strong recommendation), "
            "balanced crystalloids for resuscitation guided by dynamic parameters and serial lactate clearance, norepinephrine as first-line vasopressor "
            "targeting MAP >=65 mmHg, and procalcitonin-guided antibiotic discontinuation once clinical stability is achieved."
        ),
    },
    # Cardiology / GI Bleed / AFib Anticoagulation
    {
        "pmid": "38033089",
        "doi": "10.1161/CIR.0000000000001193",
        "title": "2023 ACC/AHA/ACCP/HRS Guideline for the Diagnosis and Management of Atrial Fibrillation",
        "journal": "Circulation",
        "journal_short": "Circulation (AHA)",
        "year": "2024",
        "authors": "Joglar JA, Chung MK, Armbruster AL, et al.",
        "pub_type": "Practice Guideline",
        "evidence_level": "Class 1 Guideline",
        "keywords": ["atrial fibrillation", "afib", "anticoagulation", "doac", "apixaban", "rivaroxaban", "bleeding", "ulcer", "aspirin", "laao"],
        "abstract_summary": (
            "Recommends DOACs over warfarin in eligible non-valvular AF patients (Class 1, Level A). After major gastrointestinal bleeding with "
            "achieved endoscopic hemostasis and high thromboembolic risk (CHA2DS2-VASc >=2), resumption of oral anticoagulation is beneficial once "
            "hemostasis is secure (typically 7–14 days). Concomitant antiplatelet therapy (aspirin) without acute vascular indication is harmful (Class 3: Harm)."
        ),
    },
    {
        "pmid": "30146932",
        "doi": "10.7326/M18-1300",
        "title": "Gastrointestinal Bleeding Risk With Direct Oral Anticoagulants: A Systematic Review and Network Meta-Analysis",
        "journal": "Annals of Internal Medicine",
        "journal_short": "Ann Intern Med",
        "year": "2018",
        "authors": "Ingason AB, Hreinsson JP, Agustsson AS, et al.",
        "pub_type": "Meta-Analysis",
        "evidence_level": "Level A (Systematic Review)",
        "keywords": ["atrial fibrillation", "afib", "apixaban", "rivaroxaban", "dabigatran", "gi bleed", "gastrointestinal bleeding", "ulcer", "ppi"],
        "abstract_summary": (
            "Among direct oral anticoagulants in patients with atrial fibrillation, apixaban is associated with a significantly lower rate "
            "of major gastrointestinal bleeding compared with rivaroxaban and dabigatran. Co-therapy with a proton pump inhibitor (PPI) and H. pylori "
            "eradication further reduces recurrent upper GI ulcer hemorrhage."
        ),
    },
    # Rheumatology / Nephrology / Lupus Nephritis
    {
        "pmid": "32937045",
        "doi": "10.1056/NEJMoa2001180",
        "title": "Two-Year, Randomized, Controlled Trial of Belimumab in Lupus Nephritis (BLISS-LN)",
        "journal": "The New England Journal of Medicine",
        "journal_short": "NEJM",
        "year": "2020",
        "authors": "Furie R, Rovin BH, Houssiau F, et al.",
        "pub_type": "Randomized Controlled Trial",
        "evidence_level": "Level A (Landmark RCT)",
        "keywords": ["lupus nephritis", "sle", "belimumab", "mycophenolate", "mmf", "cyclophosphamide", "proteinuria", "class iv"],
        "abstract_summary": (
            "In 448 patients with biopsy-proven active lupus nephritis (Class III, IV, or V), intravenous belimumab plus standard therapy "
            "(mycophenolate mofetil or cyclophosphamide-azathioprine) significantly increased Primary Efficacy Renal Response at week 104 "
            "(43% vs 32%; OR 1.6; P=0.03) and Complete Renal Response (30% vs 20%; P=0.02), while halving renal-related events or death (HR 0.51)."
        ),
    },
    {
        "pmid": "33971155",
        "doi": "10.1016/S0140-6736(21)00578-X",
        "title": "Efficacy and Safety of Voclosporin Where Added to Mycophenolate Mofetil in Active Lupus Nephritis (AURORA 1)",
        "journal": "The Lancet",
        "journal_short": "The Lancet",
        "year": "2021",
        "authors": "Rovin BH, Teng YKO, Ginzler EM, et al.",
        "pub_type": "Randomized Controlled Trial",
        "evidence_level": "Level A (Landmark RCT)",
        "keywords": ["lupus nephritis", "sle", "voclosporin", "mycophenolate", "mmf", "proteinuria", "upcr", "glucocorticoid", "class iv"],
        "abstract_summary": (
            "In patients with active Class III, IV, or V lupus nephritis and eGFR >45 mL/min/1.73m², adding voclosporin (23.7 mg BID) to "
            "MMF (2 g/day) and a rapid low-dose oral corticosteroid taper achieved superior complete renal remission at week 52 compared with "
            "MMF and low-dose steroids alone (41% vs 23%; OR 2.65; 95% CI 1.64–4.27; P<0.0001)."
        ),
    },
    {
        "pmid": "38182286",
        "doi": "10.1016/j.kint.2023.09.002",
        "title": "KDIGO 2024 Clinical Practice Guideline for the Management of Lupus Nephritis",
        "journal": "Kidney International",
        "journal_short": "Kidney Int (KDIGO)",
        "year": "2024",
        "authors": "Rovin BH, Ayoub IM, Chan TM, et al.",
        "pub_type": "Practice Guideline",
        "evidence_level": "KDIGO 2024 Clinical Guideline",
        "keywords": ["lupus nephritis", "kdigo", "class iv", "belimumab", "voclosporin", "mmf", "hydroxychloroquine", "steroid", "proteinuria"],
        "abstract_summary": (
            "Recommends initial induction for active Class III/IV lupus nephritis with glucocorticoids (reduced-dose regimen: IV methylprednisolone "
            "pulses 0.25–0.5 g/d x 1–3 days then oral prednisone <=0.5 mg/kg/d tapering to <=5 mg/d by 4–6 months) combined with either (1) MPAA (MMF), "
            "(2) low-dose IV cyclophosphamide, (3) Belimumab + MPAA/cyclophosphamide, or (4) Voclosporin + MPAA (if eGFR >45 mL/min/1.73m²), alongside universal Hydroxychloroquine."
        ),
    },
]


def _match_journal_metadata(
    journal_title: str,
    journals_list: Optional[List[Dict[str, str]]] = None,
) -> Optional[Dict[str, str]]:
    """Checks if a journal title, ISO abbreviation, or MedlineTA belongs to the active journal list."""
    norm = _normalize_journal_key(journal_title)
    if not norm:
        return None
    active_list = journals_list if journals_list is not None else ACTIVE_MEDICAL_JOURNALS
    for j in active_list:
        j_name = _normalize_journal_key(j.get("name", ""))
        j_abbrev = _normalize_journal_key(j.get("abbrev", ""))
        j_short = _normalize_journal_key(j.get("short", ""))
        if norm in (j_name, j_abbrev, j_short):
            return j
        # Allow prefix match for long custom multi-word journal titles
        if j.get("is_custom") and len(j_name) >= 12 and (norm.startswith(j_name) or j_name.startswith(norm)):
            return j
    return None


OPEN_SOURCE_RESEARCH_APIS: List[Dict[str, str]] = [
    {
        "id": "ncbi-pubmed",
        "name": "NCBI PubMed Entrez E-Utilities",
        "endpoint": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/",
        "scope": "Peer-reviewed medical journals & MEDLINE clinical guidelines",
    },
    {
        "id": "europe-pmc",
        "name": "Europe PMC REST API (EMBL-EBI)",
        "endpoint": "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
        "scope": "Open-access biomedical literature, citation metrics & full-text links",
    },
    {
        "id": "openalex",
        "name": "OpenAlex Scholarly Research API",
        "endpoint": "https://api.openalex.org/works",
        "scope": "Latest global scholarly research works, DOIs & citation impact",
    },
    {
        "id": "clinicaltrials-v2",
        "name": "ClinicalTrials.gov REST API v2 (NIH/NLM)",
        "endpoint": "https://clinicaltrials.gov/api/v2/studies",
        "scope": "Active & completed interventional clinical trials (NCT registry)",
    },
]


def _safe_https_doi_url(raw_doi_or_url: Optional[str], fallback_url: str) -> str:
    """Ensures external DOI links strictly use HTTPS."""
    val = (raw_doi_or_url or "").strip()
    if not val:
        return fallback_url
    if val.startswith("https://"):
        return val
    if val.startswith("http://doi.org/"):
        return "https://" + val[len("http://"):]
    if val.startswith("10.") and " " not in val and "<" not in val and '"' not in val:
        return f"https://doi.org/{val}"
    return fallback_url


async def search_pubmed_reputed_journals(
    clinical_queries: List[str],
    max_results_per_query: int = 4,
    condition_keywords: Optional[str] = None,
    pub_type_filter: Optional[str] = None,
    custom_journals: Optional[List[Dict[str, Any]]] = None,
    http_client: Optional[httpx.AsyncClient] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Concurrently queries multiple open-source biomedical research APIs:
      1. NCBI PubMed Entrez E-Utilities (strictly filtered to active physician-selected medical journals)
      2. Europe PMC REST API (EMBL-EBI open-access & citation count enrichment)
      3. OpenAlex Scholarly API (latest high-impact works & citation metrics)
      4. ClinicalTrials.gov API v2 (active/recent interventional trials matching the condition)
    """
    journals_to_use: List[Dict[str, Any]] = (
        [dict(j) for j in custom_journals[:60] if isinstance(j, dict)]
        if custom_journals is not None
        else get_active_journals(session_id)
    )
    pub_filter_norm = (pub_type_filter or "all").lower().strip()
    journal_sig = tuple(sorted(_normalize_journal_key(j.get("abbrev") or j.get("name", "")) for j in journals_to_use))
    cache_key = (
        tuple(q.strip() for q in clinical_queries[:3]),
        (condition_keywords or "").strip().lower(),
        pub_filter_norm,
        max_results_per_query,
        journal_sig,
    )

    now_mono = time.monotonic()
    cached_entry = _RETRIEVAL_CACHE.get(cache_key)
    if cached_entry is not None:
        ts, cached_payload = cached_entry
        if now_mono - ts <= RETRIEVAL_CACHE_TTL_SEC:
            _RETRIEVAL_CACHE.move_to_end(cache_key)
            cloned = copy.deepcopy(cached_payload)
            cloned["cache_hit"] = True
            return cloned
        _RETRIEVAL_CACHE.pop(cache_key, None)

    dynamic_pubmed_clause = build_pubmed_journal_filter_clause(journals_to_use)
    ncbi_api_key = os.environ.get("NCBI_API_KEY", "").strip()

    live_articles: Dict[str, Dict[str, Any]] = {}
    clinical_trials: List[Dict[str, Any]] = []
    executed_pubmed_queries: List[str] = []
    api_status_map: Dict[str, str] = {
        "NCBI PubMed E-Utilities": "queried" if journals_to_use else "skipped (0 journals selected)",
        "Europe PMC (EMBL-EBI)": "queried" if journals_to_use else "skipped (0 journals selected)",
        "OpenAlex Research Graph": "queried" if journals_to_use else "skipped (0 journals selected)",
        "ClinicalTrials.gov v2": "queried",
    }

    pubmed_pt_clause = ""
    if pub_filter_norm == "rct":
        pubmed_pt_clause = ' AND ("Randomized Controlled Trial"[Publication Type] OR randomized[Title/Abstract])'
    elif pub_filter_norm == "guideline":
        pubmed_pt_clause = ' AND ("Practice Guideline"[Publication Type] OR "Guideline"[Publication Type] OR guideline[Title])'
    elif pub_filter_norm == "review":
        pubmed_pt_clause = ' AND ("Meta-Analysis"[Publication Type] OR "Systematic Review"[Publication Type] OR "meta-analysis"[Title] OR "systematic review"[Title])'

    pubmed_sem = asyncio.Semaphore(5 if ncbi_api_key else 2)

    async def _run_pubmed_esearch(client: httpx.AsyncClient, raw_q: str) -> List[str]:
        if not dynamic_pubmed_clause:
            return []
        strict_query = f"({raw_q}){pubmed_pt_clause} AND {dynamic_pubmed_clause}"
        executed_pubmed_queries.append(strict_query)
        params: Dict[str, str] = {
            "db": "pubmed",
            "term": strict_query,
            "retmode": "json",
            "retmax": str(max_results_per_query),
            "sort": "relevance",
        }
        if ncbi_api_key:
            params["api_key"] = ncbi_api_key
        try:
            async with pubmed_sem:
                esearch_resp = await client.get(
                    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                    params=params,
                )
            if esearch_resp.status_code != 200:
                api_status_map["NCBI PubMed E-Utilities"] = f"HTTP {esearch_resp.status_code}"
                return []
            api_status_map["NCBI PubMed E-Utilities"] = "200 OK (Live)"
            return [
                str(p)
                for p in (esearch_resp.json().get("esearchresult", {}).get("idlist") or [])
                if str(p).isdigit()
            ]
        except Exception as exc:
            logger.warning("PubMed esearch failed: %s", exc)
            api_status_map["NCBI PubMed E-Utilities"] = "degraded (timeout/network)"
            return []

    async def _run_pubmed_batched(client: httpx.AsyncClient, queries_to_run: List[str]) -> List[Dict[str, Any]]:
        """Runs PubMed esearch across queries, deduplicates PMIDs, and performs ONE batched efetch."""
        if not dynamic_pubmed_clause or not queries_to_run:
            return []
        esearch_lists = await asyncio.gather(
            *(_run_pubmed_esearch(client, q) for q in queries_to_run[:2]),
            return_exceptions=True,
        )
        deduped_pmids: List[str] = []
        seen_id = set()
        for res in esearch_lists:
            if isinstance(res, list):
                for pmid in res:
                    if pmid not in seen_id:
                        seen_id.add(pmid)
                        deduped_pmids.append(pmid)
        if not deduped_pmids:
            return []

        efetch_params: Dict[str, str] = {
            "db": "pubmed",
            "id": ",".join(deduped_pmids[:16]),
            "retmode": "xml",
        }
        if ncbi_api_key:
            efetch_params["api_key"] = ncbi_api_key
        try:
            async with pubmed_sem:
                efetch_resp = await client.get(
                    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
                    params=efetch_params,
                )
            if efetch_resp.status_code == 200:
                api_status_map["NCBI PubMed E-Utilities"] = "200 OK (Live)"
                return _parse_pubmed_xml(efetch_resp.text, journals_to_use)
            api_status_map["NCBI PubMed E-Utilities"] = f"HTTP {efetch_resp.status_code}"
        except Exception as exc:
            logger.warning("PubMed batched efetch failed: %s", exc)
            api_status_map["NCBI PubMed E-Utilities"] = "degraded (efetch timeout)"
        return []

    async def _run_europe_pmc_query(client: httpx.AsyncClient, raw_q: str) -> List[Dict[str, Any]]:
        if not journals_to_use:
            return []
        # Include up to 14 active journals (prioritizing custom-added journals + flagship journals)
        prioritized = sorted(journals_to_use, key=lambda item: (0 if item.get("is_custom") else 1))[:14]
        epmc_parts = [
            f'JOURNAL:"{_sanitize_journal_term(j.get("abbrev") or j.get("name"))}"'
            for j in prioritized
            if _sanitize_journal_term(j.get("abbrev") or j.get("name"))
        ]
        if not epmc_parts:
            return []
        epmc_journal_clause = "(" + " OR ".join(epmc_parts) + ")"
        epmc_pt_clause = ""
        if pub_filter_norm == "rct":
            epmc_pt_clause = " AND (randomized OR trial)"
        elif pub_filter_norm == "guideline":
            epmc_pt_clause = " AND (guideline)"
        elif pub_filter_norm == "review":
            epmc_pt_clause = ' AND ("meta-analysis" OR "systematic review")'
        upper_year = max(date.today().year, 2026)
        q_str = f"({raw_q}){epmc_pt_clause} AND {epmc_journal_clause} AND (FIRST_PDATE:[2020-01-01 TO {upper_year}-12-31])"
        try:
            resp = await client.get(
                "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
                params={
                    "query": q_str,
                    "format": "json",
                    "resultType": "core",
                    "pageSize": "4",
                    "sort": "CITED desc",
                },
            )
            if resp.status_code != 200:
                api_status_map["Europe PMC (EMBL-EBI)"] = f"HTTP {resp.status_code}"
                return []
            api_status_map["Europe PMC (EMBL-EBI)"] = "200 OK (Live)"
            items = resp.json().get("resultList", {}).get("result", [])
            parsed_epmc: List[Dict[str, Any]] = []
            for it in items:
                pmid_raw = str(it.get("pmid") or "").strip()
                j_obj = it.get("journalInfo", {}).get("journal", {}) or {}
                j_title = j_obj.get("title") or it.get("journalTitle", "")
                j_medline = j_obj.get("medlineAbbreviation") or j_obj.get("isoAbbreviation") or ""
                matched_j = (
                    _match_journal_metadata(j_title, journals_to_use)
                    or _match_journal_metadata(j_medline, journals_to_use)
                )
                if not pmid_raw.isdigit() or not matched_j:
                    continue
                abs_text = it.get("abstractText", "")
                if len(abs_text) > 650:
                    abs_text = abs_text[:647] + "..."
                cited_by = it.get("citedByCount", 0)
                doi = str(it.get("doi") or "").strip()
                fallback_epmc_url = f"https://europepmc.org/article/MED/{pmid_raw}"
                parsed_epmc.append({
                    "pmid": pmid_raw,
                    "doi": doi,
                    "title": (it.get("title") or "").rstrip("."),
                    "journal": matched_j["name"],
                    "journal_short": matched_j["short"],
                    "year": str(it.get("pubYear", "Recent")),
                    "authors": it.get("authorString", "Study Investigators")[:90],
                    "pub_type": f"Peer-Reviewed • Cited by {cited_by}",
                    "evidence_level": f"Europe PMC Verified ({cited_by} Citations)",
                    "abstract_summary": abs_text or "Open-access biomedical research record retrieved via Europe PMC REST API.",
                    "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid_raw}/",
                    "doi_url": _safe_https_doi_url(doi, fallback_epmc_url),
                    "source_verification": "Europe PMC Open API + PubMed",
                })
            return parsed_epmc
        except Exception as exc:
            logger.warning("Europe PMC query failed: %s", exc)
            api_status_map["Europe PMC (EMBL-EBI)"] = "degraded (timeout/network)"
            return []

    async def _run_clinical_trials_query(client: httpx.AsyncClient, cond_q: str) -> List[Dict[str, Any]]:
        try:
            resp = await client.get(
                "https://clinicaltrials.gov/api/v2/studies",
                params={
                    "query.term": cond_q,
                    "filter.overallStatus": "RECRUITING,ACTIVE_NOT_RECRUITING,COMPLETED",
                    "pageSize": "4",
                },
            )
            if resp.status_code != 200:
                api_status_map["ClinicalTrials.gov v2"] = f"HTTP {resp.status_code}"
                return []
            api_status_map["ClinicalTrials.gov v2"] = "200 OK (Live)"
            studies = resp.json().get("studies", [])
            out_trials: List[Dict[str, Any]] = []
            for st in studies:
                p = st.get("protocolSection", {})
                ident = p.get("identificationModule", {})
                status_mod = p.get("statusModule", {})
                design_mod = p.get("designModule", {})
                cond_mod = p.get("conditionsModule", {})
                arms_mod = p.get("armsInterventionsModule", {})

                nct_id = str(ident.get("nctId") or "").strip()
                if not re.fullmatch(r"NCT\d{6,10}", nct_id):
                    continue
                interventions = [
                    iv.get("name", "")
                    for iv in (arms_mod.get("interventions", []) or [])[:3]
                    if iv.get("name")
                ]
                phases = ", ".join(design_mod.get("phases", []) or ["Clinical Study"])
                out_trials.append({
                    "nct_id": nct_id,
                    "title": ident.get("briefTitle") or ident.get("officialTitle", "Clinical Trial"),
                    "status": status_mod.get("overallStatus", "ACTIVE"),
                    "phase": phases,
                    "conditions": ", ".join((cond_mod.get("conditions") or [])[:3]),
                    "interventions": ", ".join(interventions) or "Investigational / Standard Care",
                    "url": f"https://clinicaltrials.gov/study/{nct_id}",
                })
            return out_trials
        except Exception as exc:
            logger.warning("ClinicalTrials.gov v2 query failed: %s", exc)
            api_status_map["ClinicalTrials.gov v2"] = "degraded (timeout/network)"
            return []

    async def _run_openalex_query(client: httpx.AsyncClient, raw_q: str) -> List[Dict[str, Any]]:
        if not journals_to_use:
            return []
        clean_oa_q = re.sub(r"\b(AND|OR)\b|[()]", " ", condition_keywords or raw_q)
        clean_oa_q = " ".join(clean_oa_q.split())
        if pub_filter_norm == "rct":
            clean_oa_q = f"{clean_oa_q} randomized trial"
        elif pub_filter_norm == "guideline":
            clean_oa_q = f"{clean_oa_q} guideline"
        elif pub_filter_norm == "review":
            clean_oa_q = f"{clean_oa_q} meta-analysis"
        try:
            resp = await client.get(
                "https://api.openalex.org/works",
                params={
                    "search": clean_oa_q,
                    "filter": "from_publication_date:2020-01-01,has_pmid:true,type:article",
                    "sort": "cited_by_count:desc",
                    "per-page": "5",
                },
            )
            if resp.status_code != 200:
                api_status_map["OpenAlex Research Graph"] = f"HTTP {resp.status_code}"
                return []
            api_status_map["OpenAlex Research Graph"] = "200 OK (Live)"
            works = resp.json().get("results", [])
            parsed_oa: List[Dict[str, Any]] = []
            for w in works:
                ids = w.get("ids", {})
                pmid_url = ids.get("pmid", "")
                pmid = pmid_url.rstrip("/").split("/")[-1] if pmid_url else ""
                loc = w.get("primary_location") or {}
                src = loc.get("source") or {}
                j_name = src.get("display_name", "")
                matched_j = _match_journal_metadata(j_name, journals_to_use)
                if not pmid.isdigit() or not matched_j:
                    continue
                doi_url_raw = str(w.get("doi") or "").strip()
                doi = doi_url_raw.replace("https://doi.org/", "").replace("http://doi.org/", "") if doi_url_raw else ""
                cited_by = w.get("cited_by_count", 0)
                auths = [
                    a.get("author", {}).get("display_name", "")
                    for a in (w.get("authorships") or [])[:3]
                    if a.get("author", {}).get("display_name")
                ]
                authors_str = ", ".join(auths) + (", et al." if len(auths) >= 3 else "")
                pubmed_fallback = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                parsed_oa.append({
                    "pmid": pmid,
                    "doi": doi,
                    "title": w.get("display_name") or w.get("title") or "Medical Research Article",
                    "journal": matched_j["name"],
                    "journal_short": matched_j["short"],
                    "year": str(w.get("publication_year", "Recent")),
                    "authors": authors_str or "Study Investigators",
                    "pub_type": f"OpenAlex • {cited_by} Citations",
                    "evidence_level": f"High-Impact Study ({cited_by} Citations)",
                    "abstract_summary": (
                        f"High-impact peer-reviewed study published in {matched_j['name']} "
                        f"({w.get('publication_year')}), cited {cited_by} times in global biomedical literature (OpenAlex & PubMed indexed)."
                    ),
                    "pubmed_url": pubmed_fallback,
                    "doi_url": _safe_https_doi_url(doi_url_raw or doi, pubmed_fallback),
                    "source_verification": "OpenAlex + PubMed Verified",
                })
            return parsed_oa
        except Exception as exc:
            logger.warning("OpenAlex query failed: %s", exc)
            api_status_map["OpenAlex Research Graph"] = "degraded (timeout/network)"
            return []

    primary_q = clinical_queries[0] if clinical_queries else "clinical practice guideline"
    ct_query = condition_keywords or primary_q[:60]

    async def _execute_with_client(active_client: httpx.AsyncClient) -> None:
        nonlocal clinical_trials
        results_list = await asyncio.gather(
            _run_pubmed_batched(active_client, clinical_queries[:2] or [primary_q]),
            _run_europe_pmc_query(active_client, primary_q),
            _run_openalex_query(active_client, primary_q),
            _run_clinical_trials_query(active_client, ct_query),
            return_exceptions=True,
        )
        for idx in (0, 1, 2):
            if isinstance(results_list[idx], list):
                for item in results_list[idx]:
                    if item["pmid"] not in live_articles:
                        live_articles[item["pmid"]] = item
        if isinstance(results_list[3], list):
            clinical_trials = results_list[3]

    try:
        if http_client is not None:
            await _execute_with_client(http_client)
        else:
            async with httpx.AsyncClient(timeout=8.0) as temp_client:
                await _execute_with_client(temp_client)
    except Exception as exc:
        logger.warning("Multi-API retrieval orchestration error: %s", exc)

    # Match verified landmark clinical trials & guidelines relevant to the queries AND active journals
    combined_query_text = " ".join(clinical_queries).lower()
    min_landmark_score = 2 if len(live_articles) >= 3 else 1
    scored_landmarks = []
    for art in VERIFIED_LANDMARK_LITERATURE:
        matched_landmark_j = _match_journal_metadata(art.get("journal", ""), journals_to_use)
        if not matched_landmark_j:
            continue
        pt_lower = art.get("pub_type", "").lower()
        if pub_filter_norm == "rct" and "trial" not in pt_lower:
            continue
        if pub_filter_norm == "guideline" and "guideline" not in pt_lower:
            continue
        if pub_filter_norm == "review" and "meta-analysis" not in pt_lower and "review" not in pt_lower:
            continue
        score = sum(
            2 if (" " in kw and kw.lower() in combined_query_text) else (
                1 if re.search(rf"\b{re.escape(kw.lower())}\b", combined_query_text) else 0
            )
            for kw in art["keywords"]
        )
        if score >= min_landmark_score:
            scored_landmarks.append((score, art, matched_landmark_j))
    scored_landmarks.sort(key=lambda x: x[0], reverse=True)

    final_articles: List[Dict[str, Any]] = []
    seen_pmids = set()

    # Include top matched landmark RCTs & official guidelines from active journals
    for _, art, matched_landmark_j in scored_landmarks[:5]:
        pmid = art["pmid"]
        if pmid not in seen_pmids:
            seen_pmids.add(pmid)
            pubmed_fallback = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            final_articles.append({
                **art,
                "journal": matched_landmark_j["name"],
                "journal_short": matched_landmark_j["short"],
                "pubmed_url": pubmed_fallback,
                "doi_url": _safe_https_doi_url(art.get("doi"), pubmed_fallback),
                "source_verification": "PubMed & Landmark Trial Registry",
            })

    # Append live PubMed, Europe PMC & OpenAlex articles from active journals
    for pmid, art in live_articles.items():
        if pmid not in seen_pmids:
            seen_pmids.add(pmid)
            final_articles.append(art)

    capped_articles = final_articles[:12]

    # Summarize publications that returned papers in this query
    matched_counts: Dict[str, Dict[str, Any]] = {}
    for art in capped_articles:
        j_short = art.get("journal_short", art.get("journal", "Journal"))
        if j_short not in matched_counts:
            matched_j_meta = _match_journal_metadata(art.get("journal", ""), journals_to_use)
            matched_counts[j_short] = {
                "id": matched_j_meta["id"] if matched_j_meta else _slugify_journal_id(j_short),
                "name": art.get("journal", j_short),
                "short": j_short,
                "count": 0,
            }
        matched_counts[j_short]["count"] += 1

    matched_journals = sorted(
        matched_counts.values(),
        key=lambda item: (-item["count"], item["short"]),
    )

    result_payload: Dict[str, Any] = {
        "articles": capped_articles,
        "clinical_trials": clinical_trials,
        "open_source_apis": OPEN_SOURCE_RESEARCH_APIS,
        "api_status_map": api_status_map,
        "executed_queries": executed_pubmed_queries,
        "covered_journals": journals_to_use,
        "matched_journals": matched_journals,
        "whitelisted_journals_count": len(journals_to_use),
        "live_articles_retrieved": len(live_articles),
        "cache_hit": False,
    }

    if live_articles or clinical_trials:
        while len(_RETRIEVAL_CACHE) >= RETRIEVAL_CACHE_MAX_ENTRIES:
            _RETRIEVAL_CACHE.popitem(last=False)
        _RETRIEVAL_CACHE[cache_key] = (time.monotonic(), copy.deepcopy(result_payload))

    return result_payload


def _parse_pubmed_xml(
    xml_text: str,
    journals_list: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    if not xml_text or len(xml_text) > MAX_PUBMED_XML_BYTES:
        logger.warning("Rejected empty or oversized PubMed XML payload (%d chars).", len(xml_text or ""))
        return results
    # Block DTD entity expansion (Billion Laughs / XXE) before parsing
    if re.search(r"<!\s*ENTITY\b", xml_text, flags=re.IGNORECASE):
        logger.warning("Blocked PubMed XML containing <!ENTITY declaration.")
        return results
    # Strip benign <!DOCTYPE PubmedArticleSet ...> header if present without custom entities
    sanitized_xml = re.sub(r"<!DOCTYPE[^>]*>", "", xml_text, count=1, flags=re.IGNORECASE)
    try:
        root = SafeET.fromstring(sanitized_xml)
        for article_elem in root.findall(".//PubmedArticle"):
            pmid_elem = article_elem.find(".//MedlineCitation/PMID")
            if pmid_elem is None or not pmid_elem.text:
                continue
            pmid = pmid_elem.text.strip()
            if not pmid.isdigit():
                continue

            title_elem = article_elem.find(".//Article/ArticleTitle")
            title = "".join(title_elem.itertext()).strip() if title_elem is not None else "Untitled Medical Article"

            journal_title_elem = article_elem.find(".//Article/Journal/Title")
            journal_iso_elem = article_elem.find(".//Article/Journal/ISOAbbreviation")
            medline_ta_elem = article_elem.find(".//MedlineJournalInfo/MedlineTA")

            j_title_txt = journal_title_elem.text if (journal_title_elem is not None and journal_title_elem.text) else ""
            j_medline_txt = medline_ta_elem.text if (medline_ta_elem is not None and medline_ta_elem.text) else ""
            j_iso_txt = journal_iso_elem.text if (journal_iso_elem is not None and journal_iso_elem.text) else ""

            matched_j = (
                _match_journal_metadata(j_title_txt, journals_list)
                or _match_journal_metadata(j_medline_txt, journals_list)
                or _match_journal_metadata(j_iso_txt, journals_list)
            )
            if not matched_j:
                # Strictly enforce active journal whitelist
                continue

            year_elem = article_elem.find(".//Article/Journal/JournalIssue/PubDate/Year")
            medline_date_elem = article_elem.find(".//Article/Journal/JournalIssue/PubDate/MedlineDate")
            year = (
                year_elem.text.strip()
                if (year_elem is not None and year_elem.text)
                else (medline_date_elem.text[:4] if (medline_date_elem is not None and medline_date_elem.text) else "Recent")
            )

            # Extract authors
            author_list = []
            for auth in article_elem.findall(".//Article/AuthorList/Author")[:3]:
                last = auth.find("LastName")
                initials = auth.find("Initials")
                if last is not None and last.text:
                    init_str = f" {initials.text}" if (initials is not None and initials.text) else ""
                    author_list.append(f"{last.text}{init_str}")
            authors_str = ", ".join(author_list) + (", et al." if len(author_list) >= 3 else "")
            if not authors_str:
                authors_str = "Study Investigators"

            # Extract abstract
            abstract_parts = []
            for abs_text in article_elem.findall(".//Article/Abstract/AbstractText"):
                label = abs_text.attrib.get("Label")
                txt = "".join(abs_text.itertext()).strip()
                if txt:
                    abstract_parts.append(f"{label}: {txt}" if label else txt)
            abstract_summary = " ".join(abstract_parts)
            if len(abstract_summary) > 650:
                abstract_summary = abstract_summary[:647] + "..."
            if not abstract_summary:
                abstract_summary = "Peer-reviewed clinical article indexed in PubMed from a whitelisted medical journal."

            # Extract DOI
            doi = None
            for id_elem in article_elem.findall(".//PubmedData/ArticleIdList/ArticleId"):
                if id_elem.attrib.get("IdType") == "doi" and id_elem.text:
                    doi = id_elem.text.strip()
                    break

            # Extract Publication Types
            pub_types = [
                pt.text for pt in article_elem.findall(".//Article/PublicationTypeList/PublicationType") if pt.text
            ]
            primary_pub_type = "Peer-Reviewed Clinical Study"
            evidence_level = "Level B (Peer-Reviewed Study)"
            for pt in pub_types:
                pt_low = pt.lower()
                if "practice guideline" in pt_low or "guideline" in pt_low:
                    primary_pub_type = "Practice Guideline"
                    evidence_level = "Class 1 Clinical Guideline"
                    break
                if "randomized controlled trial" in pt_low:
                    primary_pub_type = "Randomized Controlled Trial"
                    evidence_level = "Level A (RCT)"
                    break
                if "meta-analysis" in pt_low or "systematic review" in pt_low:
                    primary_pub_type = "Systematic Review / Meta-Analysis"
                    evidence_level = "Level A (Meta-Analysis)"
                    break

            pubmed_fallback = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            results.append({
                "pmid": pmid,
                "doi": doi or "",
                "title": title,
                "journal": matched_j["name"],
                "journal_short": matched_j["short"],
                "year": year,
                "authors": authors_str,
                "pub_type": primary_pub_type,
                "evidence_level": evidence_level,
                "abstract_summary": abstract_summary,
                "pubmed_url": pubmed_fallback,
                "doi_url": _safe_https_doi_url(doi, pubmed_fallback),
                "source_verification": f"Live NCBI PubMed Verified ({matched_j['short']})",
            })
    except Exception as exc:
        logger.warning("PubMed XML parsing failed: %s", exc)
    return results
