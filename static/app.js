const form = document.getElementById("search-form");
const zipInput = document.getElementById("zip");
const status = document.getElementById("status");
const result = document.getElementById("result");

function formatAddress(address) {
  if (!address) {
    return "Nicht verfügbar";
  }
  return address;
}

function formatEmail(value) {
  return value || "Nicht öffentlich veröffentlicht";
}

function renderRow(member) {
  const card = document.createElement("article");
  card.className = "card";

  const title = document.createElement("h3");
  title.textContent = member.name || "Unbekannte Person";
  card.appendChild(title);

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
  email.innerHTML = `<strong>E-Mail:</strong> ${formatEmail(member.email)}`;
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

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const zip = zipInput.value.trim();
  if (!zip) {
    status.textContent = "Bitte eine Postleitzahl eingeben.";
    return;
  }

  status.textContent = "Suche…";
  result.innerHTML = "";

  try {
    const response = await fetch(`/api/search?zip=${encodeURIComponent(zip)}`);
    const payload = await response.json();
    const rows = payload.results || [];
    if (!rows.length) {
      status.textContent = `Keine Treffer für ${zip}.`;
      return;
    }
    status.textContent = `Gefunden: ${rows.length} Abgeordnete im Wahlkreis für ${zip}.`;
    const notice = document.createElement("div");
    notice.className = "notice";
    notice.textContent =
      "Hinweis: Viele E-Mail-Adressen der Bundestagsabgeordneten sind nicht öffentlich. Als Alternative wird das Kontaktformular angezeigt.";
    result.appendChild(notice);
    rows.forEach((member) => result.appendChild(renderRow(member)));
  } catch (error) {
    status.textContent = "Suche fehlgeschlagen. Bitte später erneut versuchen.";
    console.error(error);
  }
});
