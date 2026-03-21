const form = document.getElementById("search-form");
const queryInput = document.getElementById("search-query");
const targetInput = document.getElementById("search-target");
const suggestionsBox = document.getElementById("suggestions");
const status = document.getElementById("status");
const result = document.getElementById("result");

let currentSuggestions = [];
let activeIndex = -1;
let suggestTimer = null;

function formatAddress(address) {
  return address || "Nicht verfügbar";
}

function renderEmail(member) {
  if (!member.email) {
    return "Nicht öffentlich veröffentlicht";
  }

  const label = member.emailGuessed ? "E-Mail (vermutlich):" : "E-Mail:";
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

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function renderRow(member) {
  const card = document.createElement("article");
  card.className = "card";

  const title = document.createElement("h3");
  title.textContent = member.name || "Unbekannte Person";
  card.appendChild(title);

  const place = document.createElement("div");
  place.className = "meta";
  place.innerHTML = `<strong>Wahlkreis:</strong> ${member.constituency || "—"}${
    member.state ? `, ${member.state}` : ""
  }`;
  card.appendChild(place);

  const faction = document.createElement("div");
  faction.className = "meta";
  faction.innerHTML = `<strong>Fraktion:</strong> ${member.faction || "—"}`;
  card.appendChild(faction);

  const address = document.createElement("div");
  address.className = "meta";
  address.innerHTML = `<strong>Postanschrift:</strong> ${formatAddress(
    member.officeAddress
  )}`;
  card.appendChild(address);

  const email = document.createElement("div");
  email.className = "meta";
  email.innerHTML = renderEmail(member);
  card.appendChild(email);

  const links = document.createElement("div");
  links.className = "links muted";
  const profile = member.profileUrl
    ? `<a href="${member.profileUrl}" target="_blank" rel="noopener noreferrer">Profil</a>`
    : "";
  const contact = member.contactFormUrl
    ? `<a href="${member.contactFormUrl}" target="_blank" rel="noopener noreferrer">Kontaktformular</a>`
    : "";
  links.innerHTML = `${profile}${contact ? ` ${contact}` : ""}`.trim();
  card.appendChild(links);

  return card;
}

function clearSuggestions() {
  currentSuggestions = [];
  activeIndex = -1;
  suggestionsBox.hidden = true;
  suggestionsBox.innerHTML = "";
}

function selectSuggestion(index) {
  const suggestion = currentSuggestions[index];
  if (!suggestion) {
    return;
  }
  activeIndex = index;
  targetInput.value = suggestion.id;
  queryInput.value = suggestion.label;
  clearSuggestions();
}

function renderSuggestions(items, promptText = "") {
  currentSuggestions = items;
  activeIndex = -1;

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

function renderResults(rows, target) {
  result.innerHTML = "";
  if (!rows.length) {
    status.textContent = `Keine Treffer für ${target?.label || queryInput.value.trim()}.`;
    return;
  }

  status.textContent = `Gefunden: ${rows.length} Abgeordnete für ${target.label} (${kindLabel(
    target.kind
  )}).`;

  const notice = document.createElement("div");
  notice.className = "notice";
  notice.textContent =
    "Hinweis: Viele E-Mail-Adressen der Bundestagsabgeordneten sind nicht öffentlich. In diesen Fällen wird versucht, die E-Mail-Adresse anhand eines gebräuchlichen Schemas zu erraten. Zudem wird ggf. ein Kontaktformular verlinkt.";
  result.appendChild(notice);
  rows.forEach((member) => result.appendChild(renderRow(member)));
}

queryInput.addEventListener("input", () => {
  if (suggestTimer) {
    clearTimeout(suggestTimer);
  }
  suggestTimer = setTimeout(updateSuggestions, 120);
});

queryInput.addEventListener("keydown", (event) => {
  if (suggestionsBox.hidden || !currentSuggestions.length) {
    return;
  }

  if (event.key === "ArrowDown") {
    event.preventDefault();
    activeIndex = (activeIndex + 1) % currentSuggestions.length;
  } else if (event.key === "ArrowUp") {
    event.preventDefault();
    activeIndex =
      activeIndex <= 0 ? currentSuggestions.length - 1 : activeIndex - 1;
  } else if (event.key === "Enter" && activeIndex >= 0) {
    event.preventDefault();
    selectSuggestion(activeIndex);
    return;
  } else if (event.key === "Escape") {
    clearSuggestions();
    return;
  } else {
    return;
  }

  [...suggestionsBox.querySelectorAll(".suggestion-item")].forEach((node, index) => {
    node.classList.toggle("is-active", index === activeIndex);
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

form.addEventListener("submit", async (event) => {
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
