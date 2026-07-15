(() => {
  "use strict";

  const pressure = document.querySelector("#pressure");
  const memoryValue = document.querySelector("#memory-value");
  const historyValue = document.querySelector("#history-value");
  const memoryBar = document.querySelector("#memory-bar");
  const historyBar = document.querySelector("#history-bar");
  const budgetReadout = document.querySelector("#budget-readout");
  const event = document.querySelector("#demo-event");
  const memorySegment = document.querySelector(".memory-segment");
  const historySegment = document.querySelector(".history-segment");
  const slackSegment = document.querySelector(".slack-segment");
  const total = 8192;
  const system = 1024;

  const format = new Intl.NumberFormat("en-US");

  function renderAllocation() {
    if (!pressure) return;
    const value = Number(pressure.value);
    const history = 1536 + Math.round(value * 28.16);
    const memoryRequested = 3072;
    const memory = Math.max(1280, Math.min(memoryRequested, total - system - history - 512));
    const used = system + history + memory;
    const reclaimed = memoryRequested - memory;
    const slack = Math.max(0, total - used);

    memoryValue.textContent = format.format(memory);
    historyValue.textContent = format.format(history);
    budgetReadout.textContent = `${format.format(used)} / ${format.format(total)}`;
    memoryBar.style.setProperty("--width", `${Math.min(100, memory / memoryRequested * 100)}%`);
    historyBar.style.setProperty("--width", `${Math.min(100, history / 4352 * 100)}%`);
    memorySegment.style.width = `${memory / total * 100}%`;
    historySegment.style.width = `${history / total * 100}%`;
    slackSegment.style.width = `${slack / total * 100}%`;

    const label = event.querySelector("b");
    if (reclaimed > 0) {
      event.childNodes[1].textContent = " lease.reclaimed ";
      label.textContent = `memory −${format.format(reclaimed)}`;
    } else {
      event.childNodes[1].textContent = " lease.granted ";
      label.textContent = "memory +768";
    }
  }

  pressure?.addEventListener("input", renderAllocation);
  renderAllocation();

  const toast = document.querySelector("#toast");
  let toastTimer;
  document.querySelectorAll(".copy-command").forEach((button) => {
    button.addEventListener("click", async () => {
      const command = button.dataset.command || "";
      try {
        await navigator.clipboard.writeText(command);
      } catch {
        const textarea = document.createElement("textarea");
        textarea.value = command;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.append(textarea);
        textarea.select();
        document.execCommand("copy");
        textarea.remove();
      }
      toast.classList.add("visible");
      window.clearTimeout(toastTimer);
      toastTimer = window.setTimeout(() => toast.classList.remove("visible"), 1800);
    });
  });
})();
