import React, { useEffect, useRef } from 'react';
import './ActivityLog.css';

export interface ActivityLogEntry {
  id: string;
  timestamp: Date;
  type: 'info' | 'success' | 'warning' | 'error';
  agent: string;
  message: string;
}

interface ActivityLogProps {
  activities: ActivityLogEntry[];
  maxEntries?: number;
  compact?: boolean;  // For sidebar mode
}

export const ActivityLog: React.FC<ActivityLogProps> = ({
  activities,
  maxEntries = 50,
  compact = false
}) => {
  // Remove duplicates based on message content and timestamp
  const uniqueActivities = React.useMemo(() => {
    const seen = new Set<string>();
    return activities.filter(activity => {
      const key = `${activity.message}-${activity.timestamp.getTime()}`;
      if (seen.has(key)) {
        return false;
      }
      seen.add(key);
      return true;
    });
  }, [activities]);

  const getIcon = (type: string) => {
    switch (type) {
      case 'success': return '✅';
      case 'error': return '❌';
      case 'warning': return '⚠️';
      default: return 'ℹ️';
    }
  };

  const getAgentIcon = (agent: string) => {
    switch (agent.toLowerCase()) {
      case 'orchestrator': return '🎯';
      case 'generator': return '🤖';
      case 'validator': return '✅';
      case 'ui_controller': return '📡';
      case 'backend': return '🔌';
      case 'system': return '⚙️';
      default: return '📌';
    }
  };

  const formatTime = (date: Date) => {
    return date.toLocaleTimeString('en-US', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  };

  // Show all unique activities (newest first)
  const displayedActivities = [...uniqueActivities].reverse();

  return (
    <div className={`activity-log ${compact ? 'compact' : ''}`}>
      <div className="activity-log-header">
        <h3>📝 Live Activity Log</h3>
        <span className="activity-count">
          {displayedActivities.length} {displayedActivities.length === 1 ? 'event' : 'events'}
        </span>
      </div>

      <div className="activity-log-content">
        {displayedActivities.length === 0 ? (
          <div className="empty-log">
            <span className="empty-icon">💤</span>
            <p>No activity yet</p>
          </div>
        ) : (
          <div className="activity-list">
            {displayedActivities.map((activity) => (
              <div key={activity.id} className={`activity-entry ${activity.type}`}>
                <div className="activity-time">{formatTime(activity.timestamp)}</div>
                <div className="activity-icon">{getIcon(activity.type)}</div>
                <div className="activity-agent">
                  <span className="agent-icon">{getAgentIcon(activity.agent)}</span>
                  <span className="agent-name">{activity.agent}</span>
                </div>
                <div className="activity-message">{activity.message}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
