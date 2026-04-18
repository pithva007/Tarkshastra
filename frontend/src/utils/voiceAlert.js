/**
 * Web Speech API voice alert utility for TS-11 Stampede Predictor.
 * No external libraries required — uses built-in browser SpeechSynthesis.
 */

const MESSAGES = {
  police: (corridor, cpi, ttbMinutes) =>
    `Attention Police Control Room. High crowd pressure detected at ${corridor} corridor. ` +
    `Current pressure index is ${cpi.toFixed(2)}. ` +
    `Crush risk predicted in ${ttbMinutes} minutes. ` +
    `Deploy officers to Choke Point Bravo immediately. ` +
    `This is an automated alert from Stampede Predictor System.`,

  temple: (corridor, cpi, ttbMinutes) =>
    `Attention Temple Trust. Critical crowd density at ${corridor}. ` +
    `Corridor Pressure Index is ${cpi.toFixed(2)}. ` +
    `Please activate darshan hold at inner gate immediately and redirect pilgrims to Queue Charlie. ` +
    `Crush risk in ${ttbMinutes} minutes.`,

  gsrtc: (corridor, cpi, ttbMinutes) =>
    `Attention GSRTC Transport Control. Hold all incoming vehicles for ${corridor} at the 3 kilometre checkpoint. ` +
    `Corridor is approaching capacity. Pressure index ${cpi.toFixed(2)}. ` +
    `Do not dispatch additional buses until further notice.`,

  driver: (corridor, cpi, ttbMinutes) =>
    `Attention Bus Driver. Your destination ${corridor} has high crowd pressure. ` +
    `Please hold at the designated checkpoint. ` +
    `Do not proceed to temple area. Await further instructions from control room.`,
}

/**
 * Trigger a voice alert for the given agency.
 *
 * @param {string} corridor   - Corridor name e.g. "Ambaji"
 * @param {number} cpi        - Current CPI value 0–1
 * @param {number} ttbMinutes - Time to breach in minutes
 * @param {string} agency     - 'police' | 'temple' | 'gsrtc' | 'driver'
 */
export function triggerVoiceAlert(corridor, cpi, ttbMinutes, agency) {
  if (!window.speechSynthesis) return

  const msgFn = MESSAGES[agency] || MESSAGES['police']
  const text = msgFn(corridor, cpi, ttbMinutes ?? 5)

  const utterance = new SpeechSynthesisUtterance(text)
  utterance.rate = 0.85
  utterance.pitch = 1.0
  utterance.volume = 1.0
  utterance.lang = 'en-IN'

  // Stop any currently playing speech before starting new one
  window.speechSynthesis.cancel()
  window.speechSynthesis.speak(utterance)
}

/**
 * Stop any currently playing voice alert.
 */
export function stopVoiceAlert() {
  if (window.speechSynthesis) {
    window.speechSynthesis.cancel()
  }
}

/**
 * Check if speech synthesis is supported.
 */
export function isSpeechSupported() {
  return typeof window !== 'undefined' && !!window.speechSynthesis
}
