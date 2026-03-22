const LETTER_BODY = `Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.

Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur.

Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.`;

const state = {
  currentSuggestions: [],
  activeSuggestionIndex: -1,
  suggestTimer: null,
  currentTarget: null,
  results: [],
  selectedMembers: new Map(),
  step: 1,
};

const searchForm = document.getElementById("search-form");
const queryInput = document.getElementById("search-query");
const targetInput = document.getElementById("search-target");
const suggestionsBox = document.getElementById("suggestions");
const status = document.getElementById("status");
const selectionInfo = document.getElementById("selection-info");
const result = document.getElementById("result");
const toStep2Button = document.getElementById("to-step-2");

const step1Panel = document.getElementById("step-1");
const step2Panel = document.getElementById("step-2");
const stepChip1 = document.getElementById("step-chip-1");
const stepChip2 = document.getElementById("step-chip-2");

const selectedMembersBox = document.getElementById("selected-members");
const letterForm = document.getElementById("letter-form");
const senderNameInput = document.getElementById("sender-name");
const senderNameExtraInput = document.getElementById("sender-name-extra");
const senderAddressInput = document.getElementById("sender-address");
const senderEmailInput = document.getElementById("sender-email");
const letterPreview = document.getElementById("letter-preview");
const backToStep1Button = document.getElementById("back-to-step-1");
const downloadStatus = document.getElementById("download-status");

function formatAddress(address) {
  return address || "Nicht verfügbar";
}

function splitAddressLines(address) {
  const text = String(address || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n").trim();
  if (!text) {
    return [];
  }
  if (text.includes("\n")) {
    return text.split("\n").map((line) => line.trim()).filter(Boolean);
  }
  return text.split(",").map((part) => part.trim()).filter(Boolean);
}

function renderEmail(member) {
  if (!member.email) {
    return "Nicht öffentlich veröffentlicht";
  }

  const label = "<strong>E-Mail:</strong>";
  const safeEmail = escapeHtml(member.email);
  return `${label} <a href="mailto:${safeEmail}">${safeEmail}</a>`;
}

function kindLabel(kind) {
  return (
    {
      zip: "PLZ",
      community: "Gemeinde",
      county: "Landkreis",
      state: "Bundesland",
    }[kind] || "Treffer"
  );
}

function isAfDMember(member) {
  return String(member?.faction || "").trim().toLowerCase() === "afd";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function clearSuggestions() {
  state.currentSuggestions = [];
  state.activeSuggestionIndex = -1;
  suggestionsBox.hidden = true;
  suggestionsBox.innerHTML = "";
}

function renderSuggestions(items, promptText = "") {
  state.currentSuggestions = items;
  state.activeSuggestionIndex = -1;

  if (!items.length) {
    clearSuggestions();
    return;
  }

  const prompt = promptText
    ? `<div class="suggestions-title">${escapeHtml(promptText)}</div>`
    : "";

  suggestionsBox.innerHTML =
    prompt +
    items
      .map(
        (item, index) => `
          <button class="suggestion-item" data-index="${index}" type="button">
            <span class="suggestion-main">${escapeHtml(item.label)}</span>
            <span class="suggestion-type">${escapeHtml(kindLabel(item.kind))}</span>
            <span class="suggestion-sub">${escapeHtml(item.subtitle || "")}</span>
          </button>
        `
      )
      .join("");
  suggestionsBox.hidden = false;
}

function selectSuggestion(index) {
  const suggestion = state.currentSuggestions[index];
  if (!suggestion) {
    return;
  }
  targetInput.value = suggestion.id;
  queryInput.value = suggestion.label;
  clearSuggestions();
}

async function fetchSuggestions(query) {
  const response = await fetch(`/api/suggest?q=${encodeURIComponent(query)}`);
  const payload = await response.json();
  return payload.suggestions || [];
}

async function updateSuggestions() {
  const query = queryInput.value.trim();
  targetInput.value = "";

  if (!query || query.length < 2) {
    clearSuggestions();
    return;
  }

  try {
    const suggestions = await fetchSuggestions(query);
    renderSuggestions(suggestions);
  } catch (error) {
    clearSuggestions();
    console.error(error);
  }
}

function updateSelectionInfo() {
  const count = state.selectedMembers.size;
  toStep2Button.disabled = count === 0;
  if (!count) {
    selectionInfo.hidden = true;
    selectionInfo.textContent = "";
    return;
  }
  selectionInfo.hidden = false;
  selectionInfo.textContent = `${count} Abgeordnete ausgewählt.`;
}

function renderMemberCard(member) {
  const selected = state.selectedMembers.has(member.id);
  const displayName = member.displayName || member.name || "Unbekannte Person";
  return `
    <article class="card selectable-card${selected ? " is-selected" : ""}">
      <label class="selection-toggle">
        <input type="checkbox" data-member-id="${escapeHtml(member.id)}" ${selected ? "checked" : ""} />
        <span>Diese*n Empfänger*in auswählen</span>
      </label>
      <h3>${escapeHtml(displayName)}</h3>
      <div class="meta"><strong>Wahlkreis:</strong> ${escapeHtml(member.constituency || "—")}${
        member.state ? `, ${escapeHtml(member.state)}` : ""
      }</div>
      <div class="meta"><strong>Fraktion:</strong> ${escapeHtml(member.faction || "—")}</div>
      <div class="meta"><strong>Postanschrift:</strong> ${escapeHtml(formatAddress(member.officeAddress))}</div>
      <div class="meta">${renderEmail(member)}</div>
      <div class="links muted">
        ${
          member.profileUrl
            ? `<a href="${escapeHtml(member.profileUrl)}" target="_blank" rel="noopener noreferrer">Profil</a>`
            : ""
        }
        ${
          member.contactFormUrl
            ? ` <a href="${escapeHtml(member.contactFormUrl)}" target="_blank" rel="noopener noreferrer">Kontaktformular</a>`
            : ""
        }
      </div>
    </article>
  `;
}

function renderResults(rows, target) {
  state.results = rows;
  state.currentTarget = target;
  state.selectedMembers = new Map(rows.filter((member) => !isAfDMember(member)).map((member) => [member.id, member]));
  result.innerHTML = "";

  if (!rows.length) {
    status.textContent = `Keine Treffer für ${target?.label || queryInput.value.trim()}.`;
    updateSelectionInfo();
    return;
  }

  status.textContent = `Gefunden: ${rows.length} Abgeordnete für ${target.label} (${kindLabel(
    target.kind
  )}). Wähle unten die gewünschten Empfänger*innen aus. Wir gehen davon aus, dass du die Abgeordneten der demokratischen Fraktionen anschreiben möchtest, die deswegen bereits vorausgewählt werden.`;

  const grid = document.createElement("div");
  grid.className = "result-grid";
  grid.innerHTML = rows.map(renderMemberCard).join("");
  result.appendChild(grid);
  updateSelectionInfo();
}

function renderSelectedMembers() {
  const selected = [...state.selectedMembers.values()];
  if (!selected.length) {
    selectedMembersBox.innerHTML = "<p class=\"muted\">Noch keine Empfänger*innen ausgewählt.</p>";
    return;
  }

  selectedMembersBox.innerHTML = selected
    .map(
      (member) => `
        <div class="selected-pill">
          <strong>${escapeHtml(member.displayName || member.name)}</strong>
          <span>${escapeHtml(member.constituency || "")}</span>
        </div>
      `
    )
    .join("");
}

function renderLetterPreview() {
  const senderName = senderNameInput.value.trim() || "Vorname Nachname";
  const senderExtra = senderNameExtraInput.value.trim();
  const senderAddress = senderAddressInput.value.trim() || "Straße Hausnummer\nPLZ Ort";
  const senderEmail = senderEmailInput.value.trim() || "name@example.org";
  const firstRecipient = [...state.selectedMembers.values()][0];

  const senderLines = [senderName];
  senderLines.push(...senderAddress.split(/\r?\n/).filter(Boolean));
  senderLines.push(senderEmail);

  const recipientLines = firstRecipient
    ? [
        firstRecipient.displayName || firstRecipient.name,
        ...(firstRecipient.officeAddress && firstRecipient.officeAddress !== "Nicht verfügbar"
          ? splitAddressLines(firstRecipient.officeAddress)
          : splitAddressLines(`${firstRecipient.constituency}, ${firstRecipient.state || ""}`.replace(/,\s*$/, ""))),
      ]
    : ["Ausgewählte/r Bundestagsabgeordnete/r"];

  const salutationName =
    firstRecipient?.fullName || firstRecipient?.displayName || firstRecipient?.name || "Bundestagsabgeordnete Person";

  letterPreview.innerHTML = `
    <div class="preview-meta">${escapeHtml(senderLines.join("\n"))}</div>
    <div class="preview-meta">${escapeHtml(recipientLines.join("\n"))}</div>
    <div class="preview-meta">Behördenunabhängige Asylverfahrensberatung gemäß § 12a AsylG</div>
    <p>${escapeHtml(
      firstRecipient ? `Guten Tag, ${salutationName},` : "Guten Tag,"
    )}</p>
    ${LETTER_BODY.split("\n\n")
      .map((paragraph) => `<p>${escapeHtml(paragraph)}</p>`)
      .join("")}
    <p>Mit freundlichen Grüßen</p>
    <p>${escapeHtml(senderName)}</p>
    ${senderExtra ? `<p>${escapeHtml(senderExtra)}</p>` : ""}
  `;
}

function syncStepUi() {
  const inStep2 = state.step === 2;
  step1Panel.hidden = inStep2;
  step2Panel.hidden = !inStep2;
  stepChip1.classList.toggle("is-active", !inStep2);
  stepChip2.classList.toggle("is-active", inStep2);
}

function goToStep(stepNumber) {
  state.step = stepNumber;
  if (stepNumber === 2) {
    renderSelectedMembers();
    renderLetterPreview();
    downloadStatus.textContent = "";
  }
  syncStepUi();
}

queryInput.addEventListener("input", () => {
  if (state.suggestTimer) {
    clearTimeout(state.suggestTimer);
  }
  state.suggestTimer = setTimeout(updateSuggestions, 120);
});

queryInput.addEventListener("keydown", (event) => {
  if (suggestionsBox.hidden || !state.currentSuggestions.length) {
    return;
  }

  if (event.key === "ArrowDown") {
    event.preventDefault();
    state.activeSuggestionIndex = (state.activeSuggestionIndex + 1) % state.currentSuggestions.length;
  } else if (event.key === "ArrowUp") {
    event.preventDefault();
    state.activeSuggestionIndex =
      state.activeSuggestionIndex <= 0
        ? state.currentSuggestions.length - 1
        : state.activeSuggestionIndex - 1;
  } else if (event.key === "Enter" && state.activeSuggestionIndex >= 0) {
    event.preventDefault();
    selectSuggestion(state.activeSuggestionIndex);
    return;
  } else if (event.key === "Escape") {
    clearSuggestions();
    return;
  } else {
    return;
  }

  [...suggestionsBox.querySelectorAll(".suggestion-item")].forEach((node, index) => {
    node.classList.toggle("is-active", index === state.activeSuggestionIndex);
  });
});

document.addEventListener("click", (event) => {
  if (!suggestionsBox.contains(event.target) && event.target !== queryInput) {
    clearSuggestions();
  }
});

suggestionsBox.addEventListener("click", (event) => {
  const button = event.target.closest(".suggestion-item");
  if (!button) {
    return;
  }
  selectSuggestion(Number(button.dataset.index));
});

result.addEventListener("change", (event) => {
  const checkbox = event.target.closest("input[type='checkbox'][data-member-id]");
  if (!checkbox) {
    return;
  }

  const member = state.results.find((item) => item.id === checkbox.dataset.memberId);
  if (!member) {
    return;
  }

  if (checkbox.checked) {
    state.selectedMembers.set(member.id, member);
  } else {
    state.selectedMembers.delete(member.id);
  }
  checkbox.closest(".selectable-card")?.classList.toggle("is-selected", checkbox.checked);
  updateSelectionInfo();
});

searchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = queryInput.value.trim();
  if (!query) {
    status.textContent = "Bitte einen Ort, Landkreis, ein Bundesland oder eine PLZ eingeben.";
    return;
  }

  status.textContent = "Suche…";
  result.innerHTML = "";

  try {
    const params = new URLSearchParams();
    if (targetInput.value) {
      params.set("target", targetInput.value);
    } else {
      params.set("q", query);
    }

    const response = await fetch(`/api/search?${params.toString()}`);
    const payload = await response.json();

    if (payload.ambiguous && payload.suggestions?.length) {
      status.textContent = `„${query}“ ist nicht eindeutig. Bitte wähle einen passenden Eintrag aus.`;
      renderSuggestions(payload.suggestions, "Passende Vorschläge");
      return;
    }

    if (!payload.target) {
      status.textContent = `Keine Treffer für ${query}.`;
      clearSuggestions();
      updateSelectionInfo();
      return;
    }

    targetInput.value = payload.target.id;
    queryInput.value = payload.target.label;
    clearSuggestions();
    renderResults(payload.results || [], payload.target);
  } catch (error) {
    status.textContent = "Suche fehlgeschlagen. Bitte später erneut versuchen.";
    console.error(error);
  }
});

toStep2Button.addEventListener("click", () => {
  if (!state.selectedMembers.size) {
    return;
  }
  goToStep(2);
});

backToStep1Button.addEventListener("click", () => {
  goToStep(1);
});

[senderNameInput, senderNameExtraInput, senderAddressInput, senderEmailInput].forEach((field) => {
  field.addEventListener("input", renderLetterPreview);
});

letterForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!letterForm.reportValidity()) {
    return;
  }

  downloadStatus.textContent = "Schreiben werden erstellt…";

  try {
    const response = await fetch("/api/letters", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        memberIds: [...state.selectedMembers.keys()],
        sender: {
          name: senderNameInput.value.trim(),
          nameExtra: senderNameExtraInput.value.trim(),
          address: senderAddressInput.value.trim(),
          email: senderEmailInput.value.trim(),
        },
      }),
    });

    if (!response.ok) {
      let message = "Download fehlgeschlagen.";
      try {
        const payload = await response.json();
        if (payload.error) {
          message = payload.error;
        }
      } catch (error) {
        console.error(error);
      }
      downloadStatus.textContent = message;
      return;
    }

    const blob = await response.blob();
    const downloadUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const disposition = response.headers.get("Content-Disposition") || "";
    const filenameMatch = disposition.match(/filename="([^"]+)"/);
    link.href = downloadUrl;
    link.download = filenameMatch ? filenameMatch[1] : "bundestag-schreiben.zip";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(downloadUrl);
    downloadStatus.textContent = "ZIP-Archiv wurde heruntergeladen.";
  } catch (error) {
    downloadStatus.textContent = "Download fehlgeschlagen. Bitte später erneut versuchen.";
    console.error(error);
  }
});

syncStepUi();
updateSelectionInfo();
renderLetterPreview();
