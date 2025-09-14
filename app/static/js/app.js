\
        document.addEventListener("DOMContentLoaded", function () {
          const src = document.getElementById("src");
          const dest = document.getElementById("dest");
          const addBtn = document.getElementById("add");
          const qDiv = document.getElementById("queue");
          const log = document.getElementById("log");
          const filterImages = document.getElementById("filter_images");
          const filterNfo = document.getElementById("filter_nfo");

          addBtn.onclick = async () => {
            const s = src.value.trim(), d = dest.value.trim();
            if (!s || !d) { alert("请填写 src 和 dest"); return; }
            addBtn.disabled = true;
            try {
              const res = await fetch("/api/add", {
                method: "POST",
                headers: {"Content-Type":"application/json"},
                body: JSON.stringify({src:s,dest:d,filter_images:filterImages.checked,filter_nfo:filterNfo.checked})
              });
              const data = await res.json();
              if (!data.ok) alert("添加失败: " + (data.error || ""));
              else { src.value=""; dest.value=""; refreshQueue(); }
            } catch (e) {
              alert("请求失败: " + e);
            } finally { addBtn.disabled = false; }
          };

          async function refreshQueue(){
            try {
              const res = await fetch("/api/queue");
              const j = await res.json();
              const arr = j.queue || [];
              qDiv.innerHTML = arr.length ? "" : "<div>队列为空</div>";
              arr.forEach((it, i) => {
                const el = document.createElement("div");
                el.className = "task";
                el.innerHTML = `<strong>#${i+1}</strong><div>src: ${it.src}</div><div>dest: ${it.dest}</div>`;
                qDiv.appendChild(el);
              });
            } catch (e) { qDiv.textContent = "获取队列失败: " + e; }
          }

          const evt = new EventSource("/stream");
          evt.onmessage = (e) => {
            log.textContent += e.data + "\n";
            window.scrollTo(0, document.body.scrollHeight);
          };
          evt.onerror = () => console.warn("SSE 断开，浏览器会自动重连");

          refreshQueue();
        });
