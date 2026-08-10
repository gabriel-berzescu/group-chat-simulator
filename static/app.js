const messagesList = document.getElementById("messages");
const form = document.getElementById("chat-form");
const input = document.getElementById("chat-input");

async function refreshMessages() {
  const response = await fetch("/api/messages");
  const messages = await response.json();

  messagesList.replaceChildren(
    ...messages.map((message) => {
      const item = document.createElement("li");
      item.textContent = `${message.author}: ${message.text}`;
      return item;
    })
  );
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text) return;

  input.value = "";
  input.disabled = true;
  try {
    await fetch("/api/messages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
  } finally {
    input.disabled = false;
    input.focus();
  }
  refreshMessages();
});

refreshMessages();
setInterval(refreshMessages, 1500);
