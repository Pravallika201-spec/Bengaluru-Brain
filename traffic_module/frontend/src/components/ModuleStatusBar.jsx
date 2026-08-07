import React, { useState, useEffect } from 'react';
import { Brain, Droplet, Zap, Waves, Trash2, MessageSquare, CheckCircle, AlertCircle } from 'lucide-react';

const ModuleStatusBar = () => {
  const [modules, setModules] = useState([
    {
      name: 'Traffic',
      icon: Brain,
      status: 'LIVE',
      color: 'traffic-low',
      description: 'Real-time traffic prediction'
    },
    {
      name: 'Water',
      icon: Droplet,
      status: 'SIMULATED',
      color: 'traffic-medium',
      description: 'Water supply monitoring'
    },
    {
      name: 'Power',
      icon: Zap,
      status: 'SIMULATED',
      color: 'traffic-medium',
      description: 'Power grid status'
    },
    {
      name: 'Flood',
      icon: Waves,
      status: 'SIMULATED',
      color: 'traffic-medium',
      description: 'Flood risk assessment'
    },
    {
      name: 'Waste',
      icon: Trash2,
      status: 'SIMULATED',
      color: 'traffic-medium',
      description: 'Waste management'
    },
    {
      name: 'Complaints',
      icon: MessageSquare,
      status: 'SIMULATED',
      color: 'traffic-medium',
      description: 'Citizen complaints'
    }
  ]);

  const [tooltip, setTooltip] = useState(null);

  const handleModuleClick = (module) => {
    if (module.status === 'SIMULATED') {
      setTooltip({
        module: module.name,
        message: 'Coming in Phase 2',
        position: 'top'
      });
      
      // Hide tooltip after 3 seconds
      setTimeout(() => setTooltip(null), 3000);
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'LIVE':
        return <CheckCircle size={16} />;
      case 'SIMULATED':
        return <AlertCircle size={16} />;
      case 'OFFLINE':
        return <div className="status-dot offline"></div>;
      default:
        return <div className="status-dot unknown"></div>;
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'LIVE':
        return 'status-green';
      case 'SIMULATED':
        return 'status-yellow';
      case 'OFFLINE':
        return 'status-red';
      default:
        return 'status-gray';
    }
  };

  return (
    <div className="module-status-bar">
      <div className="status-header">
        <div className="header-title">
          <Brain size={20} />
          <span>Bengaluru Brain Modules</span>
        </div>
        
        <div className="system-status">
          <div className="status-indicator live">
            <div className="status-dot live"></div>
            <span>System Online</span>
          </div>
        </div>
      </div>

      <div className="modules-container">
        {modules.map((module) => {
          const Icon = module.icon;
          return (
            <div
              key={module.name}
              className={`module-item ${module.status === 'LIVE' ? 'live' : 'simulated'}`}
              onClick={() => handleModuleClick(module)}
            >
              <div className="module-icon">
                <Icon size={24} />
              </div>
              
              <div className="module-info">
                <div className="module-name">{module.name}</div>
                <div className={`module-status ${getStatusColor(module.status)}`}>
                  {getStatusIcon(module.status)}
                  <span>{module.status}</span>
                </div>
              </div>
              
              <div className="module-description">
                {module.description}
              </div>
            </div>
          );
        })}
      </div>

      {/* Tooltip */}
      {tooltip && (
        <div className={`tooltip tooltip-${tooltip.position}`}>
          <div className="tooltip-content">
            <div className="tooltip-title">{tooltip.module}</div>
            <div className="tooltip-message">{tooltip.message}</div>
          </div>
          <div className="tooltip-arrow"></div>
        </div>
      )}

      {/* System Info */}
      <div className="system-info">
        <div className="info-item">
          <span className="info-label">Version:</span>
          <span className="info-value">v2.0.0</span>
        </div>
        <div className="info-item">
          <span className="info-label">Uptime:</span>
          <span className="info-value">99.8%</span>
        </div>
        <div className="info-item">
          <span className="info-label">Last Update:</span>
          <span className="info-value">{new Date().toLocaleTimeString()}</span>
        </div>
      </div>
    </div>
  );
};

export default ModuleStatusBar;
