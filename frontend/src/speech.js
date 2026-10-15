// Browser speech: recognition (Chrome, Edge, Safari) and speech synthesis (all modern browsers).
const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;

export const canListen = Boolean(Recognition);

export function listen({ onText, onEnd, onError }) {
  if (!Recognition) return null;
  const r = new Recognition();
  r.lang = "en-AU";
  r.interimResults = false;
  r.maxAlternatives = 1;
  r.onresult = (e) => onText(e.results[0][0].transcript);
  r.onerror = (e) => onError && onError(e.error);
  r.onend = () => onEnd && onEnd();
  r.start();
  return r;
}

export function speak(text, { rate = 0.95 } = {}) {
  if (!("speechSynthesis" in window) || !text) return;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "en-AU";
  u.rate = rate;
  window.speechSynthesis.speak(u);
}

export function stopSpeaking() {
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
}
