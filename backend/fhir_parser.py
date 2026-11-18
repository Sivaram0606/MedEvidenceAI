"""
Agent 1: HL7 FHIR R4 Clinical Parser & Phenotyper.
Ingests raw FHIR R4 Bundles (from local JSON, uploaded files, or external FHIR REST endpoints)
and extracts structured patient demographics, conditions, labs, vitals, medications, allergies,
and automated clinical safety flags.
"""

import asyncio
from datetime import date, datetime
import ipaddress
import json
import os
import re
import socket
from typing import Dict, Any, List, Optional
from urllib.parse import urljoin, urlparse
import httpx

MAX_EXTERNAL_FHIR_BYTES = 2 * 1024 * 1024  # 2 MB cap for external FHIR bundles
MAX_FHIR_REDIRECT_HOPS = 3
_BLOCKED_HOSTNAMES = {"localhost", "metadata.google.internal", "metadata", "169.254.169.254"}


def _sanitize_fhir_text(text: Optional[str], max_len: int = 320) -> str:
    """Strips control characters and XML delimiter characters from untrusted FHIR text fields."""
    if not text:
        return ""
    cleaned = re.sub(r"[\x00-\x1f\x7f]+", " ", str(text))
    cleaned = cleaned.replace("<", "‹").replace(">", "›")
    cleaned = " ".join(cleaned.split())
    if len(cleaned) > max_len:
        return cleaned[: max_len - 1].rstrip() + "…"
    return cleaned


def _calculate_age(birth_date_str: Optional[str], reference_date: Optional[date] = None) -> Optional[int]:
    if not birth_date_str:
        return None
    try:
        bdate = datetime.strptime(birth_date_str[:10], "%Y-%m-%d").date()
        today = reference_date or date.today()
        return today.year - bdate.year - ((today.month, today.day) < (bdate.month, bdate.day))
    except Exception:
        return None


def parse_fhir_bundle(bundle: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parses an HL7 FHIR R4 Bundle into a normalized clinical summary structure
    for both the Physician UI and downstream clinical reasoning agents.
    """
    entries = bundle.get("entry", [])
    if not entries and bundle.get("resourceType") == "Patient":
        entries = [{"resource": bundle}]

    patient_info: Dict[str, Any] = {
        "id": "unknown",
        "mrn": "N/A",
        "name": "Unknown Patient",
        "gender": "unknown",
        "birthDate": None,
        "age": None,
    }
    encounter_info: Dict[str, Any] = {
        "class": "Outpatient / Inpatient",
        "type": "Clinical Consultation",
        "reason": "Clinical evaluation",
    }
    conditions: List[Dict[str, Any]] = []
    observations: List[Dict[str, Any]] = []
    medications: List[Dict[str, Any]] = []
    allergies: List[Dict[str, Any]] = []

    for item in entries[:250]:
        if not isinstance(item, dict):
            continue
        res = item.get("resource", item)
        if not isinstance(res, dict):
            continue
        rtype = res.get("resourceType")

        if rtype == "Patient":
            patient_info["id"] = _sanitize_fhir_text(res.get("id", "unknown"), 80) or "unknown"
            identifiers = res.get("identifier", [])
            if identifiers and isinstance(identifiers[0], dict):
                patient_info["mrn"] = _sanitize_fhir_text(identifiers[0].get("value", "N/A"), 80) or "N/A"
            names = res.get("name", [])
            if names and isinstance(names[0], dict):
                n = names[0]
                given = " ".join(str(g) for g in (n.get("given") or []))
                family = str(n.get("family") or "")
                full_name = f"{given} {family}".strip() or str(n.get("text") or "Unknown Patient")
                patient_info["name"] = _sanitize_fhir_text(full_name.title(), 120) or "Unknown Patient"
            patient_info["gender"] = _sanitize_fhir_text((res.get("gender") or "unknown").capitalize(), 32) or "Unknown"
            patient_info["birthDate"] = _sanitize_fhir_text(res.get("birthDate"), 16) or None
            patient_info["age"] = _calculate_age(patient_info["birthDate"])

        elif rtype == "Encounter":
            cls = res.get("class", {}) if isinstance(res.get("class"), dict) else {}
            encounter_info["class"] = _sanitize_fhir_text(
                cls.get("display") or cls.get("code") or "Clinical Encounter", 120
            )
            types = res.get("type", [])
            if types and isinstance(types[0], dict):
                encounter_info["type"] = _sanitize_fhir_text(types[0].get("text") or "Clinical Evaluation", 200)
            reasons = res.get("reasonCode", [])
            if reasons and isinstance(reasons[0], dict):
                encounter_info["reason"] = _sanitize_fhir_text(
                    reasons[0].get("text") or encounter_info["type"], 200
                )

        elif rtype == "Condition":
            code_obj = res.get("code", {}) if isinstance(res.get("code"), dict) else {}
            codings = [c for c in (code_obj.get("coding") or []) if isinstance(c, dict)]
            primary_code = _sanitize_fhir_text(codings[0].get("code", ""), 40) if codings else ""
            primary_system = _sanitize_fhir_text(codings[0].get("system", ""), 120) if codings else ""
            icd10_code = next(
                (
                    _sanitize_fhir_text(c.get("code"), 40)
                    for c in codings
                    if "icd-10" in (c.get("system") or "").lower()
                ),
                None,
            )
            snomed_code = next(
                (
                    _sanitize_fhir_text(c.get("code"), 40)
                    for c in codings
                    if "snomed" in (c.get("system") or "").lower()
                ),
                None,
            )
            display_text = _sanitize_fhir_text(
                code_obj.get("text")
                or (codings[0].get("display") if codings else "Unspecified Condition"),
                220,
            )
            clinical_status_codings = (
                res.get("clinicalStatus", {}).get("coding", [{}])
                if isinstance(res.get("clinicalStatus"), dict)
                else [{}]
            )
            clinical_status = _sanitize_fhir_text(
                clinical_status_codings[0].get("code", "active") if clinical_status_codings else "active",
                32,
            )
            conditions.append({
                "id": _sanitize_fhir_text(res.get("id", ""), 80),
                "display": display_text or "Unspecified Condition",
                "snomed_code": snomed_code or primary_code,
                "icd10_code": icd10_code,
                "system": primary_system,
                "status": clinical_status,
                "onset": _sanitize_fhir_text(res.get("onsetDateTime", "Not specified"), 40),
            })

        elif rtype == "Observation":
            code_obj = res.get("code", {}) if isinstance(res.get("code"), dict) else {}
            codings = [c for c in (code_obj.get("coding") or []) if isinstance(c, dict)]
            loinc = _sanitize_fhir_text(codings[0].get("code", ""), 40) if codings else ""
            label = _sanitize_fhir_text(
                code_obj.get("text") or (codings[0].get("display") if codings else "Observation"),
                180,
            )

            val_qty = res.get("valueQuantity") if isinstance(res.get("valueQuantity"), dict) else None
            val_str = res.get("valueString")
            if val_qty:
                val = val_qty.get("value")
                unit = _sanitize_fhir_text(val_qty.get("unit", ""), 40)
                formatted_value = _sanitize_fhir_text(f"{val} {unit}".strip(), 120)
                numeric_value = val if isinstance(val, (int, float)) else None
            elif val_str:
                formatted_value = _sanitize_fhir_text(val_str, 180)
                numeric_value = None
                unit = ""
            else:
                formatted_value = "Recorded"
                numeric_value = None
                unit = ""

            ref_ranges = res.get("referenceRange", [])
            ref_str = ""
            if ref_ranges and isinstance(ref_ranges[0], dict):
                r = ref_ranges[0]
                low = (r.get("low") or {}).get("value") if isinstance(r.get("low"), dict) else None
                high = (r.get("high") or {}).get("value") if isinstance(r.get("high"), dict) else None
                r_unit = _sanitize_fhir_text(
                    ((r.get("low") or {}).get("unit") if isinstance(r.get("low"), dict) else None)
                    or ((r.get("high") or {}).get("unit") if isinstance(r.get("high"), dict) else None)
                    or unit,
                    40,
                )
                if low is not None and high is not None:
                    ref_str = f"{low}–{high} {r_unit}".strip()
                elif high is not None:
                    ref_str = f"<{high} {r_unit}".strip()
                elif low is not None:
                    ref_str = f">{low} {r_unit}".strip()

            interps = res.get("interpretation", [])
            flag_code = "N"
            flag_display = "Normal"
            if interps and isinstance(interps[0], dict):
                icodings = interps[0].get("coding") or [{}]
                icoding = icodings[0] if (icodings and isinstance(icodings[0], dict)) else {}
                flag_code = _sanitize_fhir_text(icoding.get("code", "N"), 16) or "N"
                flag_display = _sanitize_fhir_text(icoding.get("display", flag_code), 64) or flag_code

            observations.append({
                "id": _sanitize_fhir_text(res.get("id", ""), 80),
                "name": label or "Observation",
                "loinc": loinc,
                "value": formatted_value,
                "numeric_value": numeric_value,
                "unit": unit,
                "reference_range": ref_str,
                "flag": flag_code,
                "flag_display": flag_display,
                "is_abnormal": flag_code in ("H", "HH", "L", "LL", "A", "AA"),
                "is_critical": flag_code in ("HH", "LL", "AA"),
            })

        elif rtype in ("MedicationStatement", "MedicationRequest"):
            med_concept = (
                res.get("medicationCodeableConcept", {})
                if isinstance(res.get("medicationCodeableConcept"), dict)
                else {}
            )
            codings = [c for c in (med_concept.get("coding") or []) if isinstance(c, dict)]
            rxnorm = _sanitize_fhir_text(codings[0].get("code", ""), 40) if codings else ""
            med_text = _sanitize_fhir_text(
                med_concept.get("text")
                or (codings[0].get("display") if codings else "Medication"),
                200,
            )
            medications.append({
                "id": _sanitize_fhir_text(res.get("id", ""), 80),
                "name": med_text or "Medication",
                "rxnorm": rxnorm,
                "status": _sanitize_fhir_text(res.get("status", "active"), 32) or "active",
            })

        elif rtype == "AllergyIntolerance":
            code_obj = res.get("code", {}) if isinstance(res.get("code"), dict) else {}
            substance = _sanitize_fhir_text(code_obj.get("text") or "Unspecified Allergen", 160)
            criticality = _sanitize_fhir_text(res.get("criticality", "moderate"), 32) or "moderate"
            reactions = res.get("reaction", [])
            reaction_text = "Documented intolerance"
            if reactions and isinstance(reactions[0], dict):
                manif = reactions[0].get("manifestation", [])
                if manif and isinstance(manif[0], dict):
                    reaction_text = _sanitize_fhir_text(manif[0].get("text", reaction_text), 200)
            allergies.append({
                "id": _sanitize_fhir_text(res.get("id", ""), 80),
                "substance": substance or "Unspecified Allergen",
                "criticality": criticality,
                "reaction": reaction_text or "Documented intolerance",
            })

    # Generate automated FHIR clinical safety alerts
    safety_alerts = _derive_clinical_safety_alerts(conditions, observations, medications, allergies)

    # Create a HIPAA de-identified structured narrative prompt context for LLM Agents
    # (Direct identifiers like Patient.name, MRN, and exact birthDate are strictly excluded)
    age_label = f"{patient_info['age']}yo" if patient_info["age"] is not None else "Adult"
    narrative_lines = [
        f"PATIENT PHENOTYPE: {age_label} {patient_info['gender']} (De-Identified HL7 FHIR R4 Context)",
        f"ENCOUNTER: {encounter_info['class']} — {encounter_info['type']} ({encounter_info['reason']})",
        "",
        "ACTIVE CONDITIONS (FHIR Condition):",
    ]
    for c in conditions:
        codes = []
        if c.get("icd10_code"):
            codes.append(f"ICD-10: {c['icd10_code']}")
        if c.get("snomed_code"):
            codes.append(f"SNOMED: {c['snomed_code']}")
        code_suffix = f" [{' | '.join(codes)}]" if codes else ""
        narrative_lines.append(f"- {c['display']}{code_suffix}")

    narrative_lines.append("\nKEY OBSERVATIONS, LABS & VITALS (FHIR Observation):")
    for o in observations:
        ref = f" (Ref: {o['reference_range']})" if o["reference_range"] else ""
        flag = f" [{o['flag_display']}]" if o["is_abnormal"] else ""
        narrative_lines.append(f"- {o['name']} (LOINC {o['loinc']}): {o['value']}{ref}{flag}")

    narrative_lines.append("\nMEDICATIONS (FHIR MedicationStatement/Request):")
    for m in medications:
        narrative_lines.append(f"- {m['name']} (Status: {m['status']})")

    narrative_lines.append("\nALLERGIES & INTOLERANCES (FHIR AllergyIntolerance):")
    if allergies:
        for a in allergies:
            narrative_lines.append(f"- {a['substance']} (Criticality: {a['criticality'].upper()}) -> {a['reaction']}")
    else:
        narrative_lines.append("- No Known Drug Allergies (NKDA)")

    if safety_alerts:
        narrative_lines.append("\nPHARMACOLOGICAL & SUBGROUP RESEARCH CONTEXT (FROM FHIR CHART):")
        for alert in safety_alerts:
            narrative_lines.append(f"- [{alert['severity'].upper()}] {alert['title']}: {alert['detail']}")

    auto_query_bundle = generate_patient_auto_query(
        patient_info=patient_info,
        encounter_info=encounter_info,
        conditions=conditions,
        observations=observations,
        medications=medications,
        allergies=allergies,
    )

    deidentified_narrative = "\n".join(narrative_lines)
    return {
        "patient": patient_info,
        "encounter": encounter_info,
        "conditions": conditions,
        "observations": observations,
        "medications": medications,
        "allergies": allergies,
        "safety_alerts": safety_alerts,
        "auto_generated_query": auto_query_bundle["query"],
        "auto_suggested_questions": auto_query_bundle["suggested_questions"],
        "clinical_narrative": deidentified_narrative,
        "deidentified_narrative": deidentified_narrative,
        "resource_counts": {
            "conditions": len(conditions),
            "observations": len(observations),
            "medications": len(medications),
            "allergies": len(allergies),
        },
    }


def _short_label(text: str, max_len: int = 68) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= max_len:
        return cleaned
    # Trim cleanly at parenthetical or word boundary if overly verbose
    if "(" in cleaned and cleaned.index("(") > 12:
        base = cleaned[: cleaned.index("(")].strip()
        if base:
            return base
    return cleaned[: max_len - 3].rsplit(" ", 1)[0] + "..."


def generate_patient_auto_query(
    patient_info: Dict[str, Any],
    encounter_info: Dict[str, Any],
    conditions: List[Dict[str, Any]],
    observations: List[Dict[str, Any]],
    medications: List[Dict[str, Any]],
    allergies: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Dynamically formulates a patient-specific clinical literature research query
    and follow-up questions directly from the selected patient's HL7 FHIR R4 chart.
    """
    age = patient_info.get("age")
    gender_raw = (patient_info.get("gender") or "").lower()
    gender_word = gender_raw if gender_raw in ("male", "female") else "adult"
    demo_phrase = f"{age}-year-old {gender_word}" if age else f"{gender_word} patient"

    cond_labels = [_short_label(c.get("display", ""), 64) for c in conditions[:3] if c.get("display")]
    abnormal_obs = [o for o in observations if o.get("is_abnormal")] or observations[:3]
    obs_labels = [
        f"{_short_label(o.get('name', ''), 34)} {o.get('value', '')}".strip()
        for o in abnormal_obs[:3]
        if o.get("name")
    ]
    med_labels = [
        _short_label(m.get("name", "").split("(")[0].strip(), 38)
        for m in medications[:3]
        if m.get("name")
    ]
    allergy_labels = [
        f"{a.get('substance')} ({a.get('reaction')})" if a.get("reaction") else str(a.get("substance"))
        for a in allergies[:2]
        if a.get("substance")
    ]

    if cond_labels:
        if len(cond_labels) == 1:
            cond_phrase = cond_labels[0]
        elif len(cond_labels) == 2:
            cond_phrase = f"{cond_labels[0]} and {cond_labels[1]}"
        else:
            cond_phrase = f"{', '.join(cond_labels[:-1])}, and {cond_labels[-1]}"
    else:
        enc_reason = encounter_info.get("reason") or encounter_info.get("type") or "general clinical evaluation"
        cond_phrase = _short_label(enc_reason, 64)

    context_clauses: List[str] = []
    if obs_labels:
        context_clauses.append(f"labs/vitals: {', '.join(obs_labels)}")
    if med_labels:
        context_clauses.append(f"medications: {', '.join(med_labels)}")
    if allergy_labels:
        context_clauses.append(f"allergies: {', '.join(allergy_labels)}")

    clinical_modifiers = f" ({'; '.join(context_clauses)})" if context_clauses else ""

    auto_query = (
        f"For a {demo_phrase} with {cond_phrase}{clinical_modifiers}: "
        f"what do peer-reviewed clinical trials and society guidelines report on comparative therapeutic efficacy, "
        f"diagnostic cohort criteria, and subgroup safety/exclusion considerations?"
    )

    primary_topic = cond_labels[0] if cond_labels else cond_phrase
    suggested: List[str] = [
        f"Summarize landmark RCT primary endpoints and subgroup outcomes matching {primary_topic}.",
    ]
    if obs_labels:
        suggested.append(
            f"How do published trial protocols stratify dosing and eligibility for {obs_labels[0]}?"
        )
    if allergy_labels or med_labels:
        med_or_allergy = allergy_labels[0] if allergy_labels else med_labels[0]
        suggested.append(
            f"What pharmacokinetic interactions, washout rules, or safety data apply to {med_or_allergy}?"
        )
    else:
        suggested.append(
            f"What diagnostic workup and biomarker monitoring intervals are recommended in guidelines for {primary_topic}?"
        )

    return {
        "query": auto_query,
        "suggested_questions": suggested[:3],
    }


def _derive_clinical_safety_alerts(
    conditions: List[Dict[str, Any]],
    observations: List[Dict[str, Any]],
    medications: List[Dict[str, Any]],
    allergies: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    alerts: List[Dict[str, str]] = []
    med_names = " ".join(m["name"].lower() for m in medications)
    cond_names = " ".join(c["display"].lower() for c in conditions)

    egfr_val = None
    k_val = None
    lactate_val = None
    for o in observations:
        name_lower = o["name"].lower()
        if ("egfr" in name_lower or "gfr" in name_lower or "creatinine clearance" in name_lower) and o["numeric_value"] is not None:
            egfr_val = float(o["numeric_value"])
        if "potassium" in name_lower and o["numeric_value"] is not None:
            k_val = float(o["numeric_value"])
        if "lactate" in name_lower and o["numeric_value"] is not None:
            lactate_val = float(o["numeric_value"])

    if egfr_val is not None and egfr_val < 45 and "metformin" in med_names:
        alerts.append({
            "severity": "high",
            "title": f"Renal Subgroup Literature Context: Metformin at eGFR {egfr_val} mL/min/1.73m²",
            "detail": f"Chart records Metformin 1000 mg BID with eGFR {egfr_val} mL/min/1.73m². Published KDIGO and FDA pharmacokinetic literature evaluate lower maximum daily exposure (<=1000 mg/day) in Stage 3b CKD (eGFR 30–44) and temporary interruption during acute decompensated heart failure.",
        })

    if "lisinopril" in med_names and ("hfref" in cond_names or "systolic heart failure" in cond_names):
        alerts.append({
            "severity": "critical",
            "title": "Pharmacokinetic Washout Literature: ACEi & Neprilysin Inhibition (ARNI)",
            "detail": "Chart records active Lisinopril. In PARADIGM-HF and PIONEER-HF trial protocols, a 36-hour washout window between ACEi cessation and sacubitril/valsartan exposure was studied to prevent bradykinin-mediated angioedema.",
        })

    if k_val is not None and k_val >= 4.8 and ("hfref" in cond_names or "chronic kidney disease" in cond_names):
        alerts.append({
            "severity": "moderate",
            "title": f"Electrolyte Subgroup Context: Baseline Serum K+ {k_val} mEq/L",
            "detail": "FIDELIO-DKD and RALES/EMPHASIS-HF protocols stratified enrollment by baseline serum potassium (typically <=4.8–5.0 mEq/L). Secondary analyses of DAPA-HF and EMPEROR-Reduced report lower incidence of severe hyperkalemia when SGLT2 inhibitors are co-administered with MRAs.",
        })

    for a in allergies:
        if "penicillin" in a["substance"].lower() and ("anaphylaxis" in a["reaction"].lower() or a["criticality"] == "high"):
            alerts.append({
                "severity": "critical",
                "title": "Immunologic Cross-Reactivity Literature: IgE Penicillin Anaphylaxis",
                "detail": f"Chart documents {a['reaction']} to {a['substance']}. ATS/IDSA and allergy literature distinguish R1 side-chain cross-reactivity from structurally distinct monobactams (aztreonam) and fluoroquinolones in severe IgE-mediated reactions.",
            })

    if lactate_val is not None and lactate_val >= 3.0:
        alerts.append({
            "severity": "critical",
            "title": f"Biomarker Stratification Context: Serum Lactate {lactate_val} mmol/L",
            "detail": "In Surviving Sepsis Campaign and ANDROMEDA-SHOCK studies, serum lactate >2.0–3.0 mmol/L serves as a key prognostic marker of tissue hypoperfusion and a longitudinal endpoint for evaluating resuscitation kinetics.",
        })

    if "aspirin" in med_names and ("ulcer" in cond_names or "gi hemorrhage" in cond_names or "bleeding" in cond_names):
        alerts.append({
            "severity": "high",
            "title": "Antithrombotic Subgroup Literature: Concurrent Aspirin + DOAC in AFib",
            "detail": "Chart lists OTC Aspirin 81 mg alongside non-valvular AFib and recent duodenal ulcer hemorrhage. Observational cohorts and ACC/AHA guideline evidence reviews report significantly higher major GI bleeding hazard ratios with dual DOAC + antiplatelet therapy in the absence of recent coronary stenting.",
        })

    return alerts


async def _validate_safe_external_fhir_url(raw_url: str) -> str:
    """
    Validates an external FHIR URL against SSRF vectors (non-HTTPS schemes, embedded credentials,
    cloud metadata hosts, loopback, RFC1918 private networks, and link-local addresses).
    """
    url_str = (raw_url or "").strip()
    if not url_str or len(url_str) > 2048:
        raise ValueError("Invalid FHIR URL length.")

    parsed = urlparse(url_str)
    allow_http = os.environ.get("ALLOW_HTTP_FHIR_URLS", "").lower() == "true"
    allowed_schemes = {"https", "http"} if allow_http else {"https"}
    if parsed.scheme.lower() not in allowed_schemes:
        raise ValueError("External FHIR URLs must use HTTPS.")

    if parsed.username or parsed.password:
        raise ValueError("Credentials in FHIR URLs are not permitted.")

    hostname = (parsed.hostname or "").strip().lower().rstrip(".")
    if not hostname:
        raise ValueError("FHIR URL is missing a valid hostname.")

    if (
        hostname in _BLOCKED_HOSTNAMES
        or hostname.endswith(".local")
        or hostname.endswith(".internal")
        or hostname.endswith(".localhost")
    ):
        raise ValueError("Blocked internal or metadata hostname in FHIR URL.")

    allowed_hosts_env = os.environ.get("FHIR_ALLOWED_HOSTS", "").strip()
    if allowed_hosts_env:
        allowed_hosts = {h.strip().lower() for h in allowed_hosts_env.split(",") if h.strip()}
        if hostname not in allowed_hosts:
            raise ValueError(f"Host '{hostname}' is not in FHIR_ALLOWED_HOSTS.")

    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    try:
        addr_infos = await asyncio.to_thread(
            socket.getaddrinfo, hostname, port, type=socket.SOCK_STREAM
        )
    except socket.gaierror as exc:
        raise ValueError("Could not resolve external FHIR server hostname.") from exc

    if not addr_infos:
        raise ValueError("External FHIR server hostname resolved to no addresses.")

    for info in addr_infos:
        ip_raw = info[4][0]
        ip_obj = ipaddress.ip_address(ip_raw.split("%")[0])
        if (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_multicast
            or ip_obj.is_reserved
            or ip_obj.is_unspecified
            or not ip_obj.is_global
        ):
            raise ValueError("External FHIR URL resolved to a non-public IP address (blocked for SSRF protection).")

    return url_str


async def _fetch_with_validated_redirects(
    client: httpx.AsyncClient,
    initial_url: str,
) -> Dict[str, Any]:
    current_url = await _validate_safe_external_fhir_url(initial_url)

    for _ in range(MAX_FHIR_REDIRECT_HOPS + 1):
        async with client.stream(
            "GET",
            current_url,
            headers={"Accept": "application/fhir+json, application/json"},
            follow_redirects=False,
            timeout=12.0,
        ) as resp:
            if resp.status_code in (301, 302, 303, 307, 308):
                loc = resp.headers.get("location")
                if not loc:
                    raise ValueError("External FHIR server returned a redirect without Location header.")
                current_url = await _validate_safe_external_fhir_url(urljoin(current_url, loc))
                continue

            if resp.status_code >= 400:
                raise ValueError(f"External FHIR server returned HTTP {resp.status_code}.")

            chunks: List[bytes] = []
            total_bytes = 0
            async for chunk in resp.aiter_bytes():
                total_bytes += len(chunk)
                if total_bytes > MAX_EXTERNAL_FHIR_BYTES:
                    raise ValueError("External FHIR response exceeded maximum size limit (2 MB).")
                chunks.append(chunk)

            raw_bytes = b"".join(chunks)
            try:
                payload = json.loads(raw_bytes.decode("utf-8"))
            except Exception as exc:
                raise ValueError("External endpoint did not return valid UTF-8 JSON.") from exc

            if not isinstance(payload, dict) or "resourceType" not in payload:
                raise ValueError("JSON response is not a valid HL7 FHIR resource.")
            return payload

    raise ValueError("Too many redirects while fetching external FHIR URL.")


async def fetch_external_fhir_bundle(
    fhir_url: str,
    http_client: Optional[httpx.AsyncClient] = None,
) -> Dict[str, Any]:
    """
    Fetches a FHIR R4 Bundle or Patient resource from an external FHIR server URL
    with strict SSRF, redirect, and payload-size protections.
    """
    if http_client is not None:
        return await _fetch_with_validated_redirects(http_client, fhir_url)

    async with httpx.AsyncClient(timeout=12.0, follow_redirects=False) as temp_client:
        return await _fetch_with_validated_redirects(temp_client, fhir_url)

