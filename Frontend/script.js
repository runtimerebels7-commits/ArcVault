// ================================================
// ArcVault DATASET MARKETPLACE
// ArcVault marketplace populated from the shared backend database
// ================================================


// 1. DATASET INFORMATION

let datasets = [];

const MARKETPLACE_API = window.ARCVault_API_BASE || "http://127.0.0.1:5000";

function mapPublication(publication) {
    const terms = String(publication.licence_terms || "");
    const termValue = (label, fallback = "Not specified") => {
        const match = terms.match(new RegExp("(?:^|;\\s*)" + label + "\\s*:\\s*([^;]+)", "i"));
        return match ? match[1].trim() : fallback;
    };
    const signed = publication.signed_rights_record || {};
    const rights = signed.rights_record || {};
    const uses = Array.isArray(publication.allowed_uses) ? publication.allowed_uses : [];
    const status = String(publication.status || "unknown");
    const verified = Boolean(publication.rights_verified) && publication.signature_status === "VALID";
    return {
        id: publication.publication_id,
        name: publication.title,
        language: publication.language || "Other",
        category: termValue("Category", "Other"),
        type: termValue("Category", "Dataset"),
        format: termValue("Format", "Unknown"),
        size: termValue("Size", "Not specified"),
        price: Number(publication.licensing_cost) || 0,
        provider: publication.publisher_name || "ArcVault Publisher",
        description: publication.description || "No description provided.",
        licenceType: publication.licence_type || "Unspecified",
        permittedUses: uses,
        commercialUse: uses.includes("commercial_training"),
        licenceStatus: status === "active" ? "Active" : status,
        expiryDate: rights.expiry_date || termValue("Expiry"),
        region: (rights.allowed_regions || []).join(", ") || "As specified in licence terms",
        signatureStatus: verified ? "Verified" : (publication.signature_status || "Unverified"),
        integrityStatus: verified ? "Intact" : "Unknown",
        rightsHolder: publication.publisher_name || "Dataset publisher",
        dataSource: "Publisher portal listing",
        lastUpdated: publication.updated_at || publication.created_at || "Not available",
        restrictions: termValue("Description", "Check the licence terms before use."),
        verificationReason: verified ? "The signed rights record was verified by the backend." : "Rights verification has not been confirmed."
    };
}

async function loadMarketplace() {
    datasetContainer.innerHTML = "<p>Loading datasets from the shared ArcVault database...</p>";
    try {
        const response = await fetch(`${MARKETPLACE_API}/api/marketplace`);
        if (!response.ok) throw new Error(`Marketplace API returned ${response.status}`);
        const payload = await response.json();
        datasets = (payload.publications || []).map(mapPublication);
        selectedDatasets = [];
        displayDatasets();
    } catch (error) {
        datasets = [];
        resultCount.textContent = "Marketplace unavailable";
        datasetContainer.innerHTML = `<p>Could not load the shared marketplace. Make sure the main backend is running at ${MARKETPLACE_API}. (${String(error.message)})</p>`;
        updateCompareButton();
    }
}



// 2. HTML ELEMENTS

const searchInput = document.getElementById("searchInput");
const languageFilter = document.getElementById("languageFilter");
const categoryFilter = document.getElementById("categoryFilter");
const useFilter = document.getElementById("useFilter");
const maxPriceInput = document.getElementById("maxPrice");
const licenceFilter = document.getElementById("licenceFilter");
const verificationFilter = document.getElementById("verificationFilter");

const datasetContainer = document.getElementById("datasetContainer");
const resultCount = document.getElementById("resultCount");

const compareButton = document.getElementById("compareButton");
const clearCompareButton = document.getElementById("clearCompare");

const comparisonSection = document.getElementById("comparisonSection");
const comparisonTable = document.getElementById("comparisonTable");


// 3. SELECTED DATASETS

let selectedDatasets = [];


// 4. FORMAT PRICE

function formatPrice(price) {
    return new Intl.NumberFormat("en-IN", {
        style: "currency",
        currency: "INR",
        maximumFractionDigits: 0
    }).format(price);
}


// 5. CREATE STATUS LABELS

function getStatusClass(status) {
    const value = status.toLowerCase();

    if (["active", "verified", "intact"].includes(value)) {
        return "status-active";
    }

    if (["expired", "revoked", "failed"].includes(value)) {
        return "status-expired";
    }

    return "status-unknown";
}

function statusLabel(status) {
    return `<span class="status ${getStatusClass(status)}">${status}</span>`;
}


// 6. FILTER DATASETS

function filterDatasets() {
    const searchText = searchInput.value.toLowerCase().trim();

    const language = languageFilter.value;
    const category = categoryFilter.value;
    const intendedUse = useFilter.value;
    const licenceStatus = licenceFilter.value;
    const signatureStatus = verificationFilter.value;

    const maxPrice = maxPriceInput.value === ""
        ? Infinity
        : Number(maxPriceInput.value);

    return datasets.filter(function (dataset) {

        const searchableText = [
            dataset.name,
            dataset.id,
            dataset.language,
            dataset.category,
            dataset.type,
            dataset.format,
            dataset.description
        ].join(" ").toLowerCase();

        const matchesSearch = searchableText.includes(searchText);

        const matchesLanguage =
            !language || dataset.language === language;

        const matchesCategory =
            !category || dataset.category === category;

        const matchesPrice =
            dataset.price <= maxPrice;

        const matchesLicence =
            !licenceStatus || dataset.licenceStatus === licenceStatus;

        const matchesSignature =
            !signatureStatus || dataset.signatureStatus === signatureStatus;

        let matchesUse = true;

        if (intendedUse === "commercial") {
            matchesUse = dataset.commercialUse;
        }

        if (intendedUse === "research") {
            matchesUse = dataset.permittedUses.includes("research");
        }

        if (intendedUse === "education") {
            matchesUse = dataset.permittedUses.includes("education");
        }

        return (
            matchesSearch &&
            matchesLanguage &&
            matchesCategory &&
            matchesPrice &&
            matchesLicence &&
            matchesSignature &&
            matchesUse
        );
    });
}


// 7. DISPLAY DATASET CARDS

function displayDatasets() {

    const filteredDatasets = filterDatasets();

    resultCount.textContent =
        `${filteredDatasets.length} dataset(s) found`;

    datasetContainer.innerHTML = "";

    if (filteredDatasets.length === 0) {
        datasetContainer.innerHTML = `
            <p>No datasets found. Try changing your search or filters.</p>
        `;
        updateCompareButton();
        return;
    }

    filteredDatasets.forEach(function (dataset) {

        const card = document.createElement("article");
        card.className = "dataset-card";

        const commercialStatus = dataset.commercialUse
            ? "Permitted by demo terms"
            : "Not permitted by demo terms";

        const commercialClass = dataset.commercialUse
            ? "status-active"
            : "status-not-permitted";

        card.innerHTML = `
            <div class="card-top">

                <div>
                    <p class="eyebrow">${dataset.category.toUpperCase()}</p>

                    <h3 class="card-title">${dataset.name}</h3>

                    <p class="dataset-id">${dataset.id}</p>
                </div>

                <div class="price">
                    ${formatPrice(dataset.price)}
                    <small>Demo licence price</small>
                </div>

            </div>


            <div class="tag-list">
                <span class="tag">${dataset.language}</span>
                <span class="tag">${dataset.type}</span>
                <span class="tag">${dataset.format}</span>
            </div>


            <p class="card-description">${dataset.description}</p>


            <div class="card-facts">

                <div>
                    <span class="fact-label">Dataset size</span>
                    <span class="fact-value">${dataset.size}</span>
                </div>

                <div>
                    <span class="fact-label">Licence status</span>
                    ${statusLabel(dataset.licenceStatus)}
                </div>

                <div>
                    <span class="fact-label">Commercial training</span>
                    <span class="status ${commercialClass}">
                        ${commercialStatus}
                    </span>
                </div>

                <div>
                    <span class="fact-label">Signature status</span>
                    ${statusLabel(dataset.signatureStatus)}
                </div>

                <div>
                    <span class="fact-label">Record integrity</span>
                    ${statusLabel(dataset.integrityStatus)}
                </div>

                <div>
                    <span class="fact-label">Provider</span>
                    <span class="fact-value">${dataset.provider}</span>
                </div>

            </div>


            <div class="card-actions">

                <label class="compare-choice">
                    <input
                        type="checkbox"
                        class="compare-checkbox"
                        data-id="${dataset.id}"
                        ${selectedDatasets.includes(dataset.id) ? "checked" : ""}
                    >
                    Compare
                </label>

                <button
                    type="button"
                    class="button button-secondary details-button"
                    aria-expanded="false"
                >
                    View More Details
                </button>

            </div>


            <section class="dataset-details" hidden>

                <h4>Dataset Information</h4>

                <div class="details-grid">

                    <div class="details-item">
                        <strong>Dataset ID</strong>
                        <span>${dataset.id}</span>
                    </div>

                    <div class="details-item">
                        <strong>Data provider</strong>
                        <span>${dataset.provider}</span>
                    </div>

                    <div class="details-item">
                        <strong>Rights holder</strong>
                        <span>${dataset.rightsHolder}</span>
                    </div>

                    <div class="details-item">
                        <strong>Data source</strong>
                        <span>${dataset.dataSource}</span>
                    </div>

                    <div class="details-item">
                        <strong>Last updated</strong>
                        <span>${dataset.lastUpdated}</span>
                    </div>

                    <div class="details-item">
                        <strong>Dataset format</strong>
                        <span>${dataset.format}</span>
                    </div>

                </div>


                <h4>Licensing Details</h4>

                <p><strong>Licence type:</strong> ${dataset.licenceType}</p>

                <p>
                    <strong>Permitted uses:</strong>
                    ${dataset.permittedUses.join(", ")}
                </p>

                <p>
                    <strong>Commercial AI training:</strong>
                    ${commercialStatus}
                </p>

                <p><strong>Licence expiry:</strong> ${dataset.expiryDate}</p>

                <p>
                    <strong>Geographic restrictions:</strong>
                    ${dataset.region}
                </p>

                <p>
                    <strong>Other restrictions:</strong>
                    ${dataset.restrictions}
                </p>


                <h4>Rights Verification</h4>

                <p>
                    <strong>Digital signature:</strong>
                    ${statusLabel(dataset.signatureStatus)}
                </p>

                <p>
                    <strong>Record integrity:</strong>
                    ${statusLabel(dataset.integrityStatus)}
                </p>

                <p>
                    <strong>Verification note:</strong>
                    ${dataset.verificationReason}
                </p>


                <h4>Check Intended Use</h4>

                <p>
                    Select an intended use from the filters above, then
                    check whether this demo record matches it.
                </p>

                <button type="button" class="button button-primary permission-button">
                    Check Demo Permission
                </button>

                <p class="permission-result" aria-live="polite"></p>

                <p class="demo-notice">
                    Demo only: no real licence or digital signature has been verified.
                </p>

            </section>
        `;


        // VIEW MORE DETAILS

        const detailsButton = card.querySelector(".details-button");
        const detailsSection = card.querySelector(".dataset-details");

        detailsButton.addEventListener("click", function () {

            detailsSection.hidden = !detailsSection.hidden;

            detailsButton.textContent = detailsSection.hidden
                ? "View More Details"
                : "Hide Details";

            detailsButton.setAttribute(
                "aria-expanded",
                String(!detailsSection.hidden)
            );
        });


        // SELECT DATASET FOR COMPARISON

        const checkbox = card.querySelector(".compare-checkbox");

        checkbox.addEventListener("change", function () {

            if (checkbox.checked) {

                if (selectedDatasets.length >= 3) {
                    checkbox.checked = false;

                    alert("You can compare up to 3 datasets at a time.");
                    return;
                }

                selectedDatasets.push(dataset.id);

            } else {

                selectedDatasets = selectedDatasets.filter(
                    id => id !== dataset.id
                );
            }

            updateCompareButton();
        });


        // DEMO PERMISSION CHECK

        const permissionButton = card.querySelector(".permission-button");
        const permissionResult = card.querySelector(".permission-result");

        permissionButton.addEventListener("click", function () {

            const intendedUse = useFilter.value;

            if (!intendedUse) {
                permissionResult.textContent =
                    "Select an intended use in the filters first.";
                return;
            }

            const useAllowed = dataset.permittedUses.includes(intendedUse);

            const checksPassed =
                dataset.licenceStatus === "Active" &&
                dataset.signatureStatus === "Verified" &&
                dataset.integrityStatus === "Intact";

            if (useAllowed && checksPassed) {
                permissionResult.textContent =
                    "The signed rights record and permitted-use fields match this use. " +
                    "Confirm legal terms before relying on this prototype.";
            } else {
                permissionResult.textContent =
                    "DEMO RESULT: Not approved by the prototype checks. " +
                    "Licence conditions or verification checks may not be satisfied.";
            }
        });


        datasetContainer.appendChild(card);
    });

    updateCompareButton();
}


// 8. UPDATE COMPARE BUTTON

function updateCompareButton() {
    compareButton.textContent =
        `Compare Selected (${selectedDatasets.length})`;
}


// 9. COMPARE DATASETS

function compareSelectedDatasets() {

    if (selectedDatasets.length < 2) {
        alert("Select at least 2 datasets to compare.");
        return;
    }

    const selectedData = datasets.filter(
        dataset => selectedDatasets.includes(dataset.id)
    );

    const fields = [
        { label: "Dataset ID", key: "id" },
        { label: "Language", key: "language" },
        { label: "Category", key: "category" },
        { label: "Data type", key: "type" },
        { label: "Format", key: "format" },
        { label: "Dataset size", key: "size" },
        { label: "Price", key: "price" },
        { label: "Licence type", key: "licenceType" },
        { label: "Permitted uses", key: "permittedUses" },
        { label: "Commercial training", key: "commercialUse" },
        { label: "Licence status", key: "licenceStatus" },
        { label: "Signature status", key: "signatureStatus" },
        { label: "Record integrity", key: "integrityStatus" },
        { label: "Licence expiry", key: "expiryDate" },
        { label: "Provider", key: "provider" }
    ];

    let html = `
        <table class="comparison-table">
            <thead>
                <tr>
                    <th>Feature</th>
    `;

    selectedData.forEach(function (dataset) {
        html += `<th>${dataset.name}</th>`;
    });

    html += `
                </tr>
            </thead>
            <tbody>
    `;

    fields.forEach(function (field) {

        html += `
            <tr>
                <td class="feature-name">${field.label}</td>
        `;

        selectedData.forEach(function (dataset) {

            let value = dataset[field.key];

            if (field.key === "price") {
                value = formatPrice(value);
            }

            if (field.key === "permittedUses") {
                value = value.join(", ");
            }

            if (field.key === "commercialUse") {
                value = value
                    ? "Yes, under demo terms"
                    : "No, under demo terms";
            }

            html += `<td>${value}</td>`;
        });

        html += "</tr>";
    });

    html += `
            </tbody>
        </table>

        <p class="demo-notice">
            Listings come from the shared ArcVault database. This prototype checks
            recorded rights, but legal terms should still be reviewed.
        </p>
    `;

    comparisonTable.innerHTML = html;
    comparisonSection.hidden = false;

    comparisonSection.scrollIntoView({
        behavior: "smooth",
        block: "start"
    });
}


// 10. CLEAR FILTERS

function clearFilters() {

    searchInput.value = "";
    languageFilter.value = "";
    categoryFilter.value = "";
    useFilter.value = "";
    maxPriceInput.value = "";
    licenceFilter.value = "";
    verificationFilter.value = "";

    displayDatasets();
}


// 11. CLEAR COMPARISON SELECTION

function clearComparison() {

    selectedDatasets = [];

    comparisonSection.hidden = true;
    comparisonTable.innerHTML = "";

    displayDatasets();
}


// 12. EVENT LISTENERS

searchInput.addEventListener("input", displayDatasets);

languageFilter.addEventListener("change", displayDatasets);
categoryFilter.addEventListener("change", displayDatasets);
useFilter.addEventListener("change", displayDatasets);
licenceFilter.addEventListener("change", displayDatasets);
verificationFilter.addEventListener("change", displayDatasets);
maxPriceInput.addEventListener("input", displayDatasets);

document.getElementById("clearFilters")
    .addEventListener("click", clearFilters);

compareButton.addEventListener(
    "click",
    compareSelectedDatasets
);

clearCompareButton.addEventListener(
    "click",
    clearComparison
);

document.getElementById("closeComparison")
    .addEventListener("click", function () {
        comparisonSection.hidden = true;
    });


// 13. INITIALISE PAGE

window.refreshArcVaultMarketplace = loadMarketplace;
loadMarketplace();