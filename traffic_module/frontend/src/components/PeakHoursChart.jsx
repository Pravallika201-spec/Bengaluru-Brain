import React, { useState, useEffect } from 'react';
import { XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, AreaChart } from 'recharts';
import { TrendingUp, Clock } from 'lucide-react';

// generateChartData() below is BYTE-FOR-BYTE the same heuristic as before
// (same fixed peak-hour windows/midpoint values, no Math.random(), no
// fabricated jitter) -- only the surrounding presentation (container,
// legend, tooltip, colors) has been migrated onto the shared cc- Control
// Center design tokens instead of the old legacy CSS / neon hex colors.
const CC_CYAN = '#22d3ee';
const CC_GREEN = '#22c55e';
const CC_YELLOW = '#eab308';
const CC_ORANGE = '#f97316';
const CC_RED = '#ef4444';
const CC_BORDER_STRONG = '#2a3855';
const CC_TEXT_DIM = '#8b97b0';

const PeakHoursChart = () => {
  const [chartData, setChartData] = useState([]);
  const [currentHour, setCurrentHour] = useState(new Date().getHours());

  useEffect(() => {
    generateChartData();
    const interval = setInterval(() => {
      setCurrentHour(new Date().getHours());
    }, 60000); // Update every minute

    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // NOTE: this chart is an ILLUSTRATIVE typical-day pattern derived from the
  // same fixed peak-hour windows the backend's rule-based heuristic uses
  // (app.py SPEED_TABLE) — it is NOT a live per-hour forecast for the
  // specific route being searched. Values are a fixed midpoint per hour
  // band (no Math.random()/no fabricated "live" jitter) so the chart is
  // reproducible and never implies a per-render model output.
  const generateChartData = () => {
    const data = [];

    for (let hour = 6; hour <= 22; hour++) {
      let congestionScore = 0.2; // Base congestion

      if (hour >= 8 && hour <= 10) {
        congestionScore = 0.8;
      } else if (hour >= 11 && hour <= 16) {
        congestionScore = 0.5;
      } else if (hour >= 17 && hour <= 20) {
        congestionScore = 0.87;
      } else if (hour >= 21 && hour <= 22) {
        congestionScore = 0.4;
      } else {
        congestionScore = 0.22;
      }

      congestionScore = Math.min(1.0, Math.max(0.0, congestionScore));

      data.push({
        hour: hour,
        time: `${hour}:00`,
        congestion: Math.round(congestionScore * 100),
        congestionScore: congestionScore,
        isPeak: (hour >= 8 && hour <= 10) || (hour >= 17 && hour <= 20),
        isCurrent: hour === currentHour
      });
    }

    setChartData(data);
  };

  const getCongestionColor = (congestion) => {
    if (congestion >= 80) return CC_RED;
    if (congestion >= 60) return CC_ORANGE;
    if (congestion >= 40) return CC_YELLOW;
    return CC_GREEN;
  };

  const CustomTooltip = ({ active, payload }) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      return (
        <div style={{ background: 'var(--cc-panel)', border: '1px solid var(--cc-border-strong)', borderRadius: 'var(--cc-radius-sm)', padding: '0.5rem 0.7rem', fontSize: '0.76rem' }}>
          <div style={{ fontWeight: 700, color: 'var(--cc-text)' }}>{data.time}</div>
          <div style={{ color: 'var(--cc-text-dim)' }}>Congestion: {data.congestion}%</div>
          {data.isPeak && <div style={{ color: 'var(--cc-orange)' }}>🚦 Peak Hours</div>}
          {data.isCurrent && <div style={{ color: 'var(--cc-cyan)' }}>📍 Current</div>}
        </div>
      );
    }
    return null;
  };

  const CustomDot = (props) => {
    const { cx, cy, payload } = props;
    if (payload.isCurrent) {
      return <circle cx={cx} cy={cy} r={6} fill={CC_CYAN} stroke="#ffffff" strokeWidth={2} />;
    }
    return <circle cx={cx} cy={cy} r={3} fill={getCongestionColor(payload.congestion)} />;
  };

  const currentCongestion = chartData.find((d) => d.hour === currentHour)?.congestion || 0;

  return (
    <div className="cc-panel">
      <div className="cc-panel-head">
        <p className="cc-panel-title"><TrendingUp size={13} className="cc-icon" /> Typical Peak-Hour Pattern</p>
        <span className="cc-pill neutral"><Clock size={11} style={{ verticalAlign: 'middle', marginRight: 3 }} />Now: {currentHour}:00</span>
      </div>
      <p className="cc-panel-sub" style={{ marginBottom: '0.6rem' }}>Illustrative typical-day pattern, not a live per-route forecast.</p>

      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={chartData}>
          <defs>
            <linearGradient id="congestionGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={CC_CYAN} stopOpacity={0.7} />
              <stop offset="95%" stopColor={CC_CYAN} stopOpacity={0.08} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke={CC_BORDER_STRONG} />
          <XAxis dataKey="time" stroke={CC_TEXT_DIM} tick={{ fill: CC_TEXT_DIM, fontSize: 11 }} />
          <YAxis stroke={CC_TEXT_DIM} tick={{ fill: CC_TEXT_DIM, fontSize: 11 }} domain={[0, 100]} />
          <Tooltip content={<CustomTooltip />} />
          <Area type="monotone" dataKey="congestion" stroke={CC_CYAN} strokeWidth={2} fill="url(#congestionGradient)" dot={<CustomDot />} />
        </AreaChart>
      </ResponsiveContainer>

      <div className="cc-metric-grid cc-metric-grid-4" style={{ marginTop: '0.8rem' }}>
        <div className="cc-metric-tile">
          <div className="cc-mt-label">Current Congestion</div>
          <div className="cc-mt-value sm" style={{ color: getCongestionColor(currentCongestion) }}>{currentCongestion}%</div>
        </div>
        <div className="cc-metric-tile">
          <div className="cc-mt-label">Next Peak</div>
          <div className="cc-mt-value sm">{currentHour < 8 ? '8:00 AM' : currentHour < 17 ? '5:00 PM' : 'Tomorrow 8 AM'}</div>
        </div>
        <div className="cc-metric-tile">
          <div className="cc-mt-label">Morning Peak</div>
          <div className="cc-mt-value sm">8–10 AM</div>
        </div>
        <div className="cc-metric-tile">
          <div className="cc-mt-label">Evening Peak</div>
          <div className="cc-mt-value sm">5–8 PM</div>
        </div>
      </div>
    </div>
  );
};

export default PeakHoursChart;
