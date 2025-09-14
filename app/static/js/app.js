async function addTask() {
  const path = document.getElementById("pathInput").value;
  const res = await fetch("/api/add", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path })
  });
  if (res.ok) {
    loadQueue();
  } else {
    alert("添加失败");
  }
}

async function loadQueue() {
  const res = await fetch("/api/queue");
  const data = await res.json();
  const list = document.getElementById("queue");
  list.innerHTML = "";
  data.queue.forEach(item => {
    const li = document.createElement("li");
    li.innerText = item.path;
    list.appendChild(li);
  });
}

function initLogStream() {
  const evt = new EventSource("/stream");
  const logElem = document.getElementById("log");
  evt.onmessage = (e) => {
    logElem.textContent += e.data + "\n";
    logElem.scrollTop = logElem.scrollHeight;
  };
}

window.onload = () => {
  loadQueue();
  initLogStream();
};
