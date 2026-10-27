import React from 'react';
import { MessageSquare, Smartphone } from 'lucide-react';

// Same SMS-text generation logic as before (generateKannadaSMS /
// generateEnglishSMS, same KANNADA_PLACE_NAMES map) -- this is a format
// PREVIEW only, no SMS is actually sent (no provider wired up). Only the
// visual system changed (migrated onto the shared cc- Control Center
// classes instead of the old legacy CSS).
const KANNADA_PLACE_NAMES = {
  'hebbal': 'ಹೆಬ್ಬಾಳ್',
  'silk board': 'ಸಿಲ್ಕ್ ಬೋರ್ಡ್',
  'manyata tech park': 'ಮನ್ಯತಾ ಟೆಕ್ ಪಾರ್ಕ್',
  'electronic city': 'ಎಲೆಕ್ಟ್ರಾನಿಕ್ ಸಿಟಿ',
  'whitefield': 'ವೈಟ್‌ಫೀಲ್ಡ್',
  'mg road': 'ಎಂಜಿ ರೋಡ್',
  'koramangala': 'ಕೋರಮಂಗಲ',
  'indiranagar': 'ಇಂದಿರಾನಗರ',
  'marathahalli': 'ಮರಠಹಳ್ಳಿ',
  'kr puram': 'ಕೆಆರ್ ಪುರಂ',
};

const SMSPreview = ({ prediction }) => {
  const kannadaName = (name) => KANNADA_PLACE_NAMES[(name || '').toLowerCase()] || name;

  const generateKannadaSMS = (prediction) => {
    const delayText = Math.round(prediction.delay_min || 0);
    const statusText = prediction.traffic === 'SEVERE' ? 'ಭಾರೀ' :
                     prediction.traffic === 'HIGH' ? 'ಹೆಚ್ಚು' :
                     prediction.traffic === 'MODERATE' ? 'ಮಧ್ಯಮ' : 'ಕಡಿಮೆ';

    const sourceKannada = kannadaName(prediction.source);
    const destKannada = kannadaName(prediction.destination);
    const altSuffix = prediction.recommended_route && prediction.recommended_route !== 'Fastest'
      ? `ಪರ್ಯಾಯ ಮಾರ್ಗ ಬಳಸಿ` : 'ಎಚ್ಚರಿಕೆಯಿಂದ ಪ್ರಯಾಣಿಸಿ';

    return `⚠️ ${sourceKannada}-${destKannada}: ${statusText} ದಟ್ಟಣೆ. ${delayText} ನಿಮಿಷ ವಿಳಂಬ. ${altSuffix}.`;
  };

  const generateEnglishSMS = (prediction) => {
    const delay = Math.round(prediction.delay_min || 0);
    const status = (prediction.traffic || 'moderate').toLowerCase();
    const altSuffix = prediction.recommended_route && prediction.recommended_route !== 'Fastest'
      ? `Consider the ${prediction.recommended_route} route` : 'Travel with caution';

    return `⚠️ ${prediction.source}-${prediction.destination}: ${status} congestion. ${delay} min delay. ${altSuffix}.`;
  };

  const kannadaSMS = generateKannadaSMS(prediction);
  const englishSMS = generateEnglishSMS(prediction);

  return (
    <div className="cc-panel">
      <div className="cc-panel-head">
        <p className="cc-panel-title"><MessageSquare size={13} className="cc-icon" /> Citizen Alert SMS</p>
        <span className="cc-pill high">Preview — not sent</span>
      </div>

      <div style={{ display: 'flex', gap: '0.8rem', alignItems: 'flex-start' }}>
        <div style={{ flexShrink: 0, color: 'var(--cc-text-faint)', paddingTop: '0.2rem' }}>
          <Smartphone size={32} />
        </div>
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
          <div className="cc-metric-tile">
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', color: 'var(--cc-text-faint)', marginBottom: '0.3rem' }}>
              <span>ಕನ್ನಡ · Bengaluru Brain</span>
              <span>{new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}</span>
            </div>
            <div lang="kn" style={{ color: 'var(--cc-text)', fontSize: '0.84rem' }}>{kannadaSMS}</div>
          </div>
          <div className="cc-metric-tile">
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', color: 'var(--cc-text-faint)', marginBottom: '0.3rem' }}>
              <span>English · Bengaluru Brain</span>
              <span>{new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}</span>
            </div>
            <div style={{ color: 'var(--cc-text)', fontSize: '0.84rem' }}>{englishSMS}</div>
          </div>
        </div>
      </div>

      {/* "Recipients: ~50,000" and "Channel: SMS + WhatsApp" were removed
          here -- placeholder-only numbers with no real subscriber count or
          WhatsApp integration behind them (see the Citizen Alert System
          Audit). The Route tile is real (it's this component's own
          `prediction` prop) and is kept. */}
      <div className="cc-metric-grid" style={{ gridTemplateColumns: '1fr', marginTop: '0.8rem' }}>
        <div className="cc-metric-tile">
          <div className="cc-mt-label">Route</div>
          <div className="cc-mt-value sm" style={{ fontSize: '0.82rem' }}>{prediction.source} → {prediction.destination}</div>
        </div>
      </div>
    </div>
  );
};

export default SMSPreview;
