import React, { useState, useEffect } from 'react';
import { Clock, AlertTriangle, Building } from 'lucide-react';

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

  const getTimerColor = (status) => {
    switch (status) {
      case 'APPROACHING':
        return 'traffic-critical';
      case 'UPCOMING':
        return 'traffic-high';
      default:
        return 'traffic-medium';
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'APPROACHING':
        return '🚨';
      case 'UPCOMING':
        return '⏰';
      default:
        return '📅';
    }
  };

  const isShiftChangeWarning = () => {
    return shiftTimers.some(timer => timer.status === 'APPROACHING');
  };

  return (
    <div className="it-shift-timer">
      <div className="timer-header">
        <div className="header-title">
          <Building size={20} />
          <h3>🏢 IT Shift Timers</h3>
        </div>
        
        {isShiftChangeWarning() && (
          <div className="warning-badge">
            <AlertTriangle size={16} />
            <span>Shift Change</span>
          </div>
        )}
      </div>

      {/* Warning Banner */}
      {isShiftChangeWarning() && (
        <div className="shift-warning-banner">
          <AlertTriangle size={20} />
          <div className="warning-content">
            <div className="warning-title">IT Shift Change Imminent</div>
            <div className="warning-message">
              Heavy traffic expected during shift change hours
            </div>
          </div>
        </div>
      )}

      <div className="timers-list">
        {shiftTimers.length === 0 ? (
          <div className="no-timers">
            <Clock size={32} />
            <p>No upcoming shift changes</p>
            <small>Next shift change in 2+ hours</small>
          </div>
        ) : (
          shiftTimers.map((timer, index) => (
            <div key={index} className={`timer-card ${getTimerColor(timer[2])}`}>
              <div className="timer-header">
                <div className="timer-location">
                  <Building size={16} />
                  <span>{timer[0]}</span>
                </div>
                <div className="timer-status">
                  {getStatusIcon(timer[2])}
                  <span>{timer[2]}</span>
                </div>
              </div>
              
              <div className="timer-countdown">
                <div className={`countdown-time ${getTimerColor(timer[2])}`}>
                  {formatTime(timer[1])}
                </div>
                <div className="countdown-label">
                  {timer[2] === 'APPROACHING' ? 'until shift change' : 'until shift'}
                </div>
              </div>
              
              {timer[2] === 'APPROACHING' && (
                <div className="timer-alert">
                  <AlertTriangle size={14} />
                  <span>Expect heavy traffic</span>
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* Current Time Display */}
      <div className="current-time-display">
        <div className="time-label">Current Time</div>
        <div className="time-value">
          {currentTime.toLocaleTimeString()}
        </div>
        <div className="time-date">
          {currentTime.toLocaleDateString()}
        </div>
      </div>

      {/* Shift Schedule Info */}
      <div className="shift-schedule">
        <h4>📅 Typical IT Shift Hours</h4>
        <div className="schedule-grid">
          <div className="schedule-item">
            <div className="schedule-park">Manyata Tech Park</div>
            <div className="schedule-times">8-9 AM, 5-7 PM</div>
          </div>
          <div className="schedule-item">
            <div className="schedule-park">Electronic City</div>
            <div className="schedule-times">8-9 AM, 6-8 PM</div>
          </div>
          <div className="schedule-item">
            <div className="schedule-park">Whitefield</div>
            <div className="schedule-times">9-10 AM, 6-8 PM</div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ITShiftTimer;
