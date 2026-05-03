const api = typeof messenger !== "undefined" ? messenger : browser;
const statusEl = document.getElementById("status");
const answerEl = document.getElementById("answer");

function setStatus(text) {
  statusEl.textContent = text;
}

async function loadSettings() {
  const saved = await api.storage.local.get(["baseUrl", "token", "model"]);
  document.getElementById("baseUrl").value = saved.baseUrl || "http://localhost:8765";
  document.getElementById("token").value = saved.token || "";
  document.getElementById("model").value = saved.model || "";
}

async function saveSettings() {
  await api.storage.local.set({
    baseUrl: document.getElementById("baseUrl").value.trim().replace(/\/$/, ""),
    token: document.getElementById("token").value.trim(),
    model: document.getElementById("model").value.trim()
  });
  setStatus("Saved.");
}

function partText(part) {
  if (!part) return "";
  if (part.body) return String(part.body);
  const children = Array.isArray(part.parts) ? part.parts : [];
  return children.map(partText).filter(Boolean).join("\n\n");
}

async function messageToSnippet(header) {
  const full = await api.messages.getFull(header.id);
  return {
    id: header.id,
    subject: header.subject || "",
    author: header.author || "",
    date: header.date ? new Date(header.date).toISOString() : "",
    folder: header.folder ? header.folder.name : "",
    body: partText(full).slice(0, 6000)
  };
}

async function currentMessageSnippet() {
  const tabs = await api.tabs.query({active: true, currentWindow: true});
  if (!tabs.length) throw new Error("No active Thunderbird tab.");
  const header = await api.messageDisplay.getDisplayedMessage(tabs[0].id);
  if (!header) throw new Error("No displayed message in the active tab.");
  return messageToSnippet(header);
}

async function searchSnippets(query) {
  if (!api.messages.query) {
    throw new Error("messages.query is not available in this Thunderbird version.");
  }
  const page = await api.messages.query({text: query});
  const headers = (page.messages || []).slice(0, 10);
  const snippets = [];
  for (const header of headers) {
    snippets.push(await messageToSnippet(header));
  }
  return snippets;
}

async function analyze(messages) {
  const saved = await api.storage.local.get(["baseUrl", "token", "model"]);
  const baseUrl = (saved.baseUrl || "http://localhost:8765").replace(/\/$/, "");
  const token = saved.token || "";
  if (!token) throw new Error("Paste and save the Thunderbird bridge token first.");
  const question = document.getElementById("question").value.trim();
  const response = await fetch(`${baseUrl}/api/thunderbird/analyze`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      token,
      model: saved.model || "",
      question,
      messages
    })
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.ok) throw new Error(data.error || `HTTP ${response.status}`);
  answerEl.textContent = data.text || "";
  setStatus(`Analyzed ${data.messages_used || messages.length} message(s) with ${data.model || "model"}.`);
}

document.getElementById("save").addEventListener("click", () => {
  saveSettings().catch(err => setStatus(String(err)));
});

document.getElementById("current").addEventListener("click", async () => {
  try {
    setStatus("Reading current message...");
    const snippet = await currentMessageSnippet();
    setStatus("Sending message snippet to Command Deck...");
    await analyze([snippet]);
  } catch (err) {
    setStatus(String(err));
  }
});

document.getElementById("search").addEventListener("click", async () => {
  try {
    const query = document.getElementById("query").value.trim();
    if (!query) throw new Error("Enter a search query.");
    setStatus("Searching Thunderbird...");
    const snippets = await searchSnippets(query);
    if (!snippets.length) throw new Error("No messages found.");
    setStatus("Sending search results to Command Deck...");
    await analyze(snippets);
  } catch (err) {
    setStatus(String(err));
  }
});

loadSettings().catch(err => setStatus(String(err)));
