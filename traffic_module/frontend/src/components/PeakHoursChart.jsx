import React, { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Bar, BarChart, Area, AreaChart } from 'recharts';
import { TrendingUp, Clock } from 'lucide-react';

const PeakHoursChart = () => {
  const [chartData, setChartData] = useState([]);
  const [currentHour, setCurrentHour] = useState(new Date().getHours());

  useEffect(() => {
    generateChartData();
    const interval = setInterval(() => {
      setCurrentHour(new Date().getHours());
    }, 60000); // Update every minute

    return () => clearInterval(interval);
  }, []);

  const generateChartData = () => {
    const data = [];
    
    for (let hour = 6; hour <= 22; hour++) {
      let congestionScore = 0.2; // Base congestion
      
      // Morning peak (8-10 AM)
      if (hour >= 8 && hour <= 10) {
        congestionScore = 0.7 + Math.random() * 0.2;
      }
      // Daytime (11 AM - 4 PM)
      else if (hour >= 11 && hour <= 16) {
        congestionScore = 0.4 + Math.random() * 0.2;
      }
      // Evening peak (5-8 PM)
      else if (hour >= 17 && hour <= 20) {
        congestionScore = 0.8 + Math.random() * 0.15;
      }
      // Late evening (9-10 PM)
      else if (hour >= 21 && hour <= 22) {
        congestionScore = 0.3 + Math.random() * 0.2;
      }
      // Early morning (6-7 AM)
      else {
        congestionScore = 0.15 + Math.random() * 0.15;
      }
      
      // Add some randomness
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
    if (congestion >= 80) return '#FF3131';
    if (congestion >= 60) return '#FF6B35';
    if (congestion >= 40) return '#FFD700';
    return '#00FF00';
  };

  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      return (
        <div className="chart-tooltip">
          <div className="tooltip-time">{data.time}</div>
          <div className="tooltip-congestion">
            Congestion: {data.congestion}%
          </div>
          {data.isPeak && (
            <div className="tooltip-peak">🚦 Peak Hours</div>
          )}
          {data.isCurrent && (
            <div className="tooltip-current">📍 Current</div>
          )}
        </div>
      );
    }
    return null;
  };

  const CustomDot = (props) => {
    const { cx, cy, payload } = props;
    
    if (payload.isCurrent) {
      return (
        <circle
          cx={cx}
          cy={cy}
          r={6}
          fill="#00D4FF"
          stroke="#ffffff"
          strokeWidth={2}
        />
      );
    }
    
    return (
      <circle
        cx={cx}
        cy={cy}
        r={3}
        fill={getCongestionColor(payload.congestion)}
      />
    );
  };

  return (
    <div className="peak-hours-chart">
      <div className="chart-header">
        <div className="header-title">
          <TrendingUp size={20} />
          <h3>📊 12-Hour Traffic Forecast</h3>
        </div>
        
        <div className="current-indicator">
          <Clock size={16} />
          <span>Now: {currentHour}:00</span>
        </div>
      </div>

      <div className="chart-container">
        <ResponsiveContainer width="100%" height={250}>
          <AreaChart data={chartData}>
            <defs>
              <linearGradient id="congestionGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#00D4FF" stopOpacity={0.8}/>
                <stop offset="95%" stopColor="#00D4FF" stopOpacity={0.1}/>
              </linearGradient>
            </defs>
            
            <CartesianGrid strokeDasharray="3 3" stroke="#475569" />
            
            <XAxis 
              dataKey="time" 
              stroke="#94A3B8"
              tick={{ fill: '#94A3B8', fontSize: 12 }}
            />
            
            <YAxis 
              stroke="#94A3B8"
              tick={{ fill: '#94A3B8', fontSize: 12 }}
              domain={[0, 100]}
            />
            
            <Tooltip content={<CustomTooltip />} />
            
            <Area
              type="monotone"
              dataKey="congestion"
              stroke="#00D4FF"
              strokeWidth={2}
              fill="url(#congestionGradient)"
              dot={<CustomDot />}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Peak Hours Legend */}
      <div className="chart-legend">
        <div className="legend-section">
          <h4>🚦 Peak Hours</h4>
          <div className="legend-items">
            <div className="legend-item">
              <div className="legend-color peak-morning"></div>
              <span>Morning (8-10 AM)</span>
            </div>
            <div className="legend-item">
              <div className="legend-color peak-evening"></div>
              <span>Evening (5-8 PM)</span>
            </div>
          </div>
        </div>
        
        <div className="legend-section">
          <h4>📊 Congestion Levels</h4>
          <div className="legend-items">
            <div className="legend-item">
              <div className="legend-color low"></div>
              <span>Low (0-40%)</span>
            </div>
            <div className="legend-item">
              <div className="legend-color medium"></div>
              <span>Medium (40-60%)</span>
            </div>
            <div className="legend-item">
              <div className="legend-color high"></div>
              <span>High (60-80%)</span>
            </div>
            <div className="legend-item">
              <div className="legend-color critical"></div>
              <span>Critical (80-100%)</span>
            </div>
          </div>
        </div>
      </div>

      {/* Current Status */}
      {chartData.length > 0 && (
        <div className="current-status">
          <div className="status-item">
            <div className="status-label">Current Congestion</div>
            <div className={`status-value ${getCongestionColor(chartData.find(d => d.hour === currentHour)?.congestion || 0)}`}>
              {chartData.find(d => d.hour === currentHour)?.congestion || 0}%
            </div>
          </div>
          
          <div className="status-item">
            <div className="status-label">Next Peak</div>
            <div className="status-value">
              {currentHour < 8 ? '8:00 AM' : currentHour < 17 ? '5:00 PM' : 'Tomorrow 8:00 AM'}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default PeakHoursChart;
