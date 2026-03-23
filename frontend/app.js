const messagesEl = document.getElementById("messages");
const formEl = document.getElementById("chat-form");
const inputEl = document.getElementById("chat-input");
const inspectorEl = document.getElementById("inspector");
const sqlPreviewEl = document.getElementById("sql-preview");
const entityCountEl = document.getElementById("entity-count");
const tableCountEl = document.getElementById("table-count");
const llmStatusEl = document.getElementById("llm-status");

let cy;

function addMessage(role, content, suggestions = []) {
  const wrapper = document.createElement("article");
  wrapper.className = `message ${role}`;

  const header = document.createElement("div");
  header.className = "message-header";
  header.textContent = role === "user" ? "You" : "Dataset Assistant";

  const body = document.createElement("pre");
  body.textContent = content;

  wrapper.append(header, body);

  if (role === "assistant" && suggestions.length) {
    const suggestionStrip = document.createElement("div");
    suggestionStrip.className = "inline-suggestions";
    suggestions.forEach((suggestion) => {
      const button = document.createElement("button");
      button.className = "sample-prompt";
      button.type = "button";
      button.textContent = suggestion;
      button.addEventListener("click", () => runQuery(suggestion));
      suggestionStrip.append(button);
    });
    wrapper.append(suggestionStrip);
  }

  messagesEl.prepend(wrapper);
}

function initGraph(graph) {
  const container = document.getElementById("graph");
  const elements = [
    ...graph.nodes.map((node) => ({ data: node })),
    ...graph.edges.map((edge) => ({ data: edge })),
  ];

  if (cy) {
    cy.destroy();
  }

  cy = cytoscape({
    container,
    elements,
    style: [
      {
        selector: "node",
        style: {
          "background-color": "#19494d",
          color: "#ffffff",
          label: "data(label)",
          "font-family": "Space Grotesk",
          "font-size": 12,
          "text-wrap": "wrap",
          "text-max-width": 120,
          "text-valign": "center",
          width: 48,
          height: 48,
          "border-width": 2,
          "border-color": "#f5e9d7",
        },
      },
      { selector: 'node[type = "sales_order"]', style: { "background-color": "#19494d" } },
      { selector: 'node[type = "sales_order_item"]', style: { "background-color": "#356b70" } },
      { selector: 'node[type = "delivery"]', style: { "background-color": "#337357" } },
      { selector: 'node[type = "delivery_item"]', style: { "background-color": "#4f9a6f" } },
      { selector: 'node[type = "billing_document"]', style: { "background-color": "#a63d2f" } },
      { selector: 'node[type = "billing_item"]', style: { "background-color": "#d46d45" } },
      { selector: 'node[type = "journal_entry"]', style: { "background-color": "#926c15" } },
      { selector: 'node[type = "payment"]', style: { "background-color": "#c79b2b" } },
      { selector: 'node[type = "product"]', style: { "background-color": "#5f3dc4" } },
      { selector: 'node[type = "customer"]', style: { "background-color": "#7b4f99" } },
      { selector: 'node[type = "plant"]', style: { "background-color": "#804e2d" } },
      {
        selector: 'node[type = "entity_type"]',
        style: {
          shape: "round-rectangle",
          width: 122,
          height: 54,
          "background-color": "#fff7eb",
          color: "#191610",
          "border-color": "#d7c9af",
        },
      },
      {
        selector: 'node[type = "metric"]',
        style: {
          shape: "diamond",
          width: 68,
          height: 68,
          "background-color": "#f3d2bc",
          color: "#7e2d20",
          "border-color": "#f8efe4",
        },
      },
      {
        selector: "node[highlight = 1]",
        style: {
          "border-width": 5,
          "border-color": "#fff2a8",
          "shadow-blur": 28,
          "shadow-color": "#f4d35e",
          "shadow-opacity": 0.8,
        },
      },
      {
        selector: "edge",
        style: {
          width: 2,
          label: "data(label)",
          "curve-style": "bezier",
          "target-arrow-shape": "triangle",
          "line-color": "#7f7668",
          "target-arrow-color": "#7f7668",
          color: "#615a4f",
          "font-size": 10,
          "font-family": "IBM Plex Mono",
          "text-background-color": "#fff9ef",
          "text-background-opacity": 1,
          "text-background-padding": 2,
        },
      },
    ],
    layout: {
      name: graph.nodes.some((node) => node.type === "entity_type") ? "breadthfirst" : "cose",
      animate: true,
      fit: true,
      padding: 36,
      spacingFactor: 1.1,
    },
  });

  cy.on("tap", "node", async (event) => {
    const node = event.target.data();
    inspectorEl.textContent = JSON.stringify(node.metadata || node, null, 2);

    if (["sales_order", "billing_document", "delivery", "product", "customer", "plant"].includes(node.type)) {
      const entityKey = node.id.split(":").slice(1).join(":");
      try {
        const response = await fetch(`/api/entity/${node.type}/${entityKey}`);
        if (response.ok) {
          const payload = await response.json();
          inspectorEl.textContent = JSON.stringify(payload, null, 2);
        }
      } catch (error) {
        console.error(error);
      }
    }
  });
}

async function bootstrap() {
  const response = await fetch("/api/bootstrap");
  const payload = await response.json();
  entityCountEl.textContent = Object.keys(payload.metadata.entities).length;
  tableCountEl.textContent = Object.keys(payload.metadata.tables).length;
  llmStatusEl.textContent = payload.llmEnabled ? "Enabled" : "Template mode";
  initGraph(payload.overviewGraph);
  addMessage(
    "assistant",
    "The dataset has been loaded. Ask about billed products, top customers, open billing documents, incomplete flows, or trace a document through the O2C lifecycle.",
    [
      "Which customers have the highest billed amount?",
      "Show unpaid billing documents",
      "Which plants shipped the highest delivery volume?",
    ]
  );
}

async function runQuery(prompt) {
  addMessage("user", prompt);
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: prompt }),
  });
  const payload = await response.json();
  addMessage("assistant", payload.answer, payload.suggestions || []);
  sqlPreviewEl.textContent = payload.query.sql || "No SQL executed.";
  inspectorEl.textContent = payload.query.rows.length
    ? JSON.stringify(payload.query.rows.slice(0, 5), null, 2)
    : "No rows returned.";
  if (payload.graph?.nodes?.length) {
    initGraph(payload.graph);
  }
}

formEl.addEventListener("submit", async (event) => {
  event.preventDefault();
  const prompt = inputEl.value.trim();
  if (!prompt) {
    return;
  }
  inputEl.value = "";
  await runQuery(prompt);
});

document.querySelectorAll(".sample-prompt").forEach((button) => {
  button.addEventListener("click", async () => {
    const prompt = button.dataset.prompt;
    inputEl.value = prompt;
    await runQuery(prompt);
  });
});

bootstrap().catch((error) => {
  console.error(error);
  addMessage("assistant", "Bootstrap failed. Check the backend logs and dataset paths.");
});
