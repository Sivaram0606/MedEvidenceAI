"""
Realistic HL7 FHIR R4 Patient Bundles for Point-of-Care Clinical Decision Support.
Includes 4 complex clinical cases with Patient, Encounter, Condition, Observation,
MedicationStatement, and AllergyIntolerance resources using standard SNOMED-CT,
LOINC, ICD-10, and RxNorm coding systems.
"""

from typing import Dict, Any, List

SAMPLE_FHIR_CASES: Dict[str, Dict[str, Any]] = {
    "patient-cardio-ckd": {
        "case_id": "patient-cardio-ckd",
        "title": "64M • HFrEF (LVEF 32%), Stage 3b CKD (eGFR 38) & T2DM",
        "specialty": "Cardiology / Nephrology Research",
        "default_question": (
            "What do recent peer-reviewed trials and society guidelines report on cardiovascular and renal "
            "outcomes for SGLT2 inhibitors, ARNI, and nonsteroidal MRAs in cohorts with HFrEF (LVEF <=40%), "
            "Stage 3b CKD (eGFR 30-45), and borderline potassium?"
        ),
        "suggested_questions": [
            "Compare DAPA-HF, EMPEROR-Reduced, and PIONEER-HF subgroup outcomes for eGFR <45 mL/min/1.73m².",
            "What does published literature report on hyperkalemia incidence when combining SGLT2i with MRA/Finerenone in CKD?",
            "What pharmacokinetic washout data and angioedema incidence are reported in ACEi-to-ARNI transition trials?"
        ],
        "fhir_bundle": {
            "resourceType": "Bundle",
            "id": "bundle-cardio-ckd-001",
            "type": "collection",
            "timestamp": "2026-11-05T08:30:00Z",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Patient",
                        "id": "pat-001",
                        "identifier": [{"system": "http://hospital.smarthealthit.org", "value": "MRN-849201"}],
                        "name": [{"use": "official", "family": "Vance", "given": ["Robert", "Arthur"]}],
                        "gender": "male",
                        "birthDate": "1962-03-14"
                    }
                },
                {
                    "resource": {
                        "resourceType": "Encounter",
                        "id": "enc-001",
                        "status": "in-progress",
                        "class": {"code": "IMP", "display": "Inpatient Encounter"},
                        "type": [{"text": "Admission for Progressive Dyspnea, Orthopnea, and Bilateral Lower Extremity Edema"}],
                        "reasonCode": [{"text": "Acute on chronic systolic heart failure exacerbation (NYHA Class III)"}]
                    }
                },
                {
                    "resource": {
                        "resourceType": "Condition",
                        "id": "cond-101",
                        "clinicalStatus": {"coding": [{"code": "active"}]},
                        "verificationStatus": {"coding": [{"code": "confirmed"}]},
                        "code": {
                            "coding": [
                                {"system": "http://snomed.info/sct", "code": "441481004", "display": "Chronic systolic heart failure (HFrEF)"},
                                {"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": "I50.23", "display": "Acute on chronic systolic (congestive) heart failure"}
                            ],
                            "text": "Heart Failure with Reduced Ejection Fraction (HFrEF, LVEF 32%, NYHA Class III)"
                        },
                        "onsetDateTime": "2023-06-10"
                    }
                },
                {
                    "resource": {
                        "resourceType": "Condition",
                        "id": "cond-102",
                        "clinicalStatus": {"coding": [{"code": "active"}]},
                        "verificationStatus": {"coding": [{"code": "confirmed"}]},
                        "code": {
                            "coding": [
                                {"system": "http://snomed.info/sct", "code": "433144002", "display": "Chronic kidney disease stage 3B"},
                                {"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": "N18.32", "display": "Chronic kidney disease, stage 3b"}
                            ],
                            "text": "Chronic Kidney Disease Stage 3b with moderate albuminuria (UACR 240 mg/g)"
                        },
                        "onsetDateTime": "2024-01-15"
                    }
                },
                {
                    "resource": {
                        "resourceType": "Condition",
                        "id": "cond-103",
                        "clinicalStatus": {"coding": [{"code": "active"}]},
                        "verificationStatus": {"coding": [{"code": "confirmed"}]},
                        "code": {
                            "coding": [
                                {"system": "http://snomed.info/sct", "code": "44054006", "display": "Diabetes mellitus type 2"},
                                {"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": "E11.22", "display": "Type 2 diabetes mellitus with diabetic chronic kidney disease"}
                            ],
                            "text": "Type 2 Diabetes Mellitus with Diabetic Kidney Disease"
                        },
                        "onsetDateTime": "2018-09-20"
                    }
                },
                {
                    "resource": {
                        "resourceType": "Condition",
                        "id": "cond-104",
                        "clinicalStatus": {"coding": [{"code": "active"}]},
                        "verificationStatus": {"coding": [{"code": "confirmed"}]},
                        "code": {
                            "coding": [
                                {"system": "http://snomed.info/sct", "code": "38341003", "display": "Essential hypertension"}
                            ],
                            "text": "Essential Hypertension"
                        },
                        "onsetDateTime": "2015-04-01"
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": "obs-lvef",
                        "status": "final",
                        "code": {"coding": [{"system": "http://loinc.org", "code": "10230-1", "display": "Left ventricular Ejection fraction"}], "text": "LVEF (Transthoracic Echocardiogram)"},
                        "valueQuantity": {"value": 32, "unit": "%"},
                        "referenceRange": [{"low": {"value": 50, "unit": "%"}, "high": {"value": 70, "unit": "%"}}],
                        "interpretation": [{"coding": [{"code": "L", "display": "Low"}]}]
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": "obs-ntprobnp",
                        "status": "final",
                        "code": {"coding": [{"system": "http://loinc.org", "code": "33762-6", "display": "NT-proBNP"}], "text": "NT-proBNP"},
                        "valueQuantity": {"value": 4280, "unit": "pg/mL"},
                        "referenceRange": [{"high": {"value": 300, "unit": "pg/mL"}}],
                        "interpretation": [{"coding": [{"code": "HH", "display": "Critical High"}]}]
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": "obs-egfr",
                        "status": "final",
                        "code": {"coding": [{"system": "http://loinc.org", "code": "98979-8", "display": "eGFR CKD-EPI"}], "text": "Estimated GFR (CKD-EPI)"},
                        "valueQuantity": {"value": 38, "unit": "mL/min/1.73m2"},
                        "referenceRange": [{"low": {"value": 60, "unit": "mL/min/1.73m2"}}],
                        "interpretation": [{"coding": [{"code": "L", "display": "Low"}]}]
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": "obs-cr",
                        "status": "final",
                        "code": {"coding": [{"system": "http://loinc.org", "code": "2160-0", "display": "Creatinine [Mass/volume] in Serum or Plasma"}], "text": "Serum Creatinine"},
                        "valueQuantity": {"value": 1.85, "unit": "mg/dL"},
                        "referenceRange": [{"low": {"value": 0.7, "unit": "mg/dL"}, "high": {"value": 1.3, "unit": "mg/dL"}}],
                        "interpretation": [{"coding": [{"code": "H", "display": "High"}]}]
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": "obs-potassium",
                        "status": "final",
                        "code": {"coding": [{"system": "http://loinc.org", "code": "2823-3", "display": "Potassium [Moles/volume] in Serum or Plasma"}], "text": "Serum Potassium"},
                        "valueQuantity": {"value": 4.9, "unit": "mEq/L"},
                        "referenceRange": [{"low": {"value": 3.5, "unit": "mEq/L"}, "high": {"value": 5.0, "unit": "mEq/L"}}],
                        "interpretation": [{"coding": [{"code": "N", "display": "Borderline High-Normal"}]}]
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": "obs-hba1c",
                        "status": "final",
                        "code": {"coding": [{"system": "http://loinc.org", "code": "4548-4", "display": "Hemoglobin A1c/Hemoglobin.total in Blood"}], "text": "HbA1c"},
                        "valueQuantity": {"value": 8.2, "unit": "%"},
                        "referenceRange": [{"high": {"value": 5.7, "unit": "%"}}],
                        "interpretation": [{"coding": [{"code": "H", "display": "High"}]}]
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": "obs-uacr",
                        "status": "final",
                        "code": {"coding": [{"system": "http://loinc.org", "code": "9318-7", "display": "Albumin/Creatinine [Mass Ratio] in Urine"}], "text": "Urine Albumin-to-Creatinine Ratio (UACR)"},
                        "valueQuantity": {"value": 240, "unit": "mg/g"},
                        "referenceRange": [{"high": {"value": 30, "unit": "mg/g"}}],
                        "interpretation": [{"coding": [{"code": "H", "display": "High"}]}]
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": "obs-bp",
                        "status": "final",
                        "code": {"coding": [{"system": "http://loinc.org", "code": "85354-9", "display": "Blood pressure panel"}], "text": "Blood Pressure"},
                        "valueString": "116/72 mmHg (HR 78 bpm, SpO2 94% on 2L NC)"
                    }
                },
                {
                    "resource": {
                        "resourceType": "MedicationStatement",
                        "id": "med-101",
                        "status": "active",
                        "medicationCodeableConcept": {
                            "coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "code": "314076", "display": "Lisinopril 10 MG Oral Tablet"}],
                            "text": "Lisinopril 10 mg PO daily"
                        }
                    }
                },
                {
                    "resource": {
                        "resourceType": "MedicationStatement",
                        "id": "med-102",
                        "status": "active",
                        "medicationCodeableConcept": {
                            "coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "code": "866924", "display": "Metoprolol Succinate 50 MG Extended Release Oral Tablet"}],
                            "text": "Metoprolol Succinate XL 50 mg PO daily"
                        }
                    }
                },
                {
                    "resource": {
                        "resourceType": "MedicationStatement",
                        "id": "med-103",
                        "status": "active",
                        "medicationCodeableConcept": {
                            "coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "code": "861007", "display": "Metformin hydrochloride 1000 MG Oral Tablet"}],
                            "text": "Metformin 1000 mg PO BID (Note: eGFR now 38 mL/min/1.73m2)"
                        }
                    }
                },
                {
                    "resource": {
                        "resourceType": "MedicationStatement",
                        "id": "med-104",
                        "status": "active",
                        "medicationCodeableConcept": {
                            "coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "code": "310429", "display": "Furosemide 40 MG Oral Tablet"}],
                            "text": "Furosemide 40 mg IV BID (inpatient diuresis)"
                        }
                    }
                },
                {
                    "resource": {
                        "resourceType": "AllergyIntolerance",
                        "id": "allergy-101",
                        "clinicalStatus": {"coding": [{"code": "active"}]},
                        "criticality": "low",
                        "code": {"text": "NSAIDs (Ibuprofen / Naproxen)"},
                        "reaction": [{"manifestation": [{"text": "Acute worsening of renal function and fluid retention"}]}]
                    }
                }
            ]
        }
    },
    "patient-sepsis-pneumonia": {
        "case_id": "patient-sepsis-pneumonia",
        "title": "71F • Severe CAP, Early Septic Shock & IgE Penicillin Allergy",
        "specialty": "Pulmonology / Critical Care / ID Research",
        "default_question": (
            "What do recent RCTs (including CAPE COD) and ATS/IDSA/Surviving Sepsis guidelines report on "
            "adjunctive corticosteroid outcomes and non-beta-lactam antimicrobial efficacy in ICU cohorts "
            "with severe hypoxemic CAP and IgE-mediated Penicillin allergy?"
        ),
        "suggested_questions": [
            "Summarize the CAPE COD trial (NEJM 2023) inclusion criteria, hydrocortisone protocol, and 28-day mortality outcomes.",
            "What does published literature report on beta-lactam cross-reactivity vs fluoroquinolone/aztreonam outcomes in severe IgE allergy?",
            "How do recent sepsis studies evaluate serial procalcitonin and lactate kinetics for antimicrobial stewardship?"
        ],
        "fhir_bundle": {
            "resourceType": "Bundle",
            "id": "bundle-sepsis-cap-002",
            "type": "collection",
            "timestamp": "2026-11-05T09:15:00Z",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Patient",
                        "id": "pat-002",
                        "identifier": [{"system": "http://hospital.smarthealthit.org", "value": "MRN-512098"}],
                        "name": [{"use": "official", "family": "Chen", "given": ["Eleanor", "Mei"]}],
                        "gender": "female",
                        "birthDate": "1955-07-22"
                    }
                },
                {
                    "resource": {
                        "resourceType": "Encounter",
                        "id": "enc-002",
                        "status": "in-progress",
                        "class": {"code": "EMER", "display": "ICU / Emergency Admission"},
                        "type": [{"text": "ICU Admission for Hypoxemic Respiratory Failure and Septic Shock secondary to Right Lower Lobe Pneumonia"}],
                        "reasonCode": [{"text": "Severe Community-Acquired Pneumonia (PSI Class V) with Septic Shock"}]
                    }
                },
                {
                    "resource": {
                        "resourceType": "Condition",
                        "id": "cond-201",
                        "clinicalStatus": {"coding": [{"code": "active"}]},
                        "verificationStatus": {"coding": [{"code": "confirmed"}]},
                        "code": {
                            "coding": [
                                {"system": "http://snomed.info/sct", "code": "385093006", "display": "Community acquired pneumonia"},
                                {"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": "J18.9", "display": "Pneumonia, unspecified organism"}
                            ],
                            "text": "Severe Community-Acquired Pneumonia (Multilobar RLL/RML consolidation on Chest CT)"
                        },
                        "onsetDateTime": "2026-11-03"
                    }
                },
                {
                    "resource": {
                        "resourceType": "Condition",
                        "id": "cond-202",
                        "clinicalStatus": {"coding": [{"code": "active"}]},
                        "verificationStatus": {"coding": [{"code": "confirmed"}]},
                        "code": {
                            "coding": [
                                {"system": "http://snomed.info/sct", "code": "76571007", "display": "Septic shock"},
                                {"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": "R65.21", "display": "Severe sepsis with septic shock"}
                            ],
                            "text": "Early Septic Shock (Hypotension requiring vasopressor evaluation, hyperlactatemia)"
                        },
                        "onsetDateTime": "2026-11-05"
                    }
                },
                {
                    "resource": {
                        "resourceType": "Condition",
                        "id": "cond-203",
                        "clinicalStatus": {"coding": [{"code": "active"}]},
                        "verificationStatus": {"coding": [{"code": "confirmed"}]},
                        "code": {
                            "coding": [
                                {"system": "http://snomed.info/sct", "code": "13645005", "display": "Chronic obstructive lung disease"}
                            ],
                            "text": "Severe COPD (GOLD Stage 3, baseline FEV1 44% predicted)"
                        },
                        "onsetDateTime": "2019-11-01"
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": "obs-lactate",
                        "status": "final",
                        "code": {"coding": [{"system": "http://loinc.org", "code": "2524-7", "display": "Lactate [Moles/volume] in Serum or Plasma"}], "text": "Serum Lactate"},
                        "valueQuantity": {"value": 3.4, "unit": "mmol/L"},
                        "referenceRange": [{"high": {"value": 2.0, "unit": "mmol/L"}}],
                        "interpretation": [{"coding": [{"code": "HH", "display": "Critical High"}]}]
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": "obs-pct",
                        "status": "final",
                        "code": {"coding": [{"system": "http://loinc.org", "code": "33959-8", "display": "Procalcitonin [Mass/volume] in Serum or Plasma"}], "text": "Procalcitonin"},
                        "valueQuantity": {"value": 4.2, "unit": "ng/mL"},
                        "referenceRange": [{"high": {"value": 0.25, "unit": "ng/mL"}}],
                        "interpretation": [{"coding": [{"code": "HH", "display": "Critical High"}]}]
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": "obs-wbc",
                        "status": "final",
                        "code": {"coding": [{"system": "http://loinc.org", "code": "6690-2", "display": "Leukocytes [#/volume] in Blood"}], "text": "WBC Count"},
                        "valueQuantity": {"value": 18.6, "unit": "10*3/uL"},
                        "referenceRange": [{"low": {"value": 4.5, "unit": "10*3/uL"}, "high": {"value": 11.0, "unit": "10*3/uL"}}],
                        "interpretation": [{"coding": [{"code": "H", "display": "High"}]}]
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": "obs-pao2fio2",
                        "status": "final",
                        "code": {"coding": [{"system": "http://loinc.org", "code": "50984-4", "display": "PaO2/FiO2 ratio"}], "text": "PaO2/FiO2 Ratio (on High-Flow Nasal Cannula FiO2 0.60)"},
                        "valueQuantity": {"value": 165, "unit": "mmHg"},
                        "referenceRange": [{"low": {"value": 300, "unit": "mmHg"}}],
                        "interpretation": [{"coding": [{"code": "LL", "display": "Critical Low"}]}]
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": "obs-vitals-2",
                        "status": "final",
                        "code": {"coding": [{"system": "http://loinc.org", "code": "85354-9", "display": "Vital Signs"}], "text": "Vital Signs"},
                        "valueString": "BP 88/54 mmHg (MAP 65 mmHg), HR 114 bpm, RR 28/min, Temp 38.9 °C, SpO2 91% on HFNC 50L/min FiO2 60%"
                    }
                },
                {
                    "resource": {
                        "resourceType": "MedicationStatement",
                        "id": "med-201",
                        "status": "active",
                        "medicationCodeableConcept": {"text": "Tiotropium / Olodaterol inhaler 2 puffs daily (Home medication)"}
                    }
                },
                {
                    "resource": {
                        "resourceType": "AllergyIntolerance",
                        "id": "allergy-201",
                        "clinicalStatus": {"coding": [{"code": "active"}]},
                        "criticality": "high",
                        "code": {"text": "Penicillins (Amoxicillin)"},
                        "reaction": [{"manifestation": [{"text": "Anaphylaxis, laryngeal edema, and hypotension requiring epinephrine"}]}]
                    }
                }
            ]
        }
    },
    "patient-afib-gi-bleed": {
        "case_id": "patient-afib-gi-bleed",
        "title": "78F • Non-Valvular AFib (CHA₂DS₂-VASc 6), Prior TIA & Recent Peptic Ulcer Bleed",
        "specialty": "Cardiology / GI / Hematology Research",
        "default_question": (
            "What do recent meta-analyses and ACC/AHA guidelines report on stroke vs recurrent GI bleeding "
            "outcomes when resuming DOACs (Apixaban vs Rivaroxaban vs Dabigatran) after endoscopic hemostasis "
            "of peptic ulcer bleeding in high-risk AFib cohorts?"
        ),
        "suggested_questions": [
            "Compare published recurrent GI bleeding hazard ratios across DOACs (Apixaban, Dabigatran, Rivaroxaban) in elderly CKD cohorts.",
            "What does published evidence show regarding timing of anticoagulation resumption (7-14 days vs delayed) after ulcer hemostasis?",
            "What clinical trial data compare Left Atrial Appendage Occlusion (LAAO) vs DOAC continuation after GI hemorrhage?"
        ],
        "fhir_bundle": {
            "resourceType": "Bundle",
            "id": "bundle-afib-gib-003",
            "type": "collection",
            "timestamp": "2026-11-05T10:00:00Z",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Patient",
                        "id": "pat-003",
                        "identifier": [{"system": "http://hospital.smarthealthit.org", "value": "MRN-391044"}],
                        "name": [{"use": "official", "family": "Lindqvist", "given": ["Ingrid"]}],
                        "gender": "female",
                        "birthDate": "1948-02-11"
                    }
                },
                {
                    "resource": {
                        "resourceType": "Condition",
                        "id": "cond-301",
                        "clinicalStatus": {"coding": [{"code": "active"}]},
                        "verificationStatus": {"coding": [{"code": "confirmed"}]},
                        "code": {
                            "coding": [{"system": "http://snomed.info/sct", "code": "49436004", "display": "Atrial fibrillation"}],
                            "text": "Permanent Non-Valvular Atrial Fibrillation (CHA2DS2-VASc = 6, HAS-BLED = 3)"
                        }
                    }
                },
                {
                    "resource": {
                        "resourceType": "Condition",
                        "id": "cond-302",
                        "clinicalStatus": {"coding": [{"code": "active"}]},
                        "verificationStatus": {"coding": [{"code": "confirmed"}]},
                        "code": {
                            "coding": [{"system": "http://snomed.info/sct", "code": "266366005", "display": "Bleeding duodenal ulcer"}],
                            "text": "Recent Upper GI Hemorrhage from Forrest IIa Duodenal Ulcer (Successful endoscopic clip + epinephrine 14 days ago; H. pylori positive)"
                        }
                    }
                },
                {
                    "resource": {
                        "resourceType": "Condition",
                        "id": "cond-303",
                        "clinicalStatus": {"coding": [{"code": "active"}]},
                        "verificationStatus": {"coding": [{"code": "confirmed"}]},
                        "code": {
                            "coding": [{"system": "http://snomed.info/sct", "code": "266257000", "display": "Transient ischemic attack"}],
                            "text": "History of Cardioembolic Transient Ischemic Attack (TIA, 2024)"
                        }
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": "obs-hgb-3",
                        "status": "final",
                        "code": {"coding": [{"system": "http://loinc.org", "code": "718-7", "display": "Hemoglobin"}], "text": "Hemoglobin (stable for 10 days)"},
                        "valueQuantity": {"value": 10.4, "unit": "g/dL"},
                        "referenceRange": [{"low": {"value": 12.0, "unit": "g/dL"}, "high": {"value": 15.5, "unit": "g/dL"}}],
                        "interpretation": [{"coding": [{"code": "L", "display": "Low"}]}]
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": "obs-crcl-3",
                        "status": "final",
                        "code": {"coding": [{"system": "http://loinc.org", "code": "35591-7", "display": "Cockcroft-Gault CrCl"}], "text": "Creatinine Clearance (Cockcroft-Gault, Weight 58 kg, Cr 1.18 mg/dL)"},
                        "valueQuantity": {"value": 44, "unit": "mL/min"},
                        "referenceRange": [{"low": {"value": 60, "unit": "mL/min"}}],
                        "interpretation": [{"coding": [{"code": "L", "display": "Low"}]}]
                    }
                },
                {
                    "resource": {
                        "resourceType": "MedicationStatement",
                        "id": "med-301",
                        "status": "on-hold",
                        "medicationCodeableConcept": {"text": "Rivaroxaban 20 mg PO daily (Held at admission 14 days ago due to GI bleed)"}
                    }
                },
                {
                    "resource": {
                        "resourceType": "MedicationStatement",
                        "id": "med-302",
                        "status": "active",
                        "medicationCodeableConcept": {"text": "Pantoprazole 40 mg PO BID + Bismuth quadruple H. pylori eradication therapy"}
                    }
                },
                {
                    "resource": {
                        "resourceType": "MedicationStatement",
                        "id": "med-303",
                        "status": "active",
                        "medicationCodeableConcept": {"text": "Aspirin 81 mg PO daily (Patient had been taking OTC aspirin concurrently without clear indication)"}
                    }
                }
            ]
        }
    },
    "patient-lupus-nephritis": {
        "case_id": "patient-lupus-nephritis",
        "title": "34F • Active Class IV Lupus Nephritis, Nephrotic Proteinuria & Hypocomplementemia",
        "specialty": "Rheumatology / Nephrology Research",
        "default_question": (
            "What do landmark RCTs (BLISS-LN, AURORA-1) and the 2024 KDIGO Lupus Nephritis Guidelines report "
            "on complete renal response rates and safety comparing standard MMF/Cyclophosphamide vs multi-target "
            "induction with Belimumab or Voclosporin in Class IV cohorts?"
        ),
        "suggested_questions": [
            "Compare primary renal response endpoints and eGFR trajectories in BLISS-LN (Belimumab) vs AURORA-1 (Voclosporin).",
            "What comparative outcomes are reported for reduced-dose vs standard-dose glucocorticoid tapers in KDIGO 2024?",
            "What published evidence supports adjunctive Hydroxychloroquine, RAAS blockade, and SGLT2i in Lupus Nephritis?"
        ],
        "fhir_bundle": {
            "resourceType": "Bundle",
            "id": "bundle-lupus-nephritis-004",
            "type": "collection",
            "timestamp": "2026-11-05T11:00:00Z",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Patient",
                        "id": "pat-004",
                        "identifier": [{"system": "http://hospital.smarthealthit.org", "value": "MRN-774129"}],
                        "name": [{"use": "official", "family": "okafor", "given": ["Amara"]}],
                        "gender": "female",
                        "birthDate": "1992-08-19"
                    }
                },
                {
                    "resource": {
                        "resourceType": "Encounter",
                        "id": "enc-004",
                        "status": "in-progress",
                        "class": {"code": "AMB", "display": "Specialty Clinic Consultation"},
                        "type": [{"text": "Urgent Rheumatology-Nephrology Multidisciplinary Consultation following Renal Biopsy"}],
                        "reasonCode": [{"text": "Diffuse Proliferative Lupus Nephritis (ISN/RPS Class IV)"}]
                    }
                },
                {
                    "resource": {
                        "resourceType": "Condition",
                        "id": "cond-401",
                        "clinicalStatus": {"coding": [{"code": "active"}]},
                        "verificationStatus": {"coding": [{"code": "confirmed"}]},
                        "code": {
                            "coding": [
                                {"system": "http://snomed.info/sct", "code": "55464009", "display": "Systemic lupus erythematosus"},
                                {"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": "M32.14", "display": "Glomerular disease in systemic lupus erythematosus"}
                            ],
                            "text": "Biopsy-Proven ISN/RPS Class IV Diffuse Proliferative Lupus Nephritis (Activity Index 11/24, Chronicity Index 2/12)"
                        }
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": "obs-upcr-4",
                        "status": "final",
                        "code": {"coding": [{"system": "http://loinc.org", "code": "14959-1", "display": "Urine Protein/Creatinine Ratio"}], "text": "Urine Protein-to-Creatinine Ratio (UPCR)"},
                        "valueQuantity": {"value": 3.6, "unit": "g/g"},
                        "referenceRange": [{"high": {"value": 0.2, "unit": "g/g"}}],
                        "interpretation": [{"coding": [{"code": "HH", "display": "Critical High"}]}]
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": "obs-dsdna-4",
                        "status": "final",
                        "code": {"coding": [{"system": "http://loinc.org", "code": "5130-0", "display": "DNA double strand Ab"}], "text": "Anti-dsDNA Antibody Titer"},
                        "valueQuantity": {"value": 340, "unit": "IU/mL"},
                        "referenceRange": [{"high": {"value": 30, "unit": "IU/mL"}}],
                        "interpretation": [{"coding": [{"code": "HH", "display": "Critical High"}]}]
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": "obs-c3-4",
                        "status": "final",
                        "code": {"coding": [{"system": "http://loinc.org", "code": "4485-9", "display": "Complement C3"}], "text": "Serum Complement C3"},
                        "valueQuantity": {"value": 42, "unit": "mg/dL"},
                        "referenceRange": [{"low": {"value": 90, "unit": "mg/dL"}, "high": {"value": 180, "unit": "mg/dL"}}],
                        "interpretation": [{"coding": [{"code": "LL", "display": "Critical Low"}]}]
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": "obs-egfr-4",
                        "status": "final",
                        "code": {"coding": [{"system": "http://loinc.org", "code": "98979-8", "display": "eGFR CKD-EPI"}], "text": "Estimated GFR (CKD-EPI)"},
                        "valueQuantity": {"value": 68, "unit": "mL/min/1.73m2"},
                        "referenceRange": [{"low": {"value": 90, "unit": "mL/min/1.73m2"}}],
                        "interpretation": [{"coding": [{"code": "L", "display": "Low"}]}]
                    }
                },
                {
                    "resource": {
                        "resourceType": "MedicationStatement",
                        "id": "med-401",
                        "status": "active",
                        "medicationCodeableConcept": {"text": "Hydroxychloroquine 200 mg PO daily (Weight 62 kg)"}
                    }
                },
                {
                    "resource": {
                        "resourceType": "MedicationStatement",
                        "id": "med-402",
                        "status": "active",
                        "medicationCodeableConcept": {"text": "Losartan 50 mg PO daily"}
                    }
                }
            ]
        }
    }
}

