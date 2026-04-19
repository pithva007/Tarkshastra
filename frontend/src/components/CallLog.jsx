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

// SVG icons for each role
const ROLE_ICONS_SVG = {
  police: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-blue-400">
      <path d="M12 2L4 6v6c0 5.25 3.5 10.15 8 11.5C16.5 22.15 20 17.25 20 12V6L12 2z"/>
      <path d="M9 12l2 2 4-4"/>
    </svg>
  ),
  temple: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-yellow-400">
      <path d="M12 2L2 7h20L12 2z"/>
      <rect x="4" y="7" width="16" height="13"/>
      <rect x="9" y="12" width="6" height="8"/>
      <line x1="12" y1="2" x2="12" y2="7"/>
    </svg>
  ),
  gsrtc: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-green-400">
      <rect x="1" y="6" width="22" height="13" rx="2"/>
      <path d="M16 6V4a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2"/>
      <circle cx="7" cy="19" r="2"/><circle cx="17" cy="19" r="2"/>
      <line x1="9" y1="19" x2="15" y2="19"/>
    </svg>
  ),
  driver: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-gray-300">
      <rect x="1" y="10" width="22" height="9" rx="2"/>
      <path d="M5 10V7a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v3"/>
      <circle cx="7" cy="19" r="2"/><circle cx="17" cy="19" r="2"/>
    </svg>
  ),
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
          className="text-xs bg-red-600 hover:bg-red-500 text-white px-3 py-1 rounded transition flex items-center gap-1"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>
          Test Call (Demo)
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
                  <span className="text-lg">{ROLE_ICONS_SVG[call.role] || (
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07A19.5 19.5 0 0 1 4.69 13.5a19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 3.44 2.68h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L7.91 10.09a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z"/></svg>
                  )}</span>
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
