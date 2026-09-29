const LETTER_BODY = `ich möchte Sie, da Sie mich als Abgeordnete*r vertreten, dringend bitten, sich in den laufenden Haushaltsverhandlungen für die ausreichende Weiterfinanzierung der Asylverfahrensberatung einzusetzen.

Die Asylverfahrensberatung ist ein notwendiges Instrument, um faire und sachlich richtige Asylverfahren zu gewährleisten. Mitarbeitende der Wohlfahrtsverbände erbringen diese Beratung mit großem persönlichen Engagement für schutzsuchende Menschen.

Als Rechtsanwält*in weiß ich aus der Praxis: Es genügt nicht, Rechte zu haben, man muss sie auch kennen, um sie wahrnehmen zu können. Die Asylverfahrensberatung unterstützt Asylsuchende dabei, im komplizierten Asylverfahren ihre Schutzbedürftigkeit deutlich zu machen. Sie trägt damit auch zu qualitativ besseren Asylentscheidungen und mehr Rechtssicherheit bei. Sie erleichtert die Verfahren beim Bundesamt für Migration und Flüchtlinge. Sie hilft, unnötige Klagen vor den Verwaltungsgerichten zu vermeiden. Sie kann auch nicht durch die geplante behördliche Rechtsauskunft ersetzt werden, die keine individuell auf den Einzelfall bezogene Beratung bietet.

Im Haushaltsplan für 2027 sind für die Asylverfahrensberatung in ganz Deutschland nur noch fünf Millionen Euro vorgesehen. Ein Fünftel des Ansatzes im aktuellen Haushalt, und schon mit den derzeitigen 25 Millionen Euro lässt sich die Aufgabe eigentlich nicht bewältigen. Ursprünglich wollte Bundesinnenminister Dobrindt die Mittel für die Beratung sogar ganz streichen, obwohl der Bund gesetzlich verpflichtet ist, die Beratung zu fördern. Zudem schreibt das neue EU-Asylrecht vor, dass jeder asylsuchende Mensch Anspruch auf eine kostenlose und unabhängige Rechtsberatung hat, wie die Wohlfahrtsverbände sie erbringen. Die massive Kürzung der Mittel ist nicht nur eklatant rechtswidrig. Sie ist mit Blick auf den Nutzen einer sachgerechten Beratung für die Asylsuchenden wie für das Bundesamt auch kurzsichtig.

Bitte sorgen Sie deshalb dafür, dass die Asylverfahrensberatung weiterhin erbracht werden kann.`;

const state = {
  currentSuggestions: [],
  activeSuggestionIndex: -1,
  suggestTimer: null,
  currentTarget: null,
  results: [],
  selectedMembers: new Map(),
  previewMemberId: null,
  emailProvider: "mailto",
  // Recipients a bulk "open all" run could not open yet (pop-up blocker); the next click continues with them.
  pendingBulkIds: null,
  salutations: new Map(),
  step: 1,
};

const searchForm = document.getElementById("search-form");
const queryInput = document.getElementById("search-query");
const targetInput = document.getElementById("search-target");
const suggestionsBox = document.getElementById("suggestions");
const status = document.getElementById("status");
const selectionInfo = document.getElementById("selection-info");
const resultSortControls = document.getElementById("result-sort-controls");
const resultSortSelect = document.getElementById("result-sort");
const result = document.getElementById("result");
const toStep2Button = document.getElementById("to-step-2");

const step1Panel = document.getElementById("step-1");
const step2Panel = document.getElementById("step-2");
const step3Panel = document.getElementById("step-3");
const stepChip1 = document.getElementById("step-chip-1");
const stepChip2 = document.getElementById("step-chip-2");
const stepChip3 = document.getElementById("step-chip-3");

const selectedMembersBox = document.getElementById("selected-members");
const salutationEditor = document.getElementById("salutation-editor");
const salutationLabel = document.getElementById("salutation-label");
const salutationInput = document.getElementById("recipient-salutation");
const resetSalutationButton = document.getElementById("reset-salutation");
const letterForm = document.getElementById("letter-form");
const senderNameInput = document.getElementById("sender-name");
const senderNameExtraInput = document.getElementById("sender-name-extra");
const senderAddressInput = document.getElementById("sender-address");
const senderEmailInput = document.getElementById("sender-email");
const senderGenderInput = document.getElementById("sender-gender");
const letterPreview = document.getElementById("letter-preview");
const backToStep1Button = document.getElementById("back-to-step-1");
const backToStep2Button = document.getElementById("back-to-step-2");
const step2Status = document.getElementById("step-2-status");
const emailMode = document.getElementById("email-mode");
const emailProviderSelect = document.getElementById("email-provider");
const emailProviderHint = document.getElementById("email-provider-hint");
const openAllEmailsButton = document.getElementById("open-all-emails");
const emailStatus = document.getElementById("email-status");
const emailActions = document.getElementById("email-actions");
const downloadStatus = document.getElementById("download-status");
const downloadLettersButton = document.getElementById("download-letters");

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
  const parts = text.split(",").map((part) => part.trim()).filter(Boolean);
  if (parts.length <= 1) {
    return parts;
  }
  if (parts.length === 2) {
    return parts;
  }
  if (/\b\d{5}\b/.test(parts[parts.length - 1])) {
    if (parts.length === 3) {
      return [`${parts[0]} ${parts[1]}`, parts[2]];
    }
    return [parts[0], parts.slice(1, -1).join(" "), parts[parts.length - 1]];
  }
  return [...parts.slice(0, -2), `${parts[parts.length - 2]} ${parts[parts.length - 1]}`];
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

function normalizePartyName(party) {
  return String(party || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function sortResults(rows) {
  const collator = new Intl.Collator("de", { sensitivity: "base" });
  const sortOrder = resultSortSelect.value;
  const partyRanks = new Map([
    ["cdu csu", 0],
    ["spd", 1],
    ["bundnis 90 die grunen", 2],
    ["die linke", 3],
    ["fraktionslos", 4],
    ["afd", 6],
  ]);
  const compareNames = (left, right) =>
    collator.compare(left.lastName || left.fullName || left.name, right.lastName || right.fullName || right.name) ||
    collator.compare(left.firstName || "", right.firstName || "");

  if (sortOrder === "default") {
    return rows;
  }

  return [...rows].sort((left, right) => {
    if (sortOrder === "first-name") {
      return collator.compare(left.firstName || "", right.firstName || "") || compareNames(left, right);
    }
    if (sortOrder === "last-name") {
      return compareNames(left, right);
    }

    const leftParty = normalizePartyName(left.faction);
    const rightParty = normalizePartyName(right.faction);
    const leftRank = partyRanks.get(leftParty) ?? 5;
    const rightRank = partyRanks.get(rightParty) ?? 5;
    return leftRank - rightRank || compareNames(left, right);
  });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function getSenderPayload() {
  return {
    name: senderNameInput.value.trim(),
    nameExtra: senderNameExtraInput.value.trim(),
    address: senderAddressInput.value.trim(),
    email: senderEmailInput.value.trim(),
    gender: senderGenderInput.value,
  };
}

const PROFESSION_BY_GENDER = { "": "Rechtsanwält*in", m: "Rechtsanwalt", w: "Rechtsanwältin" };

function getProfession(gender) {
  return PROFESSION_BY_GENDER[gender] || PROFESSION_BY_GENDER[""];
}

const RECIPIENT_ROLE_BY_GENDER = { m: "als Abgeordneter", w: "als Abgeordnete" };

function getLetterText(sender, member) {
  const role = RECIPIENT_ROLE_BY_GENDER[member?.gender] || "als Abgeordnete*r";
  return LETTER_BODY.replace("als Abgeordnete*r", role).replace(
    "Als Rechtsanwält*in",
    `Als ${getProfession(sender.gender)}`
  );
}

function getLetterSubject() {
  return "Behördenunabhängige Asylverfahrensberatung gemäß § 12a AsylG";
}

function getDefaultSalutation(member) {
  const name = member?.fullName || member?.displayName || member?.name || "Bundestagsabgeordnete Person";
  return member?.salutation || `Guten Tag, ${name},`;
}

function getSalutation(member) {
  return state.salutations.get(member?.id) || getDefaultSalutation(member);
}

function getLetterBody(member, sender) {
  const closingLines = [sender.name || "Vorname Nachname"];
  if (sender.nameExtra) {
    closingLines.push(sender.nameExtra);
  }
  if (sender.email) {
    closingLines.push(sender.email);
  }

  return [
    getSalutation(member),
    "",
    ...getLetterText(sender, member).split("\n"),
    "",
    "Mit freundlichen Grüßen",
    ...closingLines,
  ].join("\n");
}

// Test mode: if set, every e-mail is addressed to this address instead of the MdB (the real address
// goes into the subject). Empty in production, so the e-mails go to the MdBs themselves.
const MAIL_TEST_RECIPIENT = "";

// Only providers whose compose link can prefill recipient, subject and body are listed (GMX, WEB.DE,
// t-online, iCloud, Proton etc. have none); everyone else uses "other" and the copy buttons.
const MAIL_PROVIDERS = {
  mailto: {
    label: "Mailprogramm auf diesem Gerät",
    action: "Im Mailprogramm öffnen",
    actionAll: "Alle E-Mails im Mailprogramm öffnen",
    compose: (to, subject, body) => `mailto:${encodeURIComponent(to)}?${buildQuery({ subject, body })}`,
    hint: "Öffnet eine fertig ausgefüllte E-Mail in deinem Mailprogramm. Manche Mailprogramme kürzen sehr lange Texte – nutze dann „Text kopieren“.",
  },
  gmail: {
    label: "Gmail",
    action: "In Gmail öffnen",
    actionAll: "Alle E-Mails in Gmail öffnen",
    compose: (to, subject, body) => `https://mail.google.com/mail/?view=cm&fs=1&${buildQuery({ to, su: subject, body })}`,
    hint: "Öffnet eine fertig ausgefüllte E-Mail in Gmail. Du musst dort angemeldet sein.",
  },
  outlookCom: {
    label: "Outlook.com (Hotmail, Live)",
    action: "In Outlook öffnen",
    actionAll: "Alle E-Mails in Outlook öffnen",
    compose: (to, subject, body) =>
      `https://outlook.live.com/mail/0/deeplink/compose?${buildQuery({ to, subject, body })}`,
    hint: "Öffnet eine fertig ausgefüllte E-Mail in Outlook.com. Du musst dort angemeldet sein.",
  },
  outlook365: {
    label: "Outlook (Microsoft 365, Arbeit oder Organisation)",
    action: "In Outlook öffnen",
    actionAll: "Alle E-Mails in Outlook öffnen",
    compose: (to, subject, body) =>
      `https://outlook.office.com/mail/deeplink/compose?${buildQuery({ to, subject, body })}`,
    hint: "Öffnet eine fertig ausgefüllte E-Mail in Outlook im Web. Du musst dort angemeldet sein.",
  },
  yahoo: {
    label: "Yahoo Mail",
    action: "In Yahoo Mail öffnen",
    actionAll: "Alle E-Mails in Yahoo Mail öffnen",
    compose: (to, subject, body) => `https://compose.mail.yahoo.com/?${buildQuery({ to, subject, body })}`,
    hint: "Öffnet eine fertig ausgefüllte E-Mail in Yahoo Mail. Du musst dort angemeldet sein.",
  },
  other: {
    label: "Anderer Anbieter (z. B. GMX, WEB.DE, t-online)",
    hint: "Dein Anbieter kann keine vorausgefüllte E-Mail öffnen. Beginne dort eine neue E-Mail und füge Adresse, Betreff und Text über die Kopier-Schaltflächen ein.",
  },
};
const EMAIL_PROVIDER_STORAGE_KEY = "brief.emailProvider";

function loadEmailProvider() {
  try {
    const stored = window.localStorage.getItem(EMAIL_PROVIDER_STORAGE_KEY);
    return MAIL_PROVIDERS[stored] ? stored : "mailto";
  } catch (error) {
    return "mailto";
  }
}

function saveEmailProvider(provider) {
  try {
    window.localStorage.setItem(EMAIL_PROVIDER_STORAGE_KEY, provider);
  } catch (error) {
    // Remembering the choice is only a convenience.
  }
}

function getMailRecipient(member) {
  return MAIL_TEST_RECIPIENT || member?.email || "";
}

function getMailSubject(member) {
  return MAIL_TEST_RECIPIENT ? `[Test, eigentlich an ${member.email}] ${getLetterSubject()}` : getLetterSubject();
}

function buildQuery(params) {
  return Object.entries(params)
    .map(([key, value]) => `${key}=${encodeURIComponent(value)}`)
    .join("&");
}

function buildProviderLink(member, sender) {
  const provider = MAIL_PROVIDERS[state.emailProvider];
  if (!provider.compose) {
    return "";
  }
  return provider.compose(getMailRecipient(member), getMailSubject(member), getLetterBody(member, sender));
}

function renderProviderSelect() {
  emailProviderSelect.innerHTML = Object.entries(MAIL_PROVIDERS)
    .map(([key, provider]) => `<option value="${key}">${escapeHtml(provider.label)}</option>`)
    .join("");
  emailProviderSelect.value = state.emailProvider;
}

function renderEmailActions() {
  const sender = getSenderPayload();
  const selected = [...state.selectedMembers.values()];

  const provider = MAIL_PROVIDERS[state.emailProvider];
  emailProviderHint.textContent = provider.hint;

  openAllEmailsButton.hidden = !provider.actionAll;
  openAllEmailsButton.textContent = state.pendingBulkIds
    ? bulkRemainderLabel(state.pendingBulkIds.length)
    : provider.actionAll || "";

  emailMode.hidden = !MAIL_TEST_RECIPIENT;
  emailMode.textContent = `Testbetrieb: Alle E-Mails sind derzeit an ${MAIL_TEST_RECIPIENT} adressiert, nicht an die Abgeordneten.`;

  if (!selected.length) {
    openAllEmailsButton.disabled = true;
    emailStatus.textContent = "";
    emailActions.innerHTML = "<p class=\"muted\">Noch keine Empfänger*innen ausgewählt.</p>";
    return;
  }

  const emailableCount = selected.filter((member) => member.email).length;
  openAllEmailsButton.disabled = emailableCount === 0;
  emailStatus.textContent = emailableCount
    ? `Für ${emailableCount} ${emailableCount === 1 ? "Person" : "Personen"} ist eine E-Mail-Adresse hinterlegt.`
    : "Für die Auswahl sind aktuell keine E-Mail-Adressen vorhanden.";

  emailActions.innerHTML = selected
    .map((member) => {
      const label = member.fullName || member.displayName || member.name || "Unbekannte Person";
      const factionLabel = member.faction ? `${label} (${member.faction})` : label;
      if (member.email) {
        const link = buildProviderLink(member, sender);
        const id = escapeHtml(member.id);
        return `
          <div class="email-action">
            <strong>${escapeHtml(factionLabel)}</strong>
            <p>${escapeHtml(getMailRecipient(member))}</p>
            ${
              link
                ? `<a class="action-link" href="${escapeHtml(link)}"${
                    state.emailProvider === "mailto" ? "" : ' target="_blank" rel="noopener noreferrer"'
                  }>${escapeHtml(provider.action)}</a>`
                : ""
            }
            <div class="copy-buttons">
              <button type="button" class="copy-button" data-copy="address" data-member-id="${id}">Adresse kopieren</button>
              <button type="button" class="copy-button" data-copy="subject" data-member-id="${id}">Betreff kopieren</button>
              <button type="button" class="copy-button" data-copy="body" data-member-id="${id}">Text kopieren</button>
            </div>
          </div>
        `;
      }
      if (member.contactFormUrl) {
        return `
          <div class="email-action">
            <strong>${escapeHtml(factionLabel)}</strong>
            <p>Keine E-Mail-Adresse verfügbar. Es gibt aber ein Kontaktformular.</p>
            <a class="action-link" href="${escapeHtml(member.contactFormUrl)}" target="_blank" rel="noopener noreferrer">Kontaktformular öffnen</a>
          </div>
        `;
      }
      return `
        <div class="email-action">
          <strong>${escapeHtml(factionLabel)}</strong>
          <p>Für diese Person ist aktuell weder eine E-Mail-Adresse noch ein Kontaktformular hinterlegt.</p>
        </div>
      `;
    })
    .join("");
}

function bulkRemainderLabel(count) {
  return count === 1 ? "Restliche E-Mail öffnen" : `Restliche ${count} E-Mails öffnen`;
}

function openAllEmails() {
  const sender = getSenderPayload();
  const emailable = [...state.selectedMembers.values()].filter((member) => member.email);
  const members = state.pendingBulkIds
    ? emailable.filter((member) => state.pendingBulkIds.includes(member.id))
    : emailable;
  state.pendingBulkIds = null;

  if (!members.length) {
    renderEmailActions();
    return;
  }

  if (state.emailProvider === "mailto") {
    emailStatus.textContent = `Es werden jetzt ${members.length} einzelne E-Mails im Mailprogramm geöffnet. Je nach Browser musst du jede einzeln bestätigen.`;
    members.forEach((member, index) => {
      window.setTimeout(() => {
        window.location.href = buildProviderLink(member, sender);
      }, index * 500);
    });
    return;
  }

  // Webmailers open in new tabs. Browsers usually allow only one new window per click and block the
  // rest, so stop at the first blocked tab and let the next click continue from there.
  let openedCount = 0;
  for (const member of members) {
    const tab = window.open(buildProviderLink(member, sender), "_blank");
    if (!tab) {
      break;
    }
    tab.opener = null;
    openedCount += 1;
  }

  const remaining = members.slice(openedCount);
  state.pendingBulkIds = remaining.length ? remaining.map((member) => member.id) : null;
  renderEmailActions();
  if (remaining.length) {
    emailStatus.textContent = `${openedCount} von ${members.length} E-Mails geöffnet. Dein Browser hat weitere Tabs blockiert. Erlaube Pop-ups für diese Seite (meist über ein Symbol in der Adressleiste) und klicke dann auf „${bulkRemainderLabel(remaining.length)}“.`;
  } else {
    emailStatus.textContent = `${openedCount} E-Mail${openedCount === 1 ? "" : "s"} in neuen Tabs geöffnet.`;
  }
}

// Rich-text editors (e.g. GMX) drop the line breaks of pasted plain text, so the letter is also put
// on the clipboard as HTML with explicit <br> line breaks; plain-text targets keep using text/plain.
function textToHtml(text) {
  return `<div>${escapeHtml(text).replace(/\n/g, "<br>")}</div>`;
}

async function copyText(text, html = "") {
  if (navigator.clipboard && window.isSecureContext) {
    if (html && window.ClipboardItem) {
      await navigator.clipboard.write([
        new ClipboardItem({
          "text/plain": new Blob([text], { type: "text/plain" }),
          "text/html": new Blob([html], { type: "text/html" }),
        }),
      ]);
    } else {
      await navigator.clipboard.writeText(text);
    }
    return;
  }
  // Fallback for plain-HTTP deployments, where the Clipboard API is unavailable.
  const onCopy = (event) => {
    event.clipboardData.setData("text/plain", text);
    if (html) {
      event.clipboardData.setData("text/html", html);
    }
    event.preventDefault();
  };
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  document.addEventListener("copy", onCopy);
  let copied = false;
  try {
    copied = document.execCommand("copy");
  } finally {
    document.removeEventListener("copy", onCopy);
    textarea.remove();
  }
  if (!copied) {
    throw new Error("Kopieren nicht möglich");
  }
}

async function handleCopyClick(button) {
  const member = state.selectedMembers.get(button.dataset.memberId);
  if (!member) {
    return;
  }
  const sender = getSenderPayload();
  const texts = {
    address: getMailRecipient(member),
    subject: getMailSubject(member),
    body: getLetterBody(member, sender),
  };
  const originalLabel = button.dataset.label || button.textContent;
  button.dataset.label = originalLabel;
  try {
    const text = texts[button.dataset.copy] || "";
    await copyText(text, button.dataset.copy === "body" ? textToHtml(text) : "");
    button.textContent = "Kopiert ✓";
  } catch (error) {
    button.textContent = "Kopieren fehlgeschlagen";
    console.error(error);
  }
  window.setTimeout(() => {
    button.textContent = originalLabel;
  }, 2000);
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
  resultSortControls.hidden = rows.length === 0;
  resultSortSelect.value = "default";

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
  grid.innerHTML = sortResults(rows).map(renderMemberCard).join("");
  result.appendChild(grid);
  updateSelectionInfo();
}

function renderSortedResults() {
  const grid = result.querySelector(".result-grid");
  if (grid) {
    grid.innerHTML = sortResults(state.results).map(renderMemberCard).join("");
  }
}

function renderSelectedMembers() {
  const selected = [...state.selectedMembers.values()];
  if (!selected.length) {
    selectedMembersBox.innerHTML = "<p class=\"muted\">Noch keine Empfänger*innen ausgewählt.</p>";
    return;
  }

  const previewMember = getPreviewMember();
  selectedMembersBox.innerHTML = selected
    .map(
      (member) => `
        <button
          type="button"
          class="selected-pill${member === previewMember ? " is-active" : ""}"
          data-member-id="${escapeHtml(member.id)}"
          aria-pressed="${member === previewMember}"
          title="Vorschau des Schreibens an diese Person anzeigen"
        >
          <strong>${escapeHtml(member.displayName || member.name)}</strong>
          <span>${escapeHtml(member.constituency || "")}</span>
        </button>
      `
    )
    .join("");
}

function renderSalutationEditor() {
  const member = getPreviewMember();
  salutationEditor.hidden = !member;
  if (!member) {
    return;
  }
  salutationLabel.textContent = `Anrede für ${member.fullName || member.displayName || member.name}`;
  salutationInput.value = getSalutation(member);
  resetSalutationButton.disabled = !state.salutations.has(member.id);
}

function getPreviewMember() {
  return state.selectedMembers.get(state.previewMemberId) || [...state.selectedMembers.values()][0];
}

function renderLetterPreview() {
  const senderName = senderNameInput.value.trim() || "Vorname Nachname";
  const senderExtra = senderNameExtraInput.value.trim();
  const senderAddress = senderAddressInput.value.trim() || "Straße Hausnummer\nPLZ Ort";
  const senderEmail = senderEmailInput.value.trim();
  const recipient = getPreviewMember();

  const senderLines = [senderName];
  senderLines.push(...senderAddress.split(/\r?\n/).filter(Boolean));
  if (senderEmail) {
    senderLines.push(senderEmail);
  }

  const recipientLines = recipient
    ? [
        recipient.addressName || recipient.fullName || recipient.name,
        ...(recipient.officeAddress && recipient.officeAddress !== "Nicht verfügbar"
          ? splitAddressLines(recipient.officeAddress)
          : splitAddressLines(`${recipient.constituency}, ${recipient.state || ""}`.replace(/,\s*$/, ""))),
      ]
    : ["Ausgewählte/r Bundestagsabgeordnete/r"];

  letterPreview.innerHTML = `
    <div class="preview-meta">${escapeHtml(senderLines.join("\n"))}</div>
    <div class="preview-meta">${escapeHtml(recipientLines.join("\n"))}</div>
    <div class="preview-meta">Behördenunabhängige Asylverfahrensberatung gemäß § 12a AsylG</div>
    <p>${escapeHtml(recipient ? getSalutation(recipient) : "Guten Tag,")}</p>
    ${getLetterText(getSenderPayload(), recipient)
      .split("\n\n")
      .map((paragraph) => `<p>${escapeHtml(paragraph)}</p>`)
      .join("")}
    <p>Mit freundlichen Grüßen</p>
    <p>${escapeHtml(senderName)}</p>
    ${senderExtra ? `<p>${escapeHtml(senderExtra)}</p>` : ""}
  `;
}

function syncStepUi() {
  step1Panel.hidden = state.step !== 1;
  step2Panel.hidden = state.step !== 2;
  step3Panel.hidden = state.step !== 3;
  stepChip1.classList.toggle("is-active", state.step === 1);
  stepChip2.classList.toggle("is-active", state.step === 2);
  stepChip3.classList.toggle("is-active", state.step === 3);
}

function goToStep(stepNumber) {
  state.step = stepNumber;
  if (stepNumber === 2) {
    renderSelectedMembers();
    renderSalutationEditor();
    renderLetterPreview();
    step2Status.textContent = "";
    downloadStatus.textContent = "";
  }
  if (stepNumber === 3) {
    renderSelectedMembers();
    renderLetterPreview();
    state.pendingBulkIds = null;
    renderEmailActions();
    step2Status.textContent = "";
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

resultSortSelect.addEventListener("change", renderSortedResults);

searchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = queryInput.value.trim();
  if (!query) {
    status.textContent = "Bitte einen Ort, Landkreis, ein Bundesland oder eine PLZ eingeben.";
    return;
  }

  status.textContent = "Suche…";
  result.innerHTML = "";
  resultSortControls.hidden = true;

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

selectedMembersBox.addEventListener("click", (event) => {
  const pill = event.target.closest(".selected-pill[data-member-id]");
  if (!pill) {
    return;
  }
  state.previewMemberId = pill.dataset.memberId;
  renderSelectedMembers();
  renderSalutationEditor();
  renderLetterPreview();
});

salutationInput.addEventListener("input", () => {
  const member = getPreviewMember();
  if (!member) {
    return;
  }
  const value = salutationInput.value.trim();
  if (value && value !== getDefaultSalutation(member)) {
    state.salutations.set(member.id, value);
  } else {
    state.salutations.delete(member.id);
  }
  resetSalutationButton.disabled = !state.salutations.has(member.id);
  renderLetterPreview();
});

resetSalutationButton.addEventListener("click", () => {
  const member = getPreviewMember();
  if (member) {
    state.salutations.delete(member.id);
  }
  renderSalutationEditor();
  renderLetterPreview();
});

backToStep1Button.addEventListener("click", () => {
  goToStep(1);
});

backToStep2Button.addEventListener("click", () => {
  goToStep(2);
});

senderGenderInput.addEventListener("change", () => {
  // Only replace the name suffix while it still holds one of the defaults, so custom text is kept.
  if (Object.values(PROFESSION_BY_GENDER).includes(senderNameExtraInput.value.trim())) {
    senderNameExtraInput.value = getProfession(senderGenderInput.value);
  }
  renderLetterPreview();
  if (state.step === 3) {
    renderEmailActions();
  }
});

[senderNameInput, senderNameExtraInput, senderAddressInput, senderEmailInput].forEach((field) => {
  field.addEventListener("input", () => {
    renderLetterPreview();
    if (state.step === 3) {
      renderEmailActions();
    }
  });
});

letterForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!letterForm.reportValidity()) {
    return;
  }
  goToStep(3);
});

async function downloadLetters() {
  if (!letterForm.reportValidity()) {
    goToStep(2);
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
        sender: getSenderPayload(),
        salutations: Object.fromEntries(state.salutations),
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
}

downloadLettersButton.addEventListener("click", downloadLetters);
openAllEmailsButton.addEventListener("click", openAllEmails);

emailProviderSelect.addEventListener("change", () => {
  state.emailProvider = emailProviderSelect.value;
  state.pendingBulkIds = null;
  saveEmailProvider(state.emailProvider);
  renderEmailActions();
});

emailActions.addEventListener("click", (event) => {
  const button = event.target.closest(".copy-button[data-copy]");
  if (button) {
    handleCopyClick(button);
  }
});

state.emailProvider = loadEmailProvider();
renderProviderSelect();
syncStepUi();
updateSelectionInfo();
renderLetterPreview();
