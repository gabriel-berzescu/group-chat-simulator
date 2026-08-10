const messagesList = document.getElementById("messages");
const form = document.getElementById("chat-form");
const input = document.getElementById("chat-input");
const roster = document.getElementById("roster");

let personas = {};
let waitingForReply = false;

async function loadPersonas() {
  const response = await fetch("/api/personas");
  const list = await response.json();
  personas = Object.fromEntries(list.map((p) => [p.id, p]));
  roster.textContent = list.map((p) => `${p.emoji} ${p.name}`).join(" · ");
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

  if (!isMine) {
    const avatar = document.createElement("span");
    avatar.className = "avatar";
    avatar.textContent = persona?.emoji ?? "🤖";
    item.appendChild(avatar);
  }

  const bubble = document.createElement("div");
  bubble.className = "bubble";

  if (!isMine) {
    const author = document.createElement("span");
    author.className = "author";
    author.textContent = persona?.name ?? message.author;
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

function renderTypingIndicator() {
  const item = document.createElement("li");
  item.className = "message theirs typing";
  item.innerHTML =
    '<span class="avatar">🤖</span>' +
    '<div class="bubble"><span class="dot"></span><span class="dot"></span><span class="dot"></span></div>';
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
  const response = await fetch("/api/messages");
  const messages = await response.json();

  const wasNearBottom =
    messagesList.scrollHeight - messagesList.scrollTop - messagesList.clientHeight < 80;

  const items = messages.length ? messages.map(renderMessage) : [renderEmptyState()];
  if (waitingForReply) items.push(renderTypingIndicator());
  messagesList.replaceChildren(...items);

  if (wasNearBottom) {
    messagesList.scrollTop = messagesList.scrollHeight;
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text || waitingForReply) return;

  input.value = "";
  waitingForReply = true;
  try {
    await fetch("/api/messages", {
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

loadPersonas();
refreshMessages();
setInterval(refreshMessages, 1500);
