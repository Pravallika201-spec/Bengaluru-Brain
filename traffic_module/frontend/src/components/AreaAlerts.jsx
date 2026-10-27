import React, { useEffect, useRef, useState } from 'react';

// ================================================================
// ONE combined, citizen-friendly Traffic + Waste alert card for the
// currently selected area -- used by both the Alerts tab and the
// bottom of the USI page (same component, same /api/alerts/{area}
// call, different heading word), so both pages always show the
// identical status for whatever area is selected. Driven entirely by
// the `selectedArea` prop (the single shared area state owned by
// App.js) -- never a locally-tracked area name of its own, so search /
// current-location / quick-location chip selection on either page all
// update this card identically.
//
// ONE MESSAGE, NOT TWO BLOCKS: Traffic and Waste are fused into a
// single sentence ("Traffic congestion is currently X and waste
// overflow risk is currently Y.") plus, when needed, a single combined
// advisory sentence -- never two separate Traffic/Waste boxes. Both
// domains are always represented in that one sentence, regardless of
// level -- a LOW domain is stated as low, not omitted. The wording is
// built purely from each domain's own existing level (usi.traffic.level
// / usi.waste.level, the exact same LOW/MEDIUM/HIGH/CRITICAL/UNKNOWN
// values UsiPanel.jsx's Traffic/Waste Contribution tiles already read)
// via the fixed, non-fabricated CLAUSE/ADVISORY phrase tables below --
// no new severity calculation and no score is invented here.
//
// LANGUAGES: English, Kannada (ಕನ್ನಡ) and Hindi (हिन्दी) only --
// deliberately no Telugu. CLAUSE and ADVISORY are hand-paired per
// level/language so buildCombinedMessage() always produces the SAME
// underlying meaning in all three -- a frontend presentation-layer
// composition of fixed phrase fragments (never a translation API call,
// never invented backend data). The backend's own `alert.kannada`
// field is a single whole-alert message keyed off the blended band,
// not the per-domain levels this sentence is built from, so it is
// intentionally not reused -- it could say something different from
// what this sentence (built straight from the real per-domain levels)
// reports. Traffic level, waste level, the actual condition, the area
// and severity all still come from the existing USI data; only the
// presentation/language layer is added here.
//
// If one domain is genuinely UNKNOWN (the backend has no signal), the
// combined sentence still names the other domain's real condition and
// honestly says that domain's data isn't available -- never a
// fabricated level. Only when BOTH domains are UNKNOWN does the card
// collapse to a single "no alerts yet" line.
// ================================================================

const CLAUSE = {
  traffic: {
    LOW: { en: 'traffic congestion is currently low', kn: 'ಸಂಚಾರ ದಟ್ಟಣೆ ಕಡಿಮೆ ಇದೆ', hi: 'यातायात की भीड़ कम है' },
    MEDIUM: { en: 'traffic congestion is currently medium', kn: 'ಸಂಚಾರ ದಟ್ಟಣೆ ಮಧ್ಯಮ ಮಟ್ಟದಲ್ಲಿದೆ', hi: 'यातायात की भीड़ मध्यम है' },
    HIGH: { en: 'traffic congestion is currently high', kn: 'ಸಂಚಾರ ದಟ್ಟಣೆ ಹೆಚ್ಚಾಗಿದೆ', hi: 'यातायात की भीड़ अधिक है' },
    CRITICAL: { en: 'traffic congestion is currently critical', kn: 'ಸಂಚಾರ ದಟ್ಟಣೆ ತೀವ್ರವಾಗಿದೆ', hi: 'यातायात की भीड़ अत्यंत गंभीर है' },
    UNKNOWN: { en: 'traffic data is not available', kn: 'ಸಂಚಾರ ಮಾಹಿತಿ ಲಭ್ಯವಿಲ್ಲ', hi: 'यातायात डेटा उपलब्ध नहीं है' },
  },
  waste: {
    LOW: { en: 'waste overflow risk is currently low', kn: 'ತ್ಯಾಜ್ಯ ಉಕ್ಕಿ ಹರಿಯುವ ಅಪಾಯ ಕಡಿಮೆ ಇದೆ', hi: 'कचरा ओवरफ्लो का खतरा कम है' },
    MEDIUM: { en: 'waste overflow risk is currently medium', kn: 'ತ್ಯಾಜ್ಯ ಉಕ್ಕಿ ಹರಿಯುವ ಅಪಾಯ ಮಧ್ಯಮ ಮಟ್ಟದಲ್ಲಿದೆ', hi: 'कचरा ओवरफ्लो का खतरा मध्यम है' },
    HIGH: { en: 'waste overflow risk is currently high', kn: 'ತ್ಯಾಜ್ಯ ಉಕ್ಕಿ ಹರಿಯುವ ಅಪಾಯ ಹೆಚ್ಚಾಗಿದೆ', hi: 'कचरा ओवरफ्लो का खतरा अधिक है' },
    CRITICAL: { en: 'waste overflow risk is currently critical', kn: 'ತ್ಯಾಜ್ಯ ಉಕ್ಕಿ ಹರಿಯುವ ಅಪಾಯ ತೀವ್ರವಾಗಿದೆ', hi: 'कचरा ओवरफ्लो का खतरा अत्यंत गंभीर है' },
    UNKNOWN: { en: 'waste data is not available', kn: 'ತ್ಯಾಜ್ಯ ಮಾಹಿತಿ ಲಭ್ಯವಿಲ್ಲ', hi: 'कचरा डेटा उपलब्ध नहीं है' },
  },
};

// Advisory fragments never carry their own leading "please" -- the
// composer adds that once, even when both domains contribute one.
const ADVISORY = {
  traffic: {
    MEDIUM: { en: 'plan your travel accordingly', kn: 'ನಿಮ್ಮ ಪ್ರಯಾಣವನ್ನು ಅದಕ್ಕೆ ಅನುಗುಣವಾಗಿ ಯೋಜಿಸಿ', hi: 'अपनी यात्रा की योजना उसी के अनुसार बनाएं' },
    HIGH: { en: 'plan your travel accordingly', kn: 'ನಿಮ್ಮ ಪ್ರಯಾಣವನ್ನು ಅದಕ್ಕೆ ಅನುಗುಣವಾಗಿ ಯೋಜಿಸಿ', hi: 'अपनी यात्रा की योजना उसी के अनुसार बनाएं' },
    CRITICAL: { en: 'avoid unnecessary travel through this area if possible', kn: 'ಸಾಧ್ಯವಾದರೆ ಈ ಪ್ರದೇಶದ ಮೂಲಕ ಅನಗತ್ಯ ಪ್ರಯಾಣವನ್ನು ತಪ್ಪಿಸಿ', hi: 'यदि संभव हो तो इस क्षेत्र से अनावश्यक यात्रा से बचें' },
  },
  waste: {
    MEDIUM: { en: 'be cautious around the area', kn: 'ಈ ಪ್ರದೇಶದ ಸುತ್ತಮುತ್ತ ಎಚ್ಚರಿಕೆಯಿಂದಿರಿ', hi: 'इस क्षेत्र के आसपास सावधान रहें' },
    HIGH: { en: 'be cautious around the area', kn: 'ಈ ಪ್ರದೇಶದ ಸುತ್ತಮುತ್ತ ಎಚ್ಚರಿಕೆಯಿಂದಿರಿ', hi: 'इस क्षेत्र के आसपास सावधान रहें' },
    CRITICAL: { en: 'be cautious around the area', kn: 'ಈ ಪ್ರದೇಶದ ಸುತ್ತಮುತ್ತ ಎಚ್ಚರಿಕೆಯಿಂದಿರಿ', hi: 'इस क्षेत्र के आसपास सावधान रहें' },
  },
};

const AND = { en: 'and', kn: 'ಮತ್ತು', hi: 'और' };
const CURRENTLY_PREFIX = { en: '', kn: 'ಪ್ರಸ್ತುತ ', hi: 'वर्तमान में ' };
const PLEASE_PREFIX = { en: 'Please ', kn: 'ದಯವಿಟ್ಟು ', hi: 'कृपया ' };
const STOP = { en: '.', kn: '.', hi: '।' };

function capitalize(s) {
  if (!s) return s;
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function normalizeLevel(domain, level) {
  return level && CLAUSE[domain][level] ? level : 'UNKNOWN';
}

// Builds the ONE combined Traffic + Waste sentence (plus a single
// combined advisory sentence when at least one domain needs one) for
// a given language. English keeps "currently" inside each clause (so
// it reads "...is currently low and ...is currently high"); Kannada
// and Hindi instead carry a single "ಪ್ರಸ್ತುತ" / "वर्तमान में" once at
// the front of the sentence, governing both clauses -- both are
// faithful, natural phrasings of the exact same underlying meaning.
function buildCombinedMessage(trafficLevel, wasteLevel, lang) {
  const tClause = CLAUSE.traffic[trafficLevel][lang];
  const wClause = CLAUSE.waste[wasteLevel][lang];
  const and = AND[lang];
  const stop = STOP[lang];

  const body = `${tClause} ${and} ${wClause}`;
  const mainSentence = lang === 'en'
    ? `${capitalize(body)}${stop}`
    : `${CURRENTLY_PREFIX[lang]}${body}${stop}`;

  const advisoryParts = [];
  const tAdv = ADVISORY.traffic[trafficLevel];
  const wAdv = ADVISORY.waste[wasteLevel];
  if (tAdv) advisoryParts.push(tAdv[lang]);
  if (wAdv) advisoryParts.push(wAdv[lang]);

  if (advisoryParts.length === 0) {
    return mainSentence;
  }

  const advisorySentence = `${PLEASE_PREFIX[lang]}${advisoryParts.join(` ${and} `)}${stop}`;
  return `${mainSentence} ${advisorySentence}`;
}

const AreaAlerts = ({ selectedArea, headingWord = 'Alerts' }) => {
  // idle | loading | loaded | error
  const [alertState, setAlertState] = useState('idle');
  const [alertData, setAlertData] = useState(null);

  // Guards against a stale, out-of-order response (e.g. the area changes
  // again before an earlier area's fetch resolves) ever being applied over
  // a newer selection's result -- the same monotonic-request-id pattern
  // already used in App.js's handlePredict, applied here so switching
  // areas quickly can never leave a previous area's status showing.
  const requestIdRef = useRef(0);

  useEffect(() => {
    if (!selectedArea) {
      // Nothing selected yet -- do not show any previous area's status.
      setAlertState('idle');
      setAlertData(null);
      return;
    }

    const thisRequestId = ++requestIdRef.current;
    setAlertState('loading');
    setAlertData(null);

    fetch(`/api/alerts/${encodeURIComponent(selectedArea)}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => {
        if (thisRequestId !== requestIdRef.current) return; // a newer area was selected meanwhile
        setAlertData(data);
        setAlertState('loaded');
      })
      .catch(() => {
        if (thisRequestId !== requestIdRef.current) return;
        setAlertState('error');
      });
  }, [selectedArea]);

  const heading = selectedArea ? `🔔 ${headingWord} for ${selectedArea}` : `🔔 ${headingWord}`;

  return (
    <div className="cc-panel" style={{ marginBottom: '1rem' }}>
      <div className="cc-panel-head">
        <p className="cc-panel-title">{heading}</p>
      </div>

      {!selectedArea && (
        <div className="cc-empty">📍 Select or detect an area to see its status.</div>
      )}

      {selectedArea && alertState === 'loading' && (
        <div className="cc-empty">Loading status…</div>
      )}

      {selectedArea && alertState === 'error' && (
        <div className="cc-empty">Unable to load nearby alerts right now. Please try again.</div>
      )}

      {selectedArea && alertState === 'loaded' && alertData && alertData.available && (() => {
        const traffic = alertData.usi?.traffic;
        const waste = alertData.usi?.waste;

        const trafficLevel = normalizeLevel('traffic', traffic?.level);
        const wasteLevel = normalizeLevel('waste', waste?.level);
        const trafficKnown = trafficLevel !== 'UNKNOWN';
        const wasteKnown = wasteLevel !== 'UNKNOWN';

        // Only when there is genuinely no real signal for either domain
        // is there nothing to show at all.
        if (!trafficKnown && !wasteKnown) {
          return (
            <div className="cc-empty" style={{ color: 'var(--cc-text-dim)' }}>
              ✓ No alerts available for {selectedArea} yet.
            </div>
          );
        }

        const english = buildCombinedMessage(trafficLevel, wasteLevel, 'en');
        const kannada = buildCombinedMessage(trafficLevel, wasteLevel, 'kn');
        const hindi = buildCombinedMessage(trafficLevel, wasteLevel, 'hi');

        // ONE card, ONE message per language -- never separate
        // Traffic/Waste boxes.
        return (
          <div className="cc-metric-tile" style={{ marginTop: '0.6rem' }}>
            <div className="cc-mt-label">🚦 Traffic + 🗑️ Waste</div>

            <div style={{ marginTop: '0.5rem' }}>
              <div style={{ fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.04em', color: 'var(--cc-text-dim)' }}>
                English
              </div>
              <p style={{ color: 'var(--cc-text)', fontSize: '0.85rem', marginTop: '0.15rem', lineHeight: 1.5 }}>
                {english}
              </p>
            </div>

            <div style={{ marginTop: '0.55rem' }}>
              <div style={{ fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.04em', color: 'var(--cc-text-dim)' }}>
                ಕನ್ನಡ
              </div>
              <p lang="kn" style={{ color: 'var(--cc-text)', fontSize: '0.85rem', marginTop: '0.15rem', lineHeight: 1.5 }}>
                {kannada}
              </p>
            </div>

            <div style={{ marginTop: '0.55rem' }}>
              <div style={{ fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.04em', color: 'var(--cc-text-dim)' }}>
                हिन्दी
              </div>
              <p lang="hi" style={{ color: 'var(--cc-text)', fontSize: '0.85rem', marginTop: '0.15rem', lineHeight: 1.5 }}>
                {hindi}
              </p>
            </div>
          </div>
        );
      })()}
    </div>
  );
};

export default AreaAlerts;
