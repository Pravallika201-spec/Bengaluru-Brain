import React, { useState, useEffect } from 'react';
import { Clock, AlertTriangle, Building } from 'lucide-react';

// Same /api/shift-timers data and logic as before -- only the visual
// system changed (migrated from the old legacy CSS classes onto the
// shared cc- Control Center classes used elsewhere in the app).
const ITShiftTimer = () => {
  const [shiftTimers, setShiftTimers] = useState([]);
  const [currentTime, setCurrentTime] = useState(new Date());

  useEffect(() => {
    fetchShiftTimers();
    const interval = setInterval(() => {
      setCurrentTime(new Date());
      fetchShiftTimers();
    }, 60000); // Update every minute

    return () => clearInterval(interval);
  }, []);

  const fetchShiftTimers = async () => {
    try {
      const response = await fetch('/api/shift-timers');
      const data = await response.json();
      setShiftTimers(data.shift_timers || []);
    } catch (error) {
      console.error('Failed to fetch shift timers:', error);
    }
  };

  const formatTime = (minutes) => {
    if (minutes < 60) {
      return `${minutes}m`;
    }
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return `${hours}h ${mins}m`;
  };

  const STATUS_COLOR = { APPROACHING: 'var(--cc-red)', UPCOMING: 'var(--cc-orange)' };
  const getStatusIcon = (status) => (status === 'APPROACHING' ? '🚨' : status === 'UPCOMING' ? '⏰' : '📅');
  const isShiftChangeWarning = () => shiftTimers.some((timer) => timer.status === 'APPROACHING');

  return (
    <div className="cc-panel">
      <div className="cc-panel-head">
        <p className="cc-panel-title"><Building size={13} className="cc-icon" /> IT Shift Timers</p>
        {isShiftChangeWarning() && (
          <span className="cc-pill critical"><AlertTriangle size={11} style={{ verticalAlign: 'middle', marginRight: 3 }} />Shift Change</span>
        )}
      </div>

      {isShiftChangeWarning() && (
        <div className="cc-metric-tile" style={{ borderLeft: '3px solid var(--cc-red)', marginBottom: '0.7rem', display: 'flex', gap: '0.6rem', alignItems: 'flex-start' }}>
          <AlertTriangle size={16} style={{ color: 'var(--cc-red)', flexShrink: 0, marginTop: 2 }} />
          <div>
            <div style={{ fontWeight: 700, color: 'var(--cc-text)', fontSize: '0.82rem' }}>IT Shift Change Imminent</div>
            <div style={{ fontSize: '0.76rem', color: 'var(--cc-text-dim)', marginTop: '0.15rem' }}>Heavy traffic expected during shift change hours</div>
          </div>
        </div>
      )}

      {shiftTimers.length === 0 ? (
        <div className="cc-empty">No upcoming shift changes — next shift change in 2+ hours</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {shiftTimers.map((timer, index) => (
            <div className="cc-metric-tile" key={index} style={{ borderLeft: `3px solid ${STATUS_COLOR[timer.status] || 'var(--cc-border-strong)'}` }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.82rem', fontWeight: 700, color: 'var(--cc-text)' }}>
                  <Building size={13} /> {timer.park}
                </span>
                <span style={{ fontSize: '0.72rem', color: 'var(--cc-text-dim)' }}>{getStatusIcon(timer.status)} {timer.status}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.4rem' }}>
                <span style={{ fontFamily: 'var(--cc-font-display)', fontSize: '1.3rem', fontWeight: 700, color: STATUS_COLOR[timer.status] || 'var(--cc-text)' }}>
                  {formatTime(timer.minutes_until)}
                </span>
                <span style={{ fontSize: '0.72rem', color: 'var(--cc-text-faint)' }}>
                  {timer.status === 'APPROACHING' ? 'until shift change' : 'until shift'}
                </span>
              </div>
              {timer.status === 'APPROACHING' && (
                <div style={{ fontSize: '0.74rem', color: 'var(--cc-red)', marginTop: '0.3rem' }}>⚠ Expect heavy traffic</div>
              )}
            </div>
          ))}
        </div>
      )}

      <div style={{ marginTop: '0.8rem', paddingTop: '0.7rem', borderTop: '1px solid var(--cc-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <span style={{ fontSize: '0.72rem', color: 'var(--cc-text-faint)' }}>Current time</span>
        <span style={{ fontFamily: 'var(--cc-font-display)', fontWeight: 700, color: 'var(--cc-text)' }}>{currentTime.toLocaleTimeString()}</span>
      </div>

      <details className="cc-details" style={{ marginTop: '0.7rem' }}>
        <summary style={{ cursor: 'pointer', fontSize: '0.74rem', color: 'var(--cc-accent)', fontWeight: 700 }}>
          Typical IT shift hours
        </summary>
        <div className="cc-metric-grid" style={{ marginTop: '0.5rem' }}>
          <div className="cc-metric-tile">
            <div className="cc-mt-label">Manyata Tech Park</div>
            <div className="cc-mt-value sm">8-9 AM, 5-7 PM</div>
          </div>
          <div className="cc-metric-tile">
            <div className="cc-mt-label">Electronic City</div>
            <div className="cc-mt-value sm">8-9 AM, 6-8 PM</div>
          </div>
          <div className="cc-metric-tile">
            <div className="cc-mt-label">Whitefield</div>
            <div className="cc-mt-value sm">9-10 AM, 6-8 PM</div>
          </div>
        </div>
      </details>
    </div>
  );
};

export default ITShiftTimer;
