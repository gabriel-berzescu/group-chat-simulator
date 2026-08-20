const messagesList = document.getElementById("messages");
const form = document.getElementById("chat-form");
const input = document.getElementById("chat-input");
const chatSubtitle = document.getElementById("chat-subtitle");
const personaList = document.getElementById("persona-list");
const conversationList = document.getElementById("conversation-list");
const newConversationButton = document.getElementById("new-conversation");
const backdrop = document.getElementById("backdrop");

let personas = {};
let waitingForReply = false;
let currentConversationId = null;
let conversationsSignature = null;

async function loadPersonas() {
  const response = await fetch("/api/personas");
  const list = await response.json();
  personas = Object.fromEntries(list.map((p) => [p.id, p]));

  personaList.replaceChildren(
    ...list.map((persona) => {
      const item = document.createElement("li");
      item.className = "persona-item";

      const avatar = document.createElement("span");
      avatar.className = "avatar";
      avatar.textContent = persona.emoji;
      if (persona.color) avatar.style.borderColor = persona.color;

      const name = document.createElement("span");
      name.className = "name";
      name.textContent = persona.name;
      if (persona.color) name.style.color = persona.color;

      item.append(avatar, name);
      return item;
    })
  );
  chatSubtitle.textContent = `${list.length} personaje în grup`;
}

function formatConversationDate(conversation) {
  const created = new Date(conversation.created_at);
  return created.toLocaleString("ro-RO", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function conversationLabel(conversation) {
  return conversation.title || formatConversationDate(conversation);
}

// Cât un meniu e deschis sau se redenumește, polling-ul nu are voie să
// re-randeze lista — altfel ar șterge exact elementul cu care lucrezi.
function listIsBusy() {
  return Boolean(conversationList.querySelector(".menu-open, .renaming"));
}

function closeMenus() {
  for (const item of conversationList.querySelectorAll(".menu-open")) {
    item.classList.remove("menu-open", "confirming");
  }
}

// Meniul e position:fixed, ca să nu-l taie scroll-ul listei; îl așezăm
// sub kebab, sau deasupra lui dacă n-are loc până jos.
function positionMenu(kebab, menu) {
  const anchor = kebab.getBoundingClientRect();
  const { width, height } = menu.getBoundingClientRect();
  const below = anchor.bottom + 4;
  const top = below + height + 8 > window.innerHeight ? anchor.top - height - 4 : below;
  menu.style.top = `${Math.max(8, top)}px`;
  menu.style.left = `${Math.min(anchor.right - width, window.innerWidth - width - 8)}px`;
}

function menuButton(label, icon, className, onClick) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.append(icon + " " + label);
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    onClick();
  });
  return button;
}

function startRename(item, conversation) {
  closeMenus();
  item.classList.add("renaming");

  const label = item.querySelector(".label");
  const input = document.createElement("input");
  input.className = "rename-input";
  input.type = "text";
  input.maxLength = 80;
  input.value = conversationLabel(conversation);
  label.replaceWith(input);
  input.focus();
  input.select();

  let finished = false;
  const finish = async (save) => {
    if (finished) return;
    finished = true;
    const title = input.value.trim();
    item.classList.remove("renaming");
    if (save && title !== conversationLabel(conversation)) {
      await fetch(`/api/conversations/${conversation.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      });
    }
    conversationsSignature = null; // forțăm re-randarea listei
    loadConversations();
  };

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") finish(true);
    if (event.key === "Escape") finish(false);
  });
  input.addEventListener("blur", () => finish(true));
  input.addEventListener("click", (event) => event.stopPropagation());
}

async function deleteConversation(conversationId) {
  await fetch(`/api/conversations/${conversationId}`, { method: "DELETE" });
  closeMenus();
  // dacă am șters-o pe cea deschisă, loadConversations alege cea mai recentă
  if (conversationId === currentConversationId) currentConversationId = null;
  conversationsSignature = null;
  await loadConversations();
  refreshMessages();
}

function renderConversationItem(conversation) {
  const item = document.createElement("li");
  item.className = "conversation-item";
  item.dataset.id = conversation.id;
  if (conversation.id === currentConversationId) item.classList.add("active");

  const open = document.createElement("button");
  open.type = "button";
  open.className = "conversation-open";

  const icon = document.createElement("span");
  icon.className = "icon";
  icon.textContent = "💬";

  const label = document.createElement("span");
  label.className = "label";
  label.textContent = conversationLabel(conversation);
  label.title = conversationLabel(conversation);

  const count = document.createElement("span");
  count.className = "count";
  count.textContent = conversation.message_count;

  open.append(icon, label, count);
  open.addEventListener("click", () => selectConversation(conversation.id));

  const kebab = document.createElement("button");
  kebab.type = "button";
  kebab.className = "kebab";
  kebab.title = "Opțiuni";
  kebab.textContent = "⋮";
  kebab.addEventListener("click", (event) => {
    event.stopPropagation();
    const wasOpen = item.classList.contains("menu-open");
    closeMenus();
    if (wasOpen) return;
    item.classList.add("menu-open");
    positionMenu(kebab, menu);
  });

  const menu = document.createElement("div");
  menu.className = "menu";
  menu.addEventListener("click", (event) => event.stopPropagation());

  const actions = document.createElement("div");
  actions.className = "menu-actions";
  actions.append(
    menuButton("Redenumește", "✏️", "", () => startRename(item, conversation)),
    menuButton("Șterge", "🗑️", "danger", () => {
      item.classList.add("confirming");
      positionMenu(kebab, menu); // confirmarea are altă înălțime
    })
  );

  const confirm = document.createElement("div");
  confirm.className = "menu-confirm";
  const question = document.createElement("p");
  question.textContent = "Ștergi conversația?";
  confirm.append(
    question,
    menuButton("Da, șterge", "🗑️", "danger", () => deleteConversation(conversation.id)),
    menuButton("Renunță", "↩️", "", closeMenus)
  );

  menu.append(actions, confirm);
  item.append(open, kebab, menu);
  return item;
}

function selectConversation(conversationId) {
  closeMenus();
  if (conversationId === currentConversationId) return closeDrawers();
  currentConversationId = conversationId;
  for (const item of conversationList.children) {
    item.classList.toggle("active", item.dataset.id === conversationId);
  }
  closeDrawers();
  refreshMessages();
}

async function loadConversations() {
  const response = await fetch("/api/conversations");
  const list = await response.json();

  // cea mai recentă e prima; o selectăm dacă nu avem deja una validă
  if (!list.some((c) => c.id === currentConversationId)) {
    currentConversationId = list[0]?.id ?? null;
  }

  // re-randăm doar când lista chiar s-a schimbat, ca să nu clipească la polling
  const signature = JSON.stringify([
    currentConversationId,
    list.map((c) => [c.id, c.title, c.message_count]),
  ]);
  if (signature === conversationsSignature || listIsBusy()) return;
  conversationsSignature = signature;

  conversationList.replaceChildren(...list.map(renderConversationItem));
}

function closeDrawers() {
  for (const el of document.querySelectorAll(".sidebar.open, #backdrop.open")) {
    el.classList.remove("open");
  }
}

function toggleDrawer(sidebar) {
  const willOpen = !sidebar.classList.contains("open");
  closeDrawers();
  sidebar.classList.toggle("open", willOpen);
  backdrop.classList.toggle("open", willOpen);
}

function formatTime(timestamp) {
  return timestamp?.slice(11, 16) ?? "";
}

// Mic renderer de Markdown pentru răspunsurile modelului: escapează HTML-ul,
// apoi suportă **bold**, *italic*, `cod`, blocuri ```, liste și titluri.
function renderMarkdown(raw) {
  const escapeHtml = (s) =>
    s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  const codeBlocks = [];
  const withPlaceholders = raw.replace(/```\w*\n?([\s\S]*?)```/g, (_, code) => {
    codeBlocks.push(`<pre><code>${escapeHtml(code.trimEnd())}</code></pre>`);
    return `\n%%CODEBLOCK${codeBlocks.length - 1}%%\n`;
  });

  const inline = (s) =>
    s
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/\*([^*]+)\*/g, "<em>$1</em>");

  const html = [];
  let listTag = null;
  let paragraph = [];

  const flushParagraph = () => {
    if (paragraph.length) {
      html.push(`<p>${inline(paragraph.join("<br>"))}</p>`);
      paragraph = [];
    }
  };
  const closeList = () => {
    if (listTag) {
      html.push(`</${listTag}>`);
      listTag = null;
    }
  };

  for (const line of escapeHtml(withPlaceholders).split("\n")) {
    const trimmed = line.trim();
    const codeRef = /^%%CODEBLOCK(\d+)%%$/.exec(trimmed);
    const bullet = /^[-*+]\s+(.*)/.exec(trimmed);
    const numbered = /^\d+[.)]\s+(.*)/.exec(trimmed);
    const heading = /^#{1,4}\s+(.*)/.exec(trimmed);
    const rule = /^([-*_])\1{2,}$/.test(trimmed);

    if (rule) {
      flushParagraph();
      closeList();
      html.push("<hr>");
    } else if (codeRef) {
      flushParagraph();
      closeList();
      html.push(codeBlocks[Number(codeRef[1])]);
    } else if (bullet || numbered) {
      flushParagraph();
      const tag = bullet ? "ul" : "ol";
      if (listTag !== tag) {
        closeList();
        html.push(`<${tag}>`);
        listTag = tag;
      }
      html.push(`<li>${inline((bullet ?? numbered)[1])}</li>`);
    } else if (heading) {
      flushParagraph();
      closeList();
      html.push(`<p class="heading">${inline(heading[1])}</p>`);
    } else if (!trimmed) {
      flushParagraph();
      closeList();
    } else {
      closeList();
      paragraph.push(trimmed);
    }
  }
  flushParagraph();
  closeList();
  return html.join("");
}

function renderMessage(message) {
  const persona = personas[message.author];
  const isMine = message.author === "user";

  const item = document.createElement("li");
  item.className = `message ${isMine ? "mine" : "theirs"}`;

  const color = persona?.color;

  if (!isMine) {
    const avatar = document.createElement("span");
    avatar.className = "avatar";
    avatar.textContent = persona?.emoji ?? "🤖";
    if (color) avatar.style.borderColor = color;
    item.appendChild(avatar);
  }

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  if (!isMine && color) {
    bubble.style.background = `color-mix(in srgb, ${color} 10%, var(--bubble-theirs))`;
  }

  if (!isMine) {
    const author = document.createElement("span");
    author.className = "author";
    author.textContent = persona?.name ?? message.author;
    if (color) author.style.color = color;
    bubble.appendChild(author);
  }

  if (isMine) {
    bubble.appendChild(document.createTextNode(message.text));
  } else {
    const body = document.createElement("div");
    body.className = "md";
    body.innerHTML = renderMarkdown(message.text);
    bubble.appendChild(body);
  }

  const time = document.createElement("span");
  time.className = "time";
  time.textContent = formatTime(message.timestamp);
  bubble.appendChild(time);

  item.appendChild(bubble);
  return item;
}

function renderTypingIndicator(personaId) {
  const persona = personas[personaId];
  const item = document.createElement("li");
  item.className = "message theirs typing";
  item.innerHTML =
    '<span class="avatar"></span>' +
    '<div class="bubble"><span class="dot"></span><span class="dot"></span><span class="dot"></span></div>';
  const avatar = item.querySelector(".avatar");
  avatar.textContent = persona?.emoji ?? "🤖";
  if (persona?.color) avatar.style.borderColor = persona.color;
  return item;
}

function renderEmptyState() {
  const item = document.createElement("li");
  item.className = "empty";
  item.innerHTML =
    '<span class="big">👋</span>Niciun mesaj încă.<br>Scrie ceva și pornește conversația!';
  return item;
}

async function refreshMessages() {
  if (!currentConversationId) return;

  const conversationId = currentConversationId;
  const response = await fetch(`/api/conversations/${conversationId}/messages`);
  const { messages, typing } = await response.json();

  // utilizatorul a comutat conversația cât timp așteptam răspunsul
  if (conversationId !== currentConversationId) return;

  const wasNearBottom =
    messagesList.scrollHeight - messagesList.scrollTop - messagesList.clientHeight < 80;

  const items = messages.length ? messages.map(renderMessage) : [renderEmptyState()];
  // backend-ul știe cine scrie (inclusiv la postările automate); până află
  // polling-ul, arătăm indicatorul generic cât așteptăm propriul POST
  if (typing || waitingForReply) items.push(renderTypingIndicator(typing));
  messagesList.replaceChildren(...items);

  if (wasNearBottom) {
    messagesList.scrollTop = messagesList.scrollHeight;
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text || waitingForReply || !currentConversationId) return;

  input.value = "";
  waitingForReply = true;
  try {
    await fetch(`/api/conversations/${currentConversationId}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
  } finally {
    waitingForReply = false;
    input.focus();
  }
  refreshMessages();
});

newConversationButton.addEventListener("click", async () => {
  const response = await fetch("/api/conversations", { method: "POST" });
  const created = await response.json();
  currentConversationId = created.id;
  await loadConversations();
  closeDrawers();
  refreshMessages();
  input.focus();
});

document
  .getElementById("toggle-conversations")
  .addEventListener("click", () => toggleDrawer(document.getElementById("conversations-sidebar")));
document
  .getElementById("toggle-personas")
  .addEventListener("click", () => toggleDrawer(document.getElementById("personas-sidebar")));
backdrop.addEventListener("click", closeDrawers);
document.addEventListener("click", closeMenus);
conversationList.addEventListener("scroll", closeMenus);

async function init() {
  loadPersonas();
  await loadConversations();
  refreshMessages();
  setInterval(() => {
    refreshMessages();
    loadConversations();
  }, 1500);
}

init();
