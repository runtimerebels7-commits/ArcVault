// ArcVault Budget Optimiser UI
// This file owns the optimisation form and renders the Flask JSON response
// as readable UI cards. It does not replace Frontend/script.js, which owns
// the dataset marketplace.

(() => {
  "use strict";

  const API_BASE = String(window.ARCVault_API_BASE || "http://127.0.0.1:5000").replace(/\/+$/, "");

  function byId(id) {
    return document.getElementById(id);
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;"
    })[char]);
  }

  function money(value) {
    const amount = Number(value);
    if (!Number.isFinite(amount)) return "—";
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 2
    }).format(amount);
  }

  function displayValue(value) {
    if (value === null || value === undefined || value === "") return "—";
    return escapeHtml(value);
  }

  function setStatus(element, message, kind = "info") {
    element.textContent = message;
    element.dataset.state = kind;
    element.setAttribute("role", kind === "error" ? "alert" : "status");
  }

  function ensureResultsContainer(original) {
    // The existing page uses <pre id="optimisationResults">, which is suitable
    // for raw JSON but not for cards/tables. Replace it with a normal section.
    if (original && original.tagName.toLowerCase() === "pre") {
      const section = document.createElement("section");
      section.id = original.id;
      section.hidden = true;
      section.className = "optimisation-results";
      section.setAttribute("aria-live", "polite");
      original.replaceWith(section);
      return section;
    }
    return original;
  }

  async function readJsonResponse(response) {
    const raw = await response.text();
    let data;
    try {
      data = raw ? JSON.parse(raw) : {};
    } catch {
      throw new Error(
        `The backend returned non-JSON content (HTTP ${response.status}). ` +
        "Check that the Flask API is running on port 5000 and that the URL is correct."
      );
    }
    if (!response.ok) {
      throw new Error(data.error || data.message || `Request failed (HTTP ${response.status})`);
    }
    return data;
  }

  async function loadMarketplaceById() {
    const response = await fetch(`${API_BASE}/api/marketplace`, {
      headers: { Accept: "application/json" }
    });
    const data = await readJsonResponse(response);
    const publications = Array.isArray(data.publications) ? data.publications : [];
    return new Map(publications.map((item) => [
      String(item.publication_id),
      item
    ]));
  }

  function renderSelectedDatasets(result, publicationMap) {
    const ids = Array.isArray(result.selected_dataset_ids) ? result.selected_dataset_ids : [];
    if (!ids.length) {
      return `
        <div class="opt-empty">
          <strong>No datasets were selected.</strong>
          <p>No rights-approved datasets fit the entered budget for this intended use,
          or no eligible datasets are currently published.</p>
        </div>`;
    }

    return `
      <div class="opt-dataset-list">
        ${ids.map((id) => {
          const publication = publicationMap.get(String(id));
          const title = publication?.title || `Dataset ${id}`;
          const provider = publication?.publisher_name || "Publisher not available";
          const cost = publication?.licensing_cost;
          const value = publication?.value_score;
          return `
            <article class="opt-dataset-card">
              <div class="opt-dataset-card__heading">
                <div>
                  <h4>${escapeHtml(title)}</h4>
                  <p class="opt-muted">ID: ${escapeHtml(id)}</p>
                </div>
                <span class="opt-badge">Selected</span>
              </div>
              <dl class="opt-dataset-facts">
                <div><dt>Licence cost</dt><dd>${cost === undefined ? "Included in total" : money(cost)}</dd></div>
                <div><dt>Value score</dt><dd>${value === undefined ? "—" : displayValue(value)}</dd></div>
                <div><dt>Publisher</dt><dd>${escapeHtml(provider)}</dd></div>
              </dl>
            </article>`;
        }).join("")}
      </div>`;
  }

  function renderRejected(result) {
    const rejected = Array.isArray(result.rejected_datasets) ? result.rejected_datasets : [];
    if (!rejected.length) {
      return `<p class="opt-muted">No rejected datasets were reported by the rights checks.</p>`;
    }

    return `
      <details class="opt-rejected">
        <summary>View ${rejected.length} dataset(s) excluded by rights checks</summary>
        <ul>
          ${rejected.map((item) => `
            <li>
              <strong>${escapeHtml(item.dataset_id || "Unknown dataset")}</strong>
              <span>${escapeHtml(item.reason || "Not approved for this intended use")}</span>
            </li>`).join("")}
        </ul>
      </details>`;
  }

  function renderManifest(result) {
    const manifest = result.manifest;
    if (!manifest || typeof manifest !== "object") return "";
    const manifestId = manifest.manifest_id || manifest.id || "Created";
    const accepted = Array.isArray(manifest.accepted_dataset_ids)
      ? manifest.accepted_dataset_ids.length
      : (Array.isArray(result.selected_dataset_ids) ? result.selected_dataset_ids.length : 0);
    return `
      <div class="opt-manifest">
        <strong>Selection manifest created</strong>
        <span>Manifest ID: ${escapeHtml(manifestId)}</span>
        <span>Accepted datasets: ${accepted}</span>
      </div>`;
  }

  function renderResultUI(container, result, publicationMap, requestedBudget, intendedUse) {
    const selectedCount = Array.isArray(result.selected_dataset_ids)
      ? result.selected_dataset_ids.length
      : 0;
    const engine = result.engine || "Optimisation engine";
    const remoteFallback = Boolean(result.remote_fallback);
    const isRemote = String(engine).toLowerCase().includes("qpiai");
    const modeLabel = remoteFallback
      ? "Local fallback used"
      : (isRemote ? "QpiAI remote solver" : "Local solver");

    container.innerHTML = `
      <div class="opt-results-header">
        <div>
          <p class="opt-eyebrow">OPTIMISATION COMPLETE</p>
          <h3>Recommended dataset selection</h3>
          <p class="opt-muted">Intended use: ${escapeHtml(intendedUse.replaceAll("_", " "))}</p>
        </div>
        <span class="opt-engine">${escapeHtml(modeLabel)}</span>
      </div>

      <div class="opt-summary-grid">
        <article class="opt-summary-card">
          <span>Selected datasets</span>
          <strong>${selectedCount}</strong>
        </article>
        <article class="opt-summary-card">
          <span>Total licensing cost</span>
          <strong>${money(result.total_cost)}</strong>
        </article>
        <article class="opt-summary-card">
          <span>Budget remaining</span>
          <strong>${money(Math.max(0, Number(requestedBudget) - Number(result.total_cost || 0)))}</strong>
        </article>
        <article class="opt-summary-card">
          <span>Total value score</span>
          <strong>${displayValue(result.total_value ?? 0)}</strong>
        </article>
      </div>

      <div class="opt-budget-track" aria-label="Budget usage">
        <div class="opt-budget-track__label">
          <span>Budget used</span>
          <strong>${requestedBudget > 0
            ? Math.min(100, Math.max(0, Number(result.total_cost || 0) / Number(requestedBudget) * 100)).toFixed(1)
            : (Number(result.total_cost || 0) === 0 ? "0.0" : "100.0")}%</strong>
        </div>
        <div class="opt-budget-track__bar">
          <span style="width:${requestedBudget > 0
            ? Math.min(100, Math.max(0, Number(result.total_cost || 0) / Number(requestedBudget) * 100))
            : (Number(result.total_cost || 0) === 0 ? 0 : 100)}%"></span>
        </div>
        <p class="opt-muted">Budget: ${money(requestedBudget)} · Engine: ${escapeHtml(engine)}</p>
      </div>

      <h3 class="opt-section-title">Selected datasets</h3>
      ${renderSelectedDatasets(result, publicationMap)}
      <h3 class="opt-section-title">Rights-check exclusions</h3>
      ${renderRejected(result)}
      ${renderManifest(result)}
      <p class="opt-result-message">${escapeHtml(result.message || "Optimisation response received from the backend.")}</p>
      ${remoteFallback && result.remote_error
        ? `<details class="opt-error-detail"><summary>Why the remote solver was not used</summary><p>${escapeHtml(result.remote_error)}</p></details>`
        : ""}
      <details class="opt-raw-response">
        <summary>Developer details (raw JSON)</summary>
        <pre>${escapeHtml(JSON.stringify(result, null, 2))}</pre>
      </details>
    `;
    container.hidden = false;
  }

  function installStyles() {
    if (byId("arcvault-optimisation-styles")) return;
    const style = document.createElement("style");
    style.id = "arcvault-optimisation-styles";
    style.textContent = `
      .optimisation-results { margin-top: 1.25rem; color: inherit; }
      .opt-results-header { display:flex; justify-content:space-between; align-items:flex-start; gap:1rem; flex-wrap:wrap; margin-bottom:1rem; }
      .opt-results-header h3, .opt-section-title { margin:.25rem 0 .65rem; }
      .opt-eyebrow { margin:0; font-size:.75rem; letter-spacing:.12em; font-weight:700; opacity:.7; }
      .opt-muted { opacity:.72; font-size:.9rem; margin:.35rem 0; overflow-wrap:anywhere; }
      .opt-engine, .opt-badge { display:inline-flex; align-items:center; border:1px solid currentColor; border-radius:999px; padding:.35rem .7rem; font-size:.8rem; font-weight:700; }
      .opt-summary-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:.75rem; margin:1rem 0; }
      .opt-summary-card, .opt-dataset-card, .opt-budget-track, .opt-empty, .opt-manifest { border:1px solid rgba(127,127,127,.28); border-radius:12px; padding:1rem; background:rgba(127,127,127,.045); }
      .opt-summary-card span { display:block; font-size:.83rem; opacity:.75; margin-bottom:.5rem; }
      .opt-summary-card strong { display:block; font-size:1.35rem; overflow-wrap:anywhere; }
      .opt-budget-track { margin:1rem 0 1.4rem; }
      .opt-budget-track__label { display:flex; justify-content:space-between; gap:1rem; }
      .opt-budget-track__bar { height:10px; border-radius:999px; background:rgba(127,127,127,.2); overflow:hidden; margin:.6rem 0; }
      .opt-budget-track__bar span { display:block; height:100%; background:#3977d5; border-radius:999px; }
      .opt-section-title { margin-top:1.4rem; }
      .opt-dataset-list { display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:.75rem; }
      .opt-dataset-card__heading { display:flex; justify-content:space-between; align-items:flex-start; gap:.75rem; }
      .opt-dataset-card h4 { margin:0; overflow-wrap:anywhere; }
      .opt-dataset-facts { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.7rem; margin:1rem 0 0; }
      .opt-dataset-facts dt { font-size:.78rem; opacity:.7; }
      .opt-dataset-facts dd { margin:.2rem 0 0; font-weight:600; overflow-wrap:anywhere; }
      .opt-empty p { margin-bottom:0; }
      .opt-rejected, .opt-raw-response, .opt-error-detail { margin:.75rem 0; border:1px solid rgba(127,127,127,.25); border-radius:10px; padding:.75rem 1rem; }
      .opt-rejected li { margin:.6rem 0; overflow-wrap:anywhere; }
      .opt-rejected li span { display:block; opacity:.75; margin-top:.2rem; }
      .opt-manifest { display:flex; flex-direction:column; gap:.35rem; margin-top:1rem; }
      .opt-result-message { margin-top:1rem; }
      .opt-raw-response pre { white-space:pre-wrap; overflow-wrap:anywhere; max-height:360px; overflow:auto; font-size:.8rem; }
      #optimisationStatus[data-state="error"] { color:#b42318; }
      #optimisationStatus[data-state="success"] { color:#167447; }
      @media(max-width:520px) { .opt-dataset-facts { grid-template-columns:1fr; } }
    `;
    document.head.appendChild(style);
  }

  async function init() {
    const form = byId("optimisationForm");
    if (!form) return;

    const status = byId("optimisationStatus");
    const resultsContainer = ensureResultsContainer(byId("optimisationResults"));
    const submitButton = form.querySelector('button[type="submit"], input[type="submit"]');

    if (!status || !resultsContainer) {
      console.error("ArcVault optimiser: missing #optimisationStatus or #optimisationResults element.");
      return;
    }

    installStyles();

    form.addEventListener("submit", async (event) => {
      event.preventDefault();

      const budgetInput = byId("optimisationBudget");
      const useInput = byId("optimisationUse");
      const budget = Number(budgetInput?.value);
      const intendedUse = String(useInput?.value || "").trim();

      if (!Number.isFinite(budget) || budget < 0) {
        setStatus(status, "Enter a valid budget of zero or more.", "error");
        budgetInput?.focus();
        return;
      }
      if (!intendedUse) {
        setStatus(status, "Choose an intended use before running optimisation.", "error");
        useInput?.focus();
        return;
      }

      resultsContainer.hidden = true;
      resultsContainer.replaceChildren();
      if (submitButton) {
        submitButton.disabled = true;
        submitButton.dataset.originalText ||= submitButton.textContent || "Find the best eligible selection";
        submitButton.textContent = "Optimising…";
      }
      setStatus(status, "Checking dataset rights and running optimisation…", "info");

      try {
        const response = await fetch(`${API_BASE}/api/optimization/run`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Accept": "application/json"
          },
          body: JSON.stringify({ budget, intended_use: intendedUse })
        });
        const result = await readJsonResponse(response);

        if (result.status === "ERROR") {
          throw new Error(result.message || "The optimiser returned an error.");
        }

        let publicationMap = new Map();
        try {
          publicationMap = await loadMarketplaceById();
        } catch (lookupError) {
          // The optimisation response is still useful even if dataset titles
          // cannot be loaded. The selected IDs will be shown instead.
          console.warn("ArcVault optimiser: marketplace lookup failed:", lookupError);
        }

        renderResultUI(resultsContainer, result, publicationMap, budget, intendedUse);
        setStatus(status, `Optimisation completed. ${Array.isArray(result.selected_dataset_ids) ? result.selected_dataset_ids.length : 0} dataset(s) selected.`, "success");
      } catch (error) {
        console.error("ArcVault optimisation failed:", error);
        setStatus(
          status,
          `Could not run optimisation: ${error.message}. Confirm the backend is running at ${API_BASE} and open its /api/health endpoint.`,
          "error"
        );
        resultsContainer.hidden = false;
        resultsContainer.innerHTML = `
          <div class="opt-empty">
            <strong>Optimisation did not complete.</strong>
            <p>${escapeHtml(error.message)}</p>
            <p class="opt-muted">Check the Flask terminal for a traceback and the browser DevTools Console/Network tab for the failed request.</p>
          </div>`;
      } finally {
        if (submitButton) {
          submitButton.disabled = false;
          submitButton.textContent = submitButton.dataset.originalText || "Find the best eligible selection";
        }
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
