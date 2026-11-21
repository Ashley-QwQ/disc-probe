export function countdownText(seconds) {
  if (!Number.isFinite(seconds)) return '';
  const whole = Math.max(0, Math.ceil(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`;
}

// The estimate can revise the pace, while each visible tick still counts down by one.
export function countdown(show) {
  let seconds = null, deadline = 0, timer;
  function schedule() {
    if (seconds <= 0) return;
    const difference = seconds - (deadline - performance.now()) / 1000;
    const delay = 1000 - Math.max(-150, Math.min(150, difference * 25));
    timer = setTimeout(() => {
      show(--seconds);
      schedule();
    }, delay);
  }
  return {
    estimate(eta) {
      if (!Number.isFinite(eta)) return;
      deadline = performance.now() + Math.max(0, eta) * 1000;
      if (seconds !== null || timer !== undefined) return;
      // The first job snapshot may replay several estimates at once. Start from the latest one.
      timer = setTimeout(() => {
        seconds = Math.max(0, Math.ceil((deadline - performance.now()) / 1000));
        show(seconds);
        schedule();
      }, 0);
    },
    clear() {
      clearTimeout(timer);
      timer = undefined;
      seconds = null;
      show(null);
    },
  };
}
