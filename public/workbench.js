"use strict";
let personalItems = new Map(), loadedGuides = [], previewUrl = null, previewRevision = 0;
const riskNames = {unclassified:"Ej riskklassad", read:"Läsande", change:"Ändrar systemet",
  outage:"Driftavbrott", destructive:"Raderar data"};

function makeDialog(id, title) {
  const dialog = el("dialog"); dialog.id = id;
  const header = el("div", "dialog-heading");
  header.append(el("h2", "", title), action("×", "icon-button", () => dialog.close()));
  header.lastChild.setAttribute("aria-label", "Stäng");
  const body = el("div"); body.id = id + "-body";
  const error = el("p", "error"); error.id = id + "-error"; error.hidden = true; error.setAttribute("role", "alert");
  dialog.append(header, body, error); document.body.append(dialog); return dialog;
}
function riskBadge(item) {
  return el("span", `risk-badge risk-${item.risk || "unclassified"}`, riskNames[item.risk] || riskNames.unclassified);
}
function confirmRisk(item) {
  if (item.risk === "read") return true;
  return confirm(`${riskNames[item.risk] || riskNames.unclassified}: "${item.title || "Historisk version"}". ` +
    "Kontrollera kommandot, mål, variabler och backup innan du använder det. Kopiera ändå?");
}
function refreshPersonal(entries) {
  personalItems = new Map(entries.map(entry => [entry.item_id, entry]));
}
async function downloadProject(project, button) {
  button.disabled = true;
  try {
    const response = await fetch(`/api/projects/${project.id}/export`);
    if (!response.ok) {
      const result = await response.json(); throw new Error(result.error || "Projektet kunde inte exporteras.");
    }
    const url = URL.createObjectURL(await response.blob());
    const link = el("a"); link.href = url; link.download = `project-${project.id}.zip`;
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000); notify("Projektets ZIP-export laddades ned.");
  } catch (failure) { showError(failure, $("#projects-error")); }
  finally { button.disabled = false; }
}
function appendPersonalFavorite(container, item) {
  const selected = Boolean(personalItems.get(item.id)?.favorite);
  const button = action(selected ? "♥" : "♡", `icon-button${selected ? " selected" : ""}`, async () => {
    button.disabled = true;
    try {
      await api(`/api/personal/${item.id}`, "PUT", {favorite:!selected});
      refreshPersonal(await api("/api/personal")); render();
    } catch (failure) { showError(failure); }
    finally { button.disabled = false; }
  });
  button.title = "Min personliga favorit";
  button.setAttribute("aria-label", selected ? "Ta bort min favorit" : "Spara som min favorit");
  button.setAttribute("aria-pressed", String(selected));
  container.append(button);
}
const dashboard = el("details", "workbench-dashboard"); dashboard.open = true;
dashboard.append(el("summary", "", "Min startsida"));
const dashboardBody = el("div", "dashboard-grid"); dashboard.append(dashboardBody);
$(".stats").before(dashboard);
const personalFilter = document.createElement("input"); personalFilter.type = "checkbox"; personalFilter.id = "filter-personal";
const reviewFilter = document.createElement("input"); reviewFilter.type = "checkbox"; reviewFilter.id = "filter-review";
const personalLabel = labeled("Mina favoriter", personalFilter); personalLabel.className = "checkbox";
const reviewLabel = labeled("Behöver granskas", reviewFilter); reviewLabel.className = "checkbox";
$(".filters").append(personalLabel, reviewLabel);
personalFilter.addEventListener("change", render); reviewFilter.addEventListener("change", render);
function workbenchMatches(item) {
  return (!personalFilter.checked || Boolean(personalItems.get(item.id)?.favorite)) &&
    (!reviewFilter.checked || item.status === "needs-update" || LibraryTools.reviewDue(item).due);
}
function renderDashboard() {
  const recent = [...personalItems.values()].filter(entry => entry.opened)
    .sort((a,b) => b.opened.localeCompare(a.opened)).map(entry => items.find(item => item.id === entry.item_id)).filter(Boolean);
  const favorites = items.filter(item => personalItems.get(item.id)?.favorite);
  const due = items.filter(item => item.status === "needs-update" || LibraryTools.reviewDue(item).due);
  dashboardBody.replaceChildren();
  for (const [title, entries] of [["Senast öppnade", recent], ["Mina favoriter", favorites], ["Behöver granskas", due]]) {
    const section = el("section"); section.append(el("h3", "", `${title} (${entries.length})`));
    entries.slice(0,5).forEach(item => section.append(action(item.title, "title-button", () => showDetail(item))));
    if (!entries.length) section.append(el("p", "muted", "Inga poster ännu."));
    dashboardBody.append(section);
  }
  const section = el("section"); section.append(el("h3", "", "Projektsamlingar"));
  projects.slice(0,5).forEach(project => section.append(action(
    `${project.name} (${items.filter(item => item.project_ids.includes(project.id)).length})`, "title-button", () => {
      active = "all"; $("#search").value = ""; $("#filter-project").value = String(project.id);
      personalFilter.checked = false; reviewFilter.checked = false; render();
    })));
  if (!projects.length) section.append(el("p", "muted", "Skapa ett projekt för att samla innehåll."));
  dashboardBody.append(section);
}

const riskInput = document.createElement("select"); riskInput.id = "editor-risk";
Object.entries(riskNames).forEach(([value, name]) => riskInput.append(option(value, name)));
const monthsInput = document.createElement("input"); monthsInput.type = "number"; monthsInput.min = "1";
monthsInput.max = "120"; monthsInput.required = true; monthsInput.id = "editor-review-months";
const reviewedInput = document.createElement("input"); reviewedInput.type = "date"; reviewedInput.id = "editor-reviewed-at";
const relatedChoices = el("fieldset", "account-form"); relatedChoices.id = "editor-related";
$("#existing-file").after(labeled("Riskklass (manuell bedömning)", riskInput),
  labeled("Granska igen efter antal månader", monthsInput), labeled("Senast granskad", reviewedInput), relatedChoices);
function populateWorkbenchEditor(item) {
  riskInput.value = item?.risk || "unclassified"; monthsInput.value = item?.review_months || "6";
  reviewedInput.value = item?.reviewed_at || "";
  relatedChoices.replaceChildren(el("legend", "", "Relaterade poster / förutsättningar"));
  const candidates = items.filter(entry => entry.id !== item?.id);
  candidates.forEach(entry => {
    const checkbox = document.createElement("input"); checkbox.type = "checkbox"; checkbox.value = entry.id;
    checkbox.checked = (item?.related_ids || []).includes(entry.id);
    const label = labeled(entry.title, checkbox); label.className = "checkbox"; relatedChoices.append(label);
  });
  (item?.related_ids || []).filter(id => !candidates.some(entry => entry.id === id)).forEach(id => {
    const checkbox = document.createElement("input"); checkbox.type = "checkbox"; checkbox.value = id; checkbox.checked = true;
    const label = labeled(`Otillgänglig post #${id} (avmarkera för att ta bort länken)`, checkbox);
    label.className = "checkbox"; relatedChoices.append(label);
  });
}
function workbenchEditorPayload() {
  return {risk:riskInput.value, review_months:monthsInput.value, reviewed_at:reviewedInput.value,
    related_ids:[...relatedChoices.querySelectorAll("input:checked")].map(input => Number(input.value))};
}
function appendWorkbenchTools(body, item) {
  body.append(riskBadge(item));
  const due = LibraryTools.reviewDue(item);
  body.append(el("p", due.due ? "review-warning" : "muted",
    `Nästa granskning: ${due.date} · intervall ${item.review_months} månader`));
  if (canEdit()) body.append(action("Markera granskad idag", "secondary", async event => {
    const button = event.currentTarget; button.disabled = true;
    try {
      await api(`/api/items/${item.id}`, "PUT", {...item, reviewed_at:new Date().toISOString().slice(0,10)});
      await load(); const updated = items.find(entry => entry.id === item.id);
      if (updated) showDetail(updated); notify("Granskningsdatum sparat. Teststatus ändrades inte.");
    } catch (failure) { showError(failure); }
    finally { button.disabled = false; }
  }));
  const favorites = el("div"); appendPersonalFavorite(favorites, item); body.append(favorites);
  if (item.related_ids.length) {
    body.append(el("h3", "", "Relaterade poster / förutsättningar"));
    item.related_ids.forEach(id => {
      const linked = items.find(entry => entry.id === id);
      body.append(linked ? action(linked.title, "small-button", () => showDetail(linked)) :
        el("p", "muted", `Post #${id} är borttagen eller finns i papperskorgen.`));
    });
  }
  if (item.filename !== null) body.append(action("Förhandsvisa bilaga", "secondary", () => previewAttachment(item)));
  api(`/api/personal/${item.id}`, "PUT", {opened:true}).then(() => api("/api/personal"))
    .then(entries => { refreshPersonal(entries); renderDashboard(); }).catch(failure => showError(failure));
}

const previewDialog = makeDialog("file-preview", "Säker filförhandsvisning");
previewDialog.addEventListener("close", () => {
  previewRevision += 1;
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = null; $("#file-preview-body").replaceChildren();
});
async function previewAttachment(item) {
  $("#file-preview-error").hidden = true; $("#file-preview-body").replaceChildren(el("p", "muted", "Läser fil…"));
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = null; const revision = ++previewRevision; previewDialog.showModal();
  try {
    if (item.filesize > 10 * 1024 * 1024) throw new Error("Förhandsvisning stöder högst 10 MB. Ladda ned större filer.");
    const response = await fetch(`/api/files/${item.id}`);
    if (!response.ok) throw new Error(`Filen kunde inte hämtas (${response.status}).`);
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (revision !== previewRevision || !previewDialog.open) return;
    const prefix = String.fromCharCode(...bytes.slice(0,12));
    const mime = bytes.length >= 8 && [137,80,78,71,13,10,26,10].every((n,i) => bytes[i] === n) ? "image/png" :
      bytes[0] === 255 && bytes[1] === 216 && bytes[2] === 255 ? "image/jpeg" :
      /^(GIF87a|GIF89a)/.test(prefix) ? "image/gif" :
      prefix.startsWith("RIFF") && prefix.slice(8,12) === "WEBP" ? "image/webp" : null;
    if (mime) {
      previewUrl = URL.createObjectURL(new Blob([bytes], {type:mime}));
      const image = el("img", "attachment-preview"); image.src = previewUrl; image.alt = item.filename;
      image.addEventListener("error", () => {
        if (revision === previewRevision) showError(new Error("Bildfilen är skadad eller kan inte visas."), $("#file-preview-error"));
      }); $("#file-preview-body").replaceChildren(image);
    } else {
      if (bytes.length > 2 * 1024 * 1024) throw new Error("Textförhandsvisning stöder högst 2 MB.");
      let text;
      try { text = new TextDecoder("utf-8", {fatal:true}).decode(bytes); }
      catch { throw new Error("Formatet stöds inte. Endast UTF-8-text och PNG/JPEG/GIF/WebP-bilder visas."); }
      if (text.includes("\0")) throw new Error("Binära filer kan inte visas som text.");
      const pre = el("pre", "detail-code", text);
      $("#file-preview-body").replaceChildren(el("p", "muted", "Visas endast som text. HTML och skript körs aldrig."), pre);
    }
  } catch (failure) { if (revision === previewRevision) showError(failure, $("#file-preview-error")); }
}

function appendHistoryComparison() {
  if (!currentHistory.length) return;
  const section = el("section", "account-form");
  const before = document.createElement("select"), after = document.createElement("select");
  before.setAttribute("aria-label", "Äldre version"); after.setAttribute("aria-label", "Nyare version");
  currentHistory.forEach(revision => {
    const name = `${formatDate(revision.created)} · ${revision.actor} · #${revision.id}`;
    before.append(option(revision.id, name)); after.append(option(revision.id, name));
  });
  before.value = String(currentHistory[Math.min(1,currentHistory.length-1)].id);
  const output = el("pre", "line-diff"); const error = el("p", "error"); error.hidden = true;
  const compare = action("Jämför kodtext rad för rad", "secondary", () => {
    error.hidden = true; output.replaceChildren();
    try {
      const a = currentHistory.find(r => String(r.id) === before.value), b = currentHistory.find(r => String(r.id) === after.value);
      const diff = LibraryTools.lineDiff(a.content, b.content);
      let oldLine = 0, newLine = 0;
      diff.forEach(line => {
        if (line.kind !== "add") oldLine += 1;
        if (line.kind !== "remove") newLine += 1;
        output.append(el("span", `diff-${line.kind}`,
          `${line.kind === "add" ? "+" : line.kind === "remove" ? "-" : " "} ${line.kind === "add" ? "-" : oldLine} / ${line.kind === "remove" ? "-" : newLine}  ${line.text}`));
      });
      if (!diff.some(line => line.kind !== "same")) output.prepend(el("p", "muted", "Kodtexten är identisk."));
    } catch (failure) { showError(failure, error); }
  });
  section.append(el("h3", "", "Versionsjämförelse"), labeled("Från", before), labeled("Till", after), compare, error, output);
  $("#history-list").prepend(section);
}

const guidesDialog = makeDialog("guides", "Checklistor & körguider");
const guideEditor = makeDialog("guide-editor", "Redigera körguide");
let editingGuide = null;
const guideForm = document.createElement("form");
function guideField(name, title, max, multiline = false) {
  const input = document.createElement(multiline ? "textarea" : "input"); input.name = name; input.maxLength = max;
  input.required = name === "title"; if (multiline) input.rows = 3;
  guideForm.append(labeled(title, input)); return input;
}
guideField("title", "Titel", 200); guideField("description", "Beskrivning", 5000, true);
guideField("prerequisites", "Förberedelser / krav / backup", 5000, true);
const stepRows = el("div", "guide-steps-editor");
guideForm.append(stepRows, action("Lägg till steg", "secondary", () => addStepRow()));
const saveGuideButton = el("button", "primary", "Spara guide"); saveGuideButton.type = "submit";
guideForm.append(saveGuideButton); $("#guide-editor-body").append(guideForm);
function addStepRow(step = null) {
  if (stepRows.children.length >= 100) { showError(new Error("Högst 100 steg."), $("#guide-editor-error")); return; }
  const row = el("div", "account-form"); if (step?.key) row.dataset.key = step.key;
  const text = document.createElement("textarea"); text.required = true; text.maxLength = 2000; text.value = step?.text || "";
  const link = document.createElement("select"); link.append(option("", "Ingen länkad post"));
  items.forEach(item => link.append(option(item.id, item.title)));
  if (step?.item_id && !items.some(item => item.id === step.item_id)) link.append(option(step.item_id, `Otillgänglig post #${step.item_id}`));
  link.value = String(step?.item_id || "");
  row.append(labeled("Stegets instruktion", text), labeled("Länk till kommando / fil", link),
    action("Flytta upp", "small-button", () => { if (row.previousElementSibling) row.previousElementSibling.before(row); }),
    action("Flytta ned", "small-button", () => { if (row.nextElementSibling) row.nextElementSibling.after(row); }),
    action("Ta bort steg", "danger-button", () => row.remove()));
  stepRows.append(row);
}
function editGuide(guide = null) {
  editingGuide = guide; guideForm.reset(); stepRows.replaceChildren(); $("#guide-editor-error").hidden = true;
  for (const field of ["title","description","prerequisites"]) guideForm.elements[field].value = guide?.[field] || "";
  if (guide) guide.steps.forEach(addStepRow); else addStepRow();
  guideEditor.showModal();
}
guideForm.addEventListener("submit", async event => {
  event.preventDefault(); saveGuideButton.disabled = true; $("#guide-editor-error").hidden = true;
  try {
    const payload = Object.fromEntries(["title","description","prerequisites"].map(name => [name, guideForm.elements[name].value]));
    payload.steps = [...stepRows.children].map(row => ({...(row.dataset.key ? {key:row.dataset.key} : {}),
      text:row.querySelector("textarea").value, item_id:Number(row.querySelector("select").value) || null}));
    await api(editingGuide ? `/api/guides/${editingGuide.id}` : "/api/guides", editingGuide ? "PUT" : "POST", payload);
    guideEditor.close(); await showGuides(); notify("Guiden sparades.");
  } catch (failure) { showError(failure, $("#guide-editor-error")); }
  finally { saveGuideButton.disabled = false; }
});
async function showGuides() {
  $("#guides-error").hidden = true;
  try {
    loadedGuides = await api("/api/guides"); const body = $("#guides-body"); body.replaceChildren();
    body.append(el("p", "muted", "Guider delas i biblioteket. Avbockade steg sparas bara för ditt konto. Inget kommando körs av sidan."));
    if (canEdit()) body.append(action("Skapa körguide", "primary", () => editGuide()));
    if (!loadedGuides.length) body.append(el("p", "muted", "Inga guider ännu."));
    loadedGuides.forEach(guide => {
      const section = el("section", "account-form");
      const heading = el("h3", "", `${guide.title} (${guide.completed.length}/${guide.steps.length})`);
      section.append(heading, el("p", "detail-notes", guide.description),
        el("h4", "", "Förberedelser"), el("p", "detail-notes", guide.prerequisites || "Inga angivna."));
      guide.steps.forEach((step, index) => {
        const row = el("div", "guide-step");
        const checkbox = document.createElement("input"); checkbox.type = "checkbox";
        checkbox.checked = guide.completed.includes(step.key); checkbox.dataset.key = step.key;
        const label = labeled(`${index + 1}. ${step.text}`, checkbox); label.className = "checkbox"; row.append(label);
        if (step.item_id) {
          const item = items.find(entry => entry.id === step.item_id);
          row.append(item ? action(item.title, "small-button", () => showDetail(item)) :
            el("p", "review-warning", `Länkad post #${step.item_id} är otillgänglig.`));
        }
        checkbox.addEventListener("change", async () => {
          const inputs = [...section.querySelectorAll("input")]; inputs.forEach(input => { input.disabled = true; });
          try {
            const completed = inputs.filter(input => input.checked).map(input => input.dataset.key);
            await api(`/api/guides/${guide.id}/progress`, "PUT", {completed});
            guide.completed = completed; heading.textContent = `${guide.title} (${completed.length}/${guide.steps.length})`;
          } catch (failure) {
            checkbox.checked = guide.completed.includes(step.key); showError(failure, $("#guides-error"));
          } finally { inputs.forEach(input => { input.disabled = false; }); }
        });
        section.append(row);
      });
      if (canEdit()) section.append(action("Redigera guide", "secondary", () => editGuide(guide)),
        action("Ta bort guide", "danger-button", async () => {
          if (!confirm(`Ta bort "${guide.title}" och allas avbockningar? Biblioteksposter behålls.`)) return;
          try { await api(`/api/guides/${guide.id}`, "DELETE"); await showGuides(); }
          catch (failure) { showError(failure, $("#guides-error")); }
        }));
      body.append(section);
    });
  } catch (failure) { showError(failure, $("#guides-error")); }
}
$(".toolbar").append(action("Checklistor & guider", "secondary", () => { guidesDialog.showModal(); showGuides(); }));

boot();
