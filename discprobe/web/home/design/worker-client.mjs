// One job per worker. Preview scheduling keeps only the latest pending request;
// exports use their own worker so processing cannot queue behind an export.
export function processingWorker() {
  const worker = new Worker(new URL("./processing-worker.mjs", import.meta.url), { type: "module" });
  let pending = null;
  const fail = error => { pending?.reject(error); pending = null; };
  worker.onmessage = ({ data }) => {
    const job = pending;
    pending = null;
    if (data.error) job?.reject(Object.assign(new Error(data.error.message), { name: data.error.name }));
    else job?.resolve(data);
  };
  worker.onerror = event => fail(new Error(event.message || "Image worker failed"));
  worker.onmessageerror = () => fail(new Error("Invalid image worker response"));
  return {
    run(data, transfers) {
      if (pending) return Promise.reject(new Error("Image worker is busy"));
      return new Promise((resolve, reject) => {
        pending = { resolve, reject };
        try { worker.postMessage(data, transfers); } catch (error) { fail(error); }
      });
    },
    close() { worker.terminate(); fail(new Error("Image worker closed")); },
  };
}
