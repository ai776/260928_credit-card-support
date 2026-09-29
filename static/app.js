const samples = [
  ["盗難・紛失", "財布を落としてカードが見当たりません。すぐに止めてください。"],
  ["登録情報", "引っ越ししたので登録住所を変えてください。"],
  ["身に覚えのない請求", "先月、知らない店で3万円の請求があります。"],
  ["明細", "今月の引き落としがいつもより多いです。明細の見方を教えてください。"],
  ["限度額", "海外旅行の前に限度額を一時的に上げたいです。"],
  ["ポイント", "ポイントの有効期限はいつですか。"],
];

const log = document.querySelector("#log");
const form = document.querySelector("#composer");
const message = document.querySelector("#message");
const send = document.querySelector("#send");
const verdict = document.querySelector("#verdict");
const sampleBox = document.querySelector("#samples");
const engineLine = document.querySelector("#engine-line");

let sessionId = null;

samples.forEach(([label, text]) => {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  button.addEventListener("click", () => {
    message.value = text;
    message.focus();
  });
  sampleBox.appendChild(button);
});

addBubble(
  "assistant",
  "アオカード会員サポートです。ご用件をどうぞ。カード番号や暗証番号は書かないでください。利用停止や登録変更そのものは、この画面では実行しません。",
);

fetch("/api/health")
  .then((response) => response.json())
  .then((health) => {
    const judge = health.jev ? "Jev" : "下書き判断";
    const writer = health.generation ? "文章生成API" : "カテゴリ専用の定型文";
    engineLine.textContent = `判断は${judge}、文章は${writer}`;
  })
  .catch(() => {});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = message.value.trim();
  if (!text) return;
  addBubble("user", text);
  message.value = "";
  send.disabled = true;
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, session_id: sessionId }),
    });
    if (!response.ok) throw new Error("送信に失敗しました");
    const data = await response.json();
    sessionId = data.session_id;
    addBubble("assistant", data.reply);
    renderVerdict(data);
  } catch (error) {
    addBubble("assistant", "いま応答できませんでした。しばらくしてからもう一度送ってください。");
  } finally {
    send.disabled = false;
    message.focus();
  }
});

function addBubble(role, text) {
  const item = document.createElement("article");
  item.className = `bubble ${role}`;
  const who = document.createElement("span");
  who.className = "who";
  who.textContent = role === "user" ? "あなた" : "サポート";
  item.append(who, document.createTextNode(text));
  log.appendChild(item);
  log.scrollTop = log.scrollHeight;
}

function renderVerdict(data) {
  const judgment = data.judgment;
  verdict.classList.remove("empty");
  verdict.replaceChildren();

  const route = document.createElement("p");
  route.className = `route ${data.route}`;
  route.textContent = data.route_label;

  const reason = document.createElement("p");
  reason.className = "reason";
  reason.textContent = data.reason;

  const meta = document.createElement("p");
  meta.className = "meta";
  const engine = judgment.engine === "jev" ? "Jev" : "下書き判断";
  meta.textContent = `${engine} / ${judgment.latency_ms} ms / ${judgment.category.label}`;

  const bars = document.createElement("div");
  bars.className = "bars";
  const probabilities = Object.entries(judgment.category.probabilities).sort((a, b) => b[1] - a[1]);
  probabilities.forEach(([key, value]) => {
    const row = document.createElement("div");
    row.className = "bar-row";
    if (key === judgment.category.choice) row.classList.add("winner");
    const name = document.createElement(key === judgment.category.choice ? "strong" : "span");
    name.textContent = labelFor(key);
    const track = document.createElement("div");
    track.className = "track";
    const fill = document.createElement("div");
    fill.className = "fill";
    fill.style.width = `${Math.round(value * 100)}%`;
    track.appendChild(fill);
    const num = document.createElement("span");
    num.textContent = value.toFixed(2);
    row.append(name, track, num);
    bars.appendChild(row);
  });

  const nums = document.createElement("div");
  nums.className = "nums";
  nums.append(
    stat("確信度", judgment.category.confidence.toFixed(2)),
    stat("緊急度", judgment.urgency.label),
    stat("人へ渡す確率", judgment.handoff_probability.toFixed(2)),
    stat("不足の確率", judgment.missing_info_probability.toFixed(2)),
    stat("調子", judgment.tone.label),
    stat("文章", data.generation.specialist_label),
  );

  verdict.append(route, reason, meta, bars, nums);
  if (judgment.note) {
    const note = document.createElement("p");
    note.className = "note";
    note.textContent = judgment.note;
    verdict.appendChild(note);
  }

  document.querySelector("#pipe-judge").classList.add("on");
  document.querySelector("#pipe-route").classList.add("on");
  document.querySelector("#pipe-write").classList.add("on");
}

function stat(label, value) {
  const box = document.createElement("div");
  const span = document.createElement("span");
  span.textContent = label;
  const strong = document.createElement("b");
  strong.textContent = value;
  box.append(span, strong);
  return box;
}

function labelFor(key) {
  return (
    {
      card_lost: "盗難・紛失",
      profile_change: "登録情報",
      statement: "明細・請求",
      unrecognized_charge: "身に覚えのない利用",
      credit_limit: "限度額",
      points: "ポイント",
      other: "その他",
    }[key] || key
  );
}
