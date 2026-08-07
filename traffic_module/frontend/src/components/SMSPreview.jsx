import React from 'react';
import { MessageSquare, AlertTriangle, Smartphone } from 'lucide-react';

const SMSPreview = ({ prediction }) => {
  const generateKannadaSMS = (prediction) => {
    const kannadaTexts = {
      'Hebbal': 'ಹೆಬ್ಬಾಳ್',
      'Silk Board': 'ಸಿಲ್ಕ್ ಬೋರ್ಡ್',
      'Manyata Tech Park': 'ಮನ್ಯತಾ ಟೆಕ್ ಪಾರ್ಕ್',
      'Electronic City': 'ಎಲೆಕ್ಟ್ರಾನಿಕ್ ಸಿಟಿ',
      'Whitefield': 'ವೈಟ್‌ಫೀಲ್ಡ್',
      'MG Road': 'ಎಂಜಿ ರೋಡ್',
      'Koramangala': 'ಕೋರಮಂಗಲ',
      'Indiranagar': 'ಇಂದಿರಾನಗರ',
      'Marathahalli': 'ಮರಠಹಳ್ಳಿ',
      'KR Puram': 'ಕೆಆರ್ ಪುರಂ'
    };

    const getSourceName = (route) => {
      const source = route.split(' → ')[0];
      return kannadaTexts[source] || source;
    };

    const getDestName = (route) => {
      const dest = route.split(' → ').pop();
      return kannadaTexts[dest] || dest;
    };

    const delayText = prediction.estimated_delay_minutes;
    const statusText = prediction.current_status === 'CRITICAL' ? 'ಭಾರೀ' : 
                     prediction.current_status === 'HIGH' ? 'ಹೆಚ್ಚು' : 
                     prediction.current_status === 'MEDIUM' ? 'ಮಧ್ಯಮ' : 'ಕಡಿಮೆ';

    const sourceKannada = getSourceName(prediction.route);
    const destKannada = getDestName(prediction.route);

    return `⚠️ ${sourceKannada}-${destKannada}: ${statusText} ದಟ್ಟಣೆ. ${delayText} ನಿಮಿಷ ವಿಳಂಬ. ${prediction.alternative_route ? 'ಪರ್ಯಾಯ: NICE ರಸ್ತೆ ಬಳಸಿ' : 'ಎಚ್ಚರಿಕೆಯಿಂದ ಪ್ರಯಾಣಿಸಿ'}.`;
  };

  const generateEnglishSMS = (prediction) => {
    const source = prediction.route.split(' → ')[0];
    const dest = prediction.route.split(' → ').pop();
    const delay = prediction.estimated_delay_minutes;
    const status = prediction.current_status.toLowerCase();

    return `⚠️ ${source}-${dest}: ${status} congestion. ${delay} min delay. ${prediction.alternative_route ? 'Use NICE Road' : 'Travel with caution'}.`;
  };

  const kannadaSMS = generateKannadaSMS(prediction);
  const englishSMS = generateEnglishSMS(prediction);

  return (
    <div className="sms-preview">
      <div className="sms-header">
        <div className="header-title">
          <MessageSquare size={20} />
          <h3>📱 Citizen Alert SMS</h3>
        </div>
        
        <div className="alert-badge">
          <AlertTriangle size={16} />
          <span>Critical Traffic</span>
        </div>
      </div>

      <div className="sms-content">
        <div className="sms-phone">
          <Smartphone size={48} />
        </div>
        
        <div className="sms-messages">
          {/* Kannada SMS */}
          <div className="sms-message kannada">
            <div className="sms-header-info">
              <span className="sms-language">ಕನ್ನಡ</span>
              <span className="sms-sender">Bengaluru Brain</span>
            </div>
            <div className="sms-text">
              {kannadaSMS}
            </div>
            <div className="sms-time">
              {new Date().toLocaleTimeString('en-IN', { 
                hour: '2-digit', 
                minute: '2-digit' 
              })}
            </div>
          </div>

          {/* English SMS */}
          <div className="sms-message english">
            <div className="sms-header-info">
              <span className="sms-language">English</span>
              <span className="sms-sender">Bengaluru Brain</span>
            </div>
            <div className="sms-text">
              {englishSMS}
            </div>
            <div className="sms-time">
              {new Date().toLocaleTimeString('en-US', { 
                hour: '2-digit', 
                minute: '2-digit' 
              })}
            </div>
          </div>
        </div>
      </div>

      {/* SMS Statistics */}
      <div className="sms-stats">
        <div className="stat-item">
          <div className="stat-label">Recipients</div>
          <div className="stat-value">~50,000</div>
        </div>
        <div className="stat-item">
          <div className="stat-label">Affected Wards</div>
          <div className="stat-value">{prediction.affected_wards.length}</div>
        </div>
        <div className="stat-item">
          <div className="stat-label">Est. Reach Time</div>
          <div className="stat-value">2 min</div>
        </div>
      </div>

      {/* SMS Action Buttons */}
      <div className="sms-actions">
        <button className="sms-action-btn send">
          📤 Send Alerts Now
        </button>
        <button className="sms-action-btn preview">
          👁️ Preview All Languages
        </button>
        <button className="sms-action-btn schedule">
          ⏰ Schedule Follow-up
        </button>
      </div>

      {/* Delivery Info */}
      <div className="delivery-info">
        <div className="delivery-item">
          <span className="delivery-label">Channel:</span>
          <span className="delivery-value">SMS + WhatsApp</span>
        </div>
        <div className="delivery-item">
          <span className="delivery-label">Priority:</span>
          <span className="delivery-value traffic-critical">HIGH</span>
        </div>
        <div className="delivery-item">
          <span className="delivery-label">Duration:</span>
          <span className="delivery-value">Next 2 hours</span>
        </div>
      </div>
    </div>
  );
};

export default SMSPreview;
