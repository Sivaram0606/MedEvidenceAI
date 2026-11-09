/**
 * Frontend Application Logic for MedEvidence AI:
 * Point-of-Care Literature Synthesis, Differential Diagnosis & Precision Treatment Agentic System.
 */

let allCases = [];
let activeCaseId = null;
let activeFhirBundle = null;
let activeRetrievedArticles = [];
let activeJournalFilter = "ALL";
let whitelistedJournals = [];

document.addEventListener("DOMContentLoaded", async () => {
  setupTabs();
  setupModals();
  await loadJournalsWhitelist();
  await loadSampleCases();

  document.getElementById("runSynthesisBtn").addEventListener("click", () => {
    runSynthesisPipeline();
  });
});

function setupTabs() {
  const tabs = document.querySelectorAll(".chart-tab");
  tabs.forEach((btn) => {
    btn.addEventListener("click", () => {
      tabs.forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-pane").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      const targetId = btn.getAttribute("data-tab");
      document.getElementById(targetId).classList.add("active");
    });
  });
}

function setupModals() {
  const fhirModal = document.getElementById("fhirModal");
  const journalsModal = document.getElementById("journalsModal");

  document.getElementById("openFhirModalBtn").addEventListener("click", () => {
    fhirModal.classList.remove("hidden");
  });
  document.getElementById("closeFhirModalBtn").addEventListener("click", () => {
    fhirModal.classList.add("hidden");
  });

  document.getElementById("openJournalsModalBtn").addEventListener("click", () => {
    journalsModal.classList.remove("hidden");
  });
  document.getElementById("closeJournalsModalBtn").addEventListener("click", () => {
    journalsModal.classList.add("hidden");
  });

  // File input reader for custom FHIR JSON
  document.getElementById("fhirFileInput").addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (evt) => {
      document.getElementById("customFhirJsonTextarea").value = evt.target.result;
    };
    reader.readAsText(file);
  });

  // Fetch from external FHIR server URL
  document.getElementById("fetchFhirUrlBtn").addEventListener("click", async () => {
    const url = document.getElementById("fhirUrlInput").value.trim();
    if (!url) return;
    try {
      const resp = await fetch("/api/parse-fhir", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fhir_url: url }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || "Failed to fetch FHIR URL");
      document.getElementById("customFhirJsonTextarea").value = JSON.stringify(data.fhir_bundle, null, 2);
    } catch (err) {
      alert("FHIR URL Fetch Error: " + err.message);
    }
  });

  // Parse and load custom FHIR JSON into the workstation
  document.getElementById("loadCustomFhirBtn").addEventListener("click", async () => {
    const rawText = document.getElementById("customFhirJsonTextarea").value.trim();
    if (!rawText) return;
    try {
      const bundleObj = JSON.parse(rawText);
      const resp = await fetch("/api/parse-fhir", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fhir_bundle: bundleObj }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || "Failed to parse FHIR Bundle");

      activeCaseId = null;
      activeFhirBundle = data.fhir_bundle;
      renderPatientChart(data.parsed_fhir, data.fhir_bundle);
      fhirModal.classList.add("hidden");
      document.getElementById("physicianQuestionInput").value =
        "Based on this patient's FHIR R4 clinical data, what is the evidence-based differential diagnosis and recommended treatment plan from reputed medical journals?";
      await runSynthesisPipeline();
    } catch (err) {
      alert("Invalid FHIR JSON: " + err.message);
    }
  });
}

async function loadJournalsWhitelist() {
  try {
    const resp = await fetch("/api/journals");
    const data = await resp.json();
    whitelistedJournals = data.journals || [];
    document.getElementById("journalCountBadge").textContent =
      `${whitelistedJournals.length} Reputed Journals`;

    const container = document.getElementById("journalsTableContainer");
    container.innerHTML = whitelistedJournals
      .map(
        (j) => `
        <div class="journal-whitelist-item">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
            <strong style="color:#fff;font-size:13px;">${escapeHtml(j.name)}</strong>
            <span class="badge-pill badge-teal">${escapeHtml(j.short)}</span>
          </div>
          <div style="font-size:11.5px;color:#94a3b8;">
            Specialty: <span style="color:#cbd5e1;">${escapeHtml(j.category)}</span> &bull;
            PubMed Filter: <code style="color:#38bdf8;">"${escapeHtml(j.abbrev)}"[Journal]</code>
          </div>
        </div>
      `
      )
      .join("");
  } catch (err) {
    console.error("Failed to load journals whitelist:", err);
  }
}

async function loadSampleCases() {
  try {
    const resp = await fetch("/api/cases");
    const data = await resp.json();
    allCases = data.cases || [];

    const selectEl = document.getElementById("caseSelect");
    selectEl.innerHTML = allCases
      .map(
        (c) =>
          `<option value="${escapeHtml(c.case_id)}">${escapeHtml(c.title)} (${escapeHtml(c.specialty)})</option>`
      )
      .join("");

    selectEl.addEventListener("change", (e) => {
      selectCase(e.target.value);
    });

    if (allCases.length > 0) {
      await selectCase(allCases[0].case_id);
    }
  } catch (err) {
    console.error("Failed to load sample FHIR cases:", err);
  }
}

async function selectCase(caseId) {
  const found = allCases.find((c) => c.case_id === caseId);
  if (!found) return;

  activeCaseId = found.case_id;
  activeFhirBundle = found.fhir_bundle;

  renderPatientChart(found.parsed_fhir, found.fhir_bundle);

  // Populate suggested clinical questions
  const suggestedWrap = document.getElementById("suggestedQuestionsWrap");
  suggestedWrap.innerHTML = (found.suggested_questions || [])
    .map(
      (q) =>
        `<button class="suggested-chip" data-question="${escapeHtml(q)}">${escapeHtml(q)}</button>`
    )
    .join("");

  suggestedWrap.querySelectorAll(".suggested-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.getElementById("physicianQuestionInput").value = btn.getAttribute("data-question");
      runSynthesisPipeline();
    });
  });

  document.getElementById("physicianQuestionInput").value = found.default_question;
  await runSynthesisPipeline();
}

function renderPatientChart(parsed, rawBundle) {
  const p = parsed.patient || {};
  const enc = parsed.encounter || {};

  document.getElementById("patientBanner").innerHTML = `
    <div class="patient-name-row">
      <span class="patient-name">${escapeHtml(p.name || "Patient")}</span>
      <span class="patient-mrn">${escapeHtml(p.mrn || "")}</span>
    </div>
    <div class="patient-demographics">
      ${p.age ? `${p.age} yrs` : ""} &bull; ${escapeHtml(p.gender || "")} &bull; DOB: ${escapeHtml(p.birthDate || "N/A")}
    </div>
    <div class="patient-encounter-box">
      <strong>${escapeHtml(enc.class || "Encounter")}:</strong> ${escapeHtml(enc.reason || enc.type || "")}
    </div>
  `;

  // Render automated FHIR safety alerts
  const alertsEl = document.getElementById("safetyAlertsContainer");
  const alerts = parsed.safety_alerts || [];
  if (alerts.length === 0) {
    alertsEl.style.display = "none";
  } else {
    alertsEl.style.display = "flex";
    alertsEl.innerHTML = alerts
      .map(
        (a) => `
        <div class="safety-alert-item ${escapeHtml(a.severity)}">
          <div class="safety-alert-title">
            <span>&#9888; ${escapeHtml(a.title)}</span>
          </div>
          <div>${escapeHtml(a.detail)}</div>
        </div>
      `
      )
      .join("");
  }

  // Render Labs & Vitals
  const obsList = parsed.observations || [];
  document.getElementById("tab-labs").innerHTML = obsList
    .map(
      (o) => `
      <div class="fhir-item-card">
        <div class="fhir-item-top">
          <span class="fhir-item-title">${escapeHtml(o.name)}</span>
          ${o.loinc ? `<span class="fhir-code-tag">LOINC ${escapeHtml(o.loinc)}</span>` : ""}
        </div>
        <div class="obs-value-row">
          <div>
            <span class="obs-value">${escapeHtml(o.value)}</span>
            ${o.reference_range ? `<div class="obs-ref">Ref: ${escapeHtml(o.reference_range)}</div>` : ""}
          </div>
          <span class="flag-badge flag-${escapeHtml(o.flag || "N")}">${escapeHtml(o.flag_display || "Normal")}</span>
        </div>
      </div>
    `
    )
    .join("");

  // Render Conditions
  const condList = parsed.conditions || [];
  document.getElementById("tab-conditions").innerHTML = condList
    .map(
      (c) => `
      <div class="fhir-item-card">
        <div class="fhir-item-top">
          <span class="fhir-item-title">${escapeHtml(c.display)}</span>
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px;">
          ${c.icd10_code ? `<span class="fhir-code-tag">ICD-10: ${escapeHtml(c.icd10_code)}</span>` : ""}
          ${c.snomed_code ? `<span class="fhir-code-tag">SNOMED: ${escapeHtml(c.snomed_code)}</span>` : ""}
          <span class="fhir-code-tag">Onset: ${escapeHtml(c.onset)}</span>
        </div>
      </div>
    `
    )
    .join("");

  // Render Medications & Allergies
  const meds = parsed.medications || [];
  const allergies = parsed.allergies || [];
  document.getElementById("tab-meds").innerHTML = `
    <div style="font-size:11.5px;font-weight:700;color:#94a3b8;text-transform:uppercase;">Allergies &amp; Intolerances (${allergies.length})</div>
    ${
      allergies.length
        ? allergies
            .map(
              (al) => `
          <div class="fhir-item-card" style="border-color:rgba(244,63,94,0.4);">
            <div class="fhir-item-top">
              <span class="fhir-item-title" style="color:#fda4af;">${escapeHtml(al.substance)}</span>
              <span class="flag-badge flag-HH">${escapeHtml(al.criticality)}</span>
            </div>
            <div style="font-size:12px;color:#cbd5e1;">Reaction: ${escapeHtml(al.reaction)}</div>
          </div>
        `
            )
            .join("")
        : `<div class="fhir-item-card">No Known Drug Allergies</div>`
    }
    <div style="font-size:11.5px;font-weight:700;color:#94a3b8;text-transform:uppercase;margin-top:8px;">Active &amp; Recent Medications (${meds.length})</div>
    ${meds
      .map(
        (m) => `
        <div class="fhir-item-card">
          <div class="fhir-item-top">
            <span class="fhir-item-title">${escapeHtml(m.name)}</span>
            <span class="fhir-code-tag">${escapeHtml(m.status.toUpperCase())}</span>
          </div>
          ${m.rxnorm ? `<div style="margin-top:4px;"><span class="fhir-code-tag">RxNorm: ${escapeHtml(m.rxnorm)}</span></div>` : ""}
        </div>
      `
      )
      .join("")}
  `;

  // Raw FHIR Bundle JSON
  document.getElementById("rawFhirPre").textContent = JSON.stringify(rawBundle, null, 2);
}

let activeClinicalTrials = [];

async function runSynthesisPipeline() {
  const question = document.getElementById("physicianQuestionInput").value.trim();
  if (!question) return;

  const runBtn = document.getElementById("runSynthesisBtn");
  const runBtnText = document.getElementById("runBtnText");
  runBtn.disabled = true;
  runBtnText.textContent = "Querying Open APIs & Flash 3.8...";

  try {
    const resp = await fetch("/api/synthesize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        case_id: activeCaseId,
        fhir_bundle: activeFhirBundle,
        physician_question: question,
      }),
    });

    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "Synthesis error");

    document.getElementById("engineBadge").textContent = data.engine_mode || "Gemini Flash 3.8 Copilot";
    document.getElementById("pipelineDurationBadge").textContent =
      `Completed in ${data.total_duration_ms} ms`;

    // Render Open-Source Research API live status badges
    const statusMap = data.api_status_map || {};
    const statusEl = document.getElementById("openApiStatusBadges");
    if (statusEl) {
      statusEl.innerHTML = Object.entries(statusMap)
        .map(
          ([apiName, st]) =>
            `<span class="badge-pill badge-teal" title="${escapeHtml(st)}">&#10003; ${escapeHtml(apiName)}</span>`
        )
        .join("");
    }

    renderAgentTrace(data.agent_trace || []);
    activeRetrievedArticles = data.retrieved_articles || [];
    activeClinicalTrials = data.clinical_trials || [];
    activeJournalFilter = "ALL";
    renderJournalEvidencePanel(activeRetrievedArticles);
    renderClinicalSynthesis(data.synthesis || {});
  } catch (err) {
    console.error("Synthesis Pipeline Error:", err);
    alert("Error running research synthesis pipeline: " + err.message);
  } finally {
    runBtn.disabled = false;
    runBtnText.textContent = "Synthesize Research Evidence";
  }
}

function renderAgentTrace(trace) {
  const grid = document.getElementById("agentTraceGrid");
  grid.innerHTML = trace
    .map(
      (step) => `
      <div class="agent-step-card">
        <div class="agent-step-top">
          <span>${escapeHtml(step.agent_name)}</span>
          <span class="agent-step-time">${step.duration_ms}ms</span>
        </div>
        <div class="agent-step-details">${escapeHtml(step.details)}</div>
      </div>
    `
    )
    .join("");
}

function renderClinicalSynthesis(syn) {
  // Primary Cohort Classification Banner
  document.getElementById("primaryDiagnosisBanner").innerHTML = `
    <strong>Published Cohort Alignment (FHIR Phenotype):</strong> ${formatClinicalTextWithPmidLinks(syn.primary_diagnosis_summary || "")}
  `;

  // Key Takeaways
  const takeaways = syn.key_clinical_takeaways || [];
  document.getElementById("keyTakeawaysBox").innerHTML = `
    <div class="takeaways-title">Key Published Trial &amp; Guideline Findings</div>
    <ul class="takeaways-list">
      ${takeaways.map((t) => `<li>${formatClinicalTextWithPmidLinks(t)}</li>`).join("")}
    </ul>
  `;

  // Detailed Point-of-Care Literature Synthesis
  const paragraphs = (syn.point_of_care_answer || "").split(/\n\n+/);
  document.getElementById("pointOfCareAnswerBox").innerHTML = paragraphs
    .map((p) => `<p>${formatClinicalTextWithPmidLinks(p)}</p>`)
    .join("");

  // Diagnostic Cohort Parallels
  const diffs = syn.differential_diagnoses || [];
  document.getElementById("differentialList").innerHTML = diffs
    .map(
      (d) => `
      <div class="dx-item-card">
        <div class="dx-top-row">
          <span class="dx-title">${escapeHtml(d.diagnosis)}</span>
          <span class="badge-pill badge-teal">${escapeHtml(d.likelihood)}</span>
        </div>
        <div class="dx-meta-grid">
          <div class="dx-meta-box">
            <div class="dx-meta-label">Patient FHIR Phenotype Parallels</div>
            <div>${escapeHtml(d.fhir_evidence)}</div>
          </div>
          <div class="dx-meta-box">
            <div class="dx-meta-label">Diagnostic Evaluation Criteria in Literature</div>
            <div>${escapeHtml(d.diagnostic_workup)}</div>
          </div>
        </div>
        <div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap;align-items:center;">
          <span style="font-size:11px;color:#94a3b8;">Peer-Reviewed Citations:</span>
          ${(d.supporting_pmids || [])
            .map(
              (pmid) =>
                `<button class="pmid-chip" onclick="focusArticle('${escapeHtml(pmid)}')">PMID: ${escapeHtml(pmid)}</button>`
            )
            .join("")}
        </div>
      </div>
    `
    )
    .join("");

  // Comparative Therapeutic Evidence Matrix
  const txPlan = syn.treatment_plan || [];
  document.getElementById("treatmentPlanList").innerHTML = txPlan
    .map(
      (tx) => `
      <div class="tx-item-card">
        <div class="tx-category-label">${escapeHtml(tx.category)}</div>
        <div class="tx-top-row">
          <span class="tx-title">${escapeHtml(tx.intervention)}</span>
          <span class="badge-pill badge-indigo">${escapeHtml(tx.evidence_grade)}</span>
        </div>
        <div style="font-size:13px;color:#cbd5e1;margin-bottom:8px;">
          ${formatClinicalTextWithPmidLinks(tx.rationale)}
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;">
          <span style="font-size:11px;color:#94a3b8;">Verified Journal Evidence:</span>
          ${(tx.supporting_pmids || [])
            .map(
              (pmid) =>
                `<button class="pmid-chip" onclick="focusArticle('${escapeHtml(pmid)}')">PMID: ${escapeHtml(pmid)}</button>`
            )
            .join("")}
        </div>
      </div>
    `
    )
    .join("");

  // Trial Exclusions & Study Endpoints
  const warnings = syn.contraindications_and_warnings || [];
  document.getElementById("warningsList").innerHTML = warnings
    .map((w) => `<li>${formatClinicalTextWithPmidLinks(w)}</li>`)
    .join("");

  const monitoring = syn.monitoring_and_follow_up || [];
  document.getElementById("monitoringList").innerHTML = monitoring
    .map((m) => `<li>${formatClinicalTextWithPmidLinks(m)}</li>`)
    .join("");
}

function renderJournalEvidencePanel(articles) {
  const totalCount = articles.length + activeClinicalTrials.length;
  document.getElementById("articlesCountBadge").textContent =
    `${articles.length} Papers • ${activeClinicalTrials.length} NCT Trials`;

  const journals = ["ALL", "NCT_TRIALS", ...new Set(articles.map((a) => a.journal_short))];
  const filterBar = document.getElementById("journalFilterBar");
  filterBar.innerHTML = journals
    .map((j) => {
      let label = j;
      if (j === "ALL") label = `All Evidence (${totalCount})`;
      else if (j === "NCT_TRIALS") label = `ClinicalTrials.gov (${activeClinicalTrials.length})`;
      return `
        <button class="filter-chip ${j === activeJournalFilter ? "active" : ""}" data-j="${escapeHtml(j)}">
          ${escapeHtml(label)}
        </button>
      `;
    })
    .join("");

  filterBar.querySelectorAll(".filter-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      activeJournalFilter = chip.getAttribute("data-j");
      renderJournalEvidencePanel(activeRetrievedArticles);
    });
  });

  const container = document.getElementById("articlesContainer");

  const renderTrialCards = () =>
    activeClinicalTrials
      .map(
        (t) => `
        <article class="article-card" style="border-left:3px solid #38bdf8;">
          <div class="article-top-badges">
            <span class="journal-badge" style="color:#38bdf8;">ClinicalTrials.gov &bull; ${escapeHtml(t.nct_id)}</span>
            <span class="pub-type-badge">${escapeHtml(t.phase)} &bull; ${escapeHtml(t.status)}</span>
          </div>
          <h4 class="article-title">${escapeHtml(t.title)}</h4>
          <div class="article-abstract">
            <strong>Conditions:</strong> ${escapeHtml(t.conditions)}<br/>
            <strong>Studied Interventions:</strong> ${escapeHtml(t.interventions)}
          </div>
          <div class="article-footer">
            <span style="color:#38bdf8;font-size:11px;font-weight:600;">&#10003; NIH ClinicalTrials.gov API v2</span>
            <div class="article-links">
              <a href="${escapeHtml(t.url)}" target="_blank" rel="noopener" class="ext-link">${escapeHtml(t.nct_id)} &#8599;</a>
            </div>
          </div>
        </article>
      `
      )
      .join("");

  if (activeJournalFilter === "NCT_TRIALS") {
    container.innerHTML = renderTrialCards();
    return;
  }

  const filtered =
    activeJournalFilter === "ALL"
      ? articles
      : articles.filter((a) => a.journal_short === activeJournalFilter);

  const articlesHtml = filtered
    .map(
      (a) => `
      <article id="article-pmid-${escapeHtml(a.pmid)}" class="article-card">
        <div class="article-top-badges">
          <span class="journal-badge">${escapeHtml(a.journal_short)} &bull; ${escapeHtml(a.year)}</span>
          <span class="pub-type-badge">${escapeHtml(a.evidence_level || a.pub_type)}</span>
        </div>
        <h4 class="article-title">${escapeHtml(a.title)}</h4>
        <div class="article-authors">${escapeHtml(a.authors)} — <em>${escapeHtml(a.journal)}</em></div>
        <div class="article-abstract">${escapeHtml(a.abstract_summary)}</div>
        <div class="article-footer">
          <span style="color:#34d399;font-size:11px;font-weight:600;">&#10003; ${escapeHtml(a.source_verification || "Whitelisted Journal")}</span>
          <div class="article-links">
            <a href="${escapeHtml(a.pubmed_url)}" target="_blank" rel="noopener" class="ext-link">PMID: ${escapeHtml(a.pmid)} &#8599;</a>
            ${
              a.doi
                ? `<a href="${escapeHtml(a.doi_url)}" target="_blank" rel="noopener" class="ext-link">DOI &#8599;</a>`
                : ""
            }
          </div>
        </div>
      </article>
    `
    )
    .join("");

  container.innerHTML =
    activeJournalFilter === "ALL" ? articlesHtml + renderTrialCards() : articlesHtml;
}

window.focusArticle = function (pmid) {
  const cleanPmid = String(pmid).replace(/\D/g, "");
  if (activeJournalFilter !== "ALL") {
    activeJournalFilter = "ALL";
    renderJournalEvidencePanel(activeRetrievedArticles);
  }
  const el = document.getElementById(`article-pmid-${cleanPmid}`);
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.remove("highlight-pulse");
    void el.offsetWidth;
    el.classList.add("highlight-pulse");
    setTimeout(() => el.classList.remove("highlight-pulse"), 2600);
  } else {
    window.open(`https://pubmed.ncbi.nlm.nih.gov/${cleanPmid}/`, "_blank", "noopener");
  }
};

function formatClinicalTextWithPmidLinks(text) {
  let safe = escapeHtml(text);
  // Bold markdown **text**
  safe = safe.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  // Italic markdown *text*
  safe = safe.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  // Convert [PMID: 12345678] or PMID: 12345678 into clickable chips
  safe = safe.replace(/\[?PMID:\s*(\d{6,9})\]?/gi, (match, pmid) => {
    return `<button class="pmid-chip" onclick="focusArticle('${pmid}')">PMID: ${pmid}</button>`;
  });
  return safe;
}

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
