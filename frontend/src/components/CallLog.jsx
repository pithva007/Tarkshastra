import React, { useEffect, useState } from 'react';
import axios from 'axios';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const STATUS_STYLES = {
  calling:  'bg-green-900 text-green-300',
  mock:     'bg-blue-900 text-blue-300',
  skipped:  'bg-gray-800 text-gray-400',
  error:    'bg-red-900 text-red-300',
  cooldown: 'bg-yellow-900 text-yellow-300',
};

const ROLE_ICONS = {
  police: '🚔',
  temple: '🛕',
  gsrtc:  '🚌',
  driver: '🚗',
};

export default function CallLog({ latestCallUpdate }) {
  const [calls,   setCalls]   = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchCalls = async () => {
    try {
      const res = await axios.get(`${API}/api/call-log?limit=20`);
      setCalls(res.data);
    } catch (e) {
      console.error('Call log fetch error:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchCalls(); }, []);

  // Refresh when new call_update arrives via WebSocket
  useEffect(() => {
    if (latestCallUpdate) fetchCalls();
  }, [latestCallUpdate]);

  // Manual test call trigger for demo
  const triggerTestCall = async () => {
    try {
      await axios.post(`${API}/api/call-alert`, {
        corridor:   'Ambaji',
        role:       'police',
        phone:      '', // leave empty — will show as mock
        cpi:        0.87,
        ttb_minutes: 9,
        surge_type: 'GENUINE_CRUSH',
        alert_id:   `DEMO_${Date.now()}`,
      });
      setTimeout(fetchCalls, 1000);
    } catch (e) {
      console.error(e);
    }
  };

  if (loading) {
    return <div className="text-gray-400 text-sm p-4">Loading call log...</div>;
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-white font-medium text-sm uppercase tracking-widest">
          Phone Call Log
        </h3>
        <button
          onClick={triggerTestCall}
          className="text-xs bg-red-600 hover:bg-red-500 text-white px-3 py-1 rounded transition"
        >
          🎙 Test Call (Demo)
        </button>
      </div>

      {calls.length === 0 ? (
        <div className="text-gray-500 text-sm text-center py-8">
          No calls triggered yet. Calls fire automatically when CPI ≥ 0.85.
        </div>
      ) : (
        <div className="space-y-2">
          {calls.map((call) => (
            <div
              key={call.id}
              className="bg-gray-800 rounded-lg p-3 border border-gray-700"
            >
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span className="text-lg">{ROLE_ICONS[call.role] || '📞'}</span>
                  <span className="text-white text-sm font-medium capitalize">{call.role}</span>
                  <span className="text-gray-400 text-xs">— {call.corridor}</span>
                </div>
                <span
                  className={`text-xs px-2 py-0.5 rounded font-medium ${
                    STATUS_STYLES[call.status] || STATUS_STYLES.skipped
                  }`}
                >
                  {call.status}
                </span>
              </div>

              <div className="flex items-center justify-between text-xs text-gray-400">
                <span>CPI: {call.cpi?.toFixed(2)} · {call.surge_type}</span>
                <span>{new Date(call.called_at).toLocaleTimeString()}</span>
              </div>

              {call.call_sid && (
                <div className="text-xs text-green-400 mt-1">SID: {call.call_sid}</div>
              )}
              {call.reason && call.status !== 'calling' && (
                <div className="text-xs text-gray-500 mt-1">Reason: {call.reason}</div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
