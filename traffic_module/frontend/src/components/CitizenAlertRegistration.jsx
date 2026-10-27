import React, { useEffect, useMemo, useState } from 'react';
import { Bell, Smartphone, Globe, MapPin, CheckCircle2, XCircle, Loader2, Search, ShieldCheck, Trash2 } from 'lucide-react';

// Citizen registration & alert-preferences panel -- Stage 1 foundation.
//
// Talks only to the new /api/citizens/* endpoints (citizen_registry.py +
// citizen_otp.py). Never touches, duplicates, or re-implements the
// existing Traffic/Waste alert engines, the existing ephemeral browser-
// location mechanism, or anything ML/prediction-related.
//
// PRIVACY: a mobile number is never treated as a GPS location. "Ward /
// area" below is an explicit choice from the real ward registry
// (/api/wards/list, the same 369-ward source used elsewhere in this
// app); "location consent" is a stored PREFERENCE only -- no
// latitude/longitude is ever collected or stored by this panel.
//
// NO REAL SMS: verification codes are never claimed to be delivered.
// While the backend is in development mode (no SMS provider connected --
// see citizen_otp.py), the code is shown here directly in a clearly
// labeled "Development Mode" notice, exactly as the API response labels
// it. This panel never shows fabricated subscriber counts, delivery
// counts, WhatsApp/BHASHINI status, or GPS tracking -- none of that
// exists yet.

const LANGUAGES = [
  { code: 'English', label: 'English' },
  { code: 'Kannada', label: 'ಕನ್ನಡ Kannada' },
  { code: 'Hindi', label: 'हिन्दी Hindi' },
];

const LANGUAGE_CODE_TO_INTERNAL = { English: 'en', Kannada: 'kn', Hindi: 'hi' };

const LOCAL_STORAGE_KEY = 'bengaluruBrain.citizenId';

// FINAL FEATURE: how often an active, consenting citizen's browser
// re-reports its current position. Deliberately well under
// user_location_service.py's own 10-minute TTL so dispatch always sees
// a fresh coordinate, but not so frequent that it spams the browser's
// Geolocation API or the backend.
const LOCATION_UPDATE_INTERVAL_MS = 3 * 60 * 1000; // 3 minutes

function readStoredCitizenId() {
  try {
    const raw = window.localStorage.getItem(LOCAL_STORAGE_KEY);
    return raw ? Number(raw) : null;
  } catch {
    return null;
  }
}
function writeStoredCitizenId(id) {
  try {
    if (id == null) window.localStorage.removeItem(LOCAL_STORAGE_KEY);
    else window.localStorage.setItem(LOCAL_STORAGE_KEY, String(id));
  } catch {
    // Private browsing / storage disabled -- the panel still works for
    // this page view, it just won't remember the citizen on reload.
  }
}

const ToggleRow = ({ icon, label, hint, value, onChange, disabled }) => (
  <div className="cc-metric-tile" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.8rem' }}>
    <div style={{ minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: 'var(--cc-text)', fontSize: '0.86rem', fontWeight: 600 }}>
        {icon}{label}
      </div>
      {hint && <div style={{ fontSize: '0.74rem', color: 'var(--cc-text-faint)', marginTop: '0.2rem' }}>{hint}</div>}
    </div>
    <button
      type="button"
      className={`cc-navlink ${value ? 'active' : ''}`}
      style={{ fontSize: '0.76rem', padding: '0.4rem 0.85rem', flexShrink: 0 }}
      onClick={() => onChange(!value)}
      disabled={disabled}
    >
      {value ? <CheckCircle2 size={13} /> : <XCircle size={13} />} {value ? 'ON' : 'OFF'}
    </button>
  </div>
);

const CitizenAlertRegistration = () => {
  const [step, setStep] = useState('loading'); // loading | form | otp | profile
  const [wards, setWards] = useState([]);
  const [wardSearch, setWardSearch] = useState('');

  // registration form state
  const [mobileNumber, setMobileNumber] = useState('');
  const [language, setLanguage] = useState('English');
  const [trafficAlerts, setTrafficAlerts] = useState(true);
  const [wasteAlerts, setWasteAlerts] = useState(true);
  const [locationConsent, setLocationConsent] = useState(false);
  const [wardId, setWardId] = useState('');
  const [registerError, setRegisterError] = useState(null);
  const [registerLoading, setRegisterLoading] = useState(false);

  // otp state
  const [pendingCitizenId, setPendingCitizenId] = useState(null);
  const [pendingMobile, setPendingMobile] = useState(null);
  const [devOtp, setDevOtp] = useState(null); // {code, notice} | null
  const [otpCode, setOtpCode] = useState('');
  const [otpError, setOtpError] = useState(null);
  const [otpLoading, setOtpLoading] = useState(false);
  const [resendLoading, setResendLoading] = useState(false);

  // profile state
  const [citizen, setCitizen] = useState(null);
  const [patchError, setPatchError] = useState(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);

  // Stage 2: simulated alert-delivery status (pure read of this
  // citizen's own rows -- see /api/citizens/{id}/alert-deliveries)
  const [deliveries, setDeliveries] = useState([]);
  const [deliveriesLoading, setDeliveriesLoading] = useState(false);
  const [deliveriesError, setDeliveriesError] = useState(null);
  const [deliveriesChecked, setDeliveriesChecked] = useState(false);

  useEffect(() => {
    fetch('/api/wards/list')
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data && data.available) {
          setWards([...data.wards].sort((a, b) => (a.ward_name || '').localeCompare(b.ward_name || '')));
        }
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    const storedId = readStoredCitizenId();
    if (!storedId) {
      setStep('form');
      return;
    }
    fetch(`/api/citizens/${storedId}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data) {
          setCitizen(data);
          setStep('profile');
        } else {
          writeStoredCitizenId(null);
          setStep('form');
        }
      })
      .catch(() => setStep('form'));
  }, []);

  // FINAL FEATURE: while this citizen is an active, consenting
  // subscriber, periodically ask the BROWSER's own Geolocation API for
  // the current position and report it to the existing alert-dispatch
  // system, so proximity-based traffic alerts can use a live coordinate
  // instead of just the registered ward. Does not replace ward-based
  // matching -- the backend (citizen_alert_dispatch.py) falls back to
  // the ward centroid automatically whenever no fresh live position is
  // available (permission denied, unsupported browser, tab closed,
  // consent off, etc.) -- this effect never fabricates a location and
  // never bypasses the browser's own native permission prompt.
  useEffect(() => {
    // TEMPORARY DIAGNOSTIC LOGGING -- to be removed once the live-location
    // 404-free-but-no-POST issue is root-caused. Never logs latitude/longitude.
    console.log('[LOCATION_EFFECT] effect ran', {
      citizenId: citizen?.id,
      status: citizen?.status,
      location_consent: citizen?.location_consent,
      location_consent_type: typeof citizen?.location_consent,
    });

    if (!citizen || citizen.status !== 'active' || !citizen.location_consent) {
      console.log('[LOCATION_EFFECT] guard blocked -- not starting tracking', {
        hasCitizen: !!citizen,
        status: citizen?.status,
        location_consent: citizen?.location_consent,
      });
      return undefined;
    }
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      console.log('[LOCATION_EFFECT] no navigator.geolocation in this environment');
      return undefined; // no browser support -- existing ward-based behavior still applies
    }

    const citizenId = citizen.id;
    let cancelled = false;
    console.log('[LOCATION_EFFECT] guard passed -- starting tracking for citizenId', citizenId);

    const reportCurrentPosition = () => {
      console.log('[LOCATION_EFFECT] calling navigator.geolocation.getCurrentPosition', { citizenId, cancelled });
      navigator.geolocation.getCurrentPosition(
        (position) => {
          console.log('[LOCATION_EFFECT] getCurrentPosition success callback fired', { citizenId, cancelled });
          if (cancelled) {
            console.log('[LOCATION_EFFECT] skipping fetch -- this watcher was already cancelled', { citizenId });
            return;
          }
          console.log('[LOCATION_EFFECT] about to fetch POST location', { citizenId });
          fetch(`/api/citizens/${citizenId}/location`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              latitude: position.coords.latitude,
              longitude: position.coords.longitude,
            }),
          })
            .then((r) => {
              console.log('[LOCATION_EFFECT] POST response status', r.status);
              return r;
            })
            .catch((e) => {
              console.log('[LOCATION_EFFECT] POST fetch failed', String(e));
              // Best-effort -- a failed update simply leaves the existing
              // ward-based match in place for this dispatch run.
            });
        },
        (err) => {
          console.log('[LOCATION_EFFECT] getCurrentPosition error callback fired', { citizenId, code: err?.code, message: err?.message });
          // Permission denied / position unavailable / timed out --
          // silently keep the existing ward-based behavior, exactly as
          // if this citizen had never granted location consent.
        },
        { enableHighAccuracy: false, timeout: 30000, maximumAge: 60000 } // was 10000 -- too short for a cold Windows network-location lookup, causing automatic calls to time out (error code 3) while an unconstrained manual console call succeeds
      );
    };

    reportCurrentPosition(); // first reading right away
    const intervalId = window.setInterval(reportCurrentPosition, LOCATION_UPDATE_INTERVAL_MS);

    return () => {
      console.log('[LOCATION_EFFECT] cleanup running -- stopping tracking', { citizenId });
      cancelled = true;
      window.clearInterval(intervalId);
      // Explicit stop -- consent was turned off, the citizen became
      // inactive, or this panel/tab is closing. Best-effort: even if
      // this never reaches the server, the stored position still
      // expires on its own via user_location_service.py's TTL.
      fetch(`/api/citizens/${citizenId}/location`, { method: 'DELETE' }).catch(() => {});
    };
  }, [citizen?.id, citizen?.status, citizen?.location_consent]);

  const filteredWards = useMemo(() => {
    if (!wardSearch.trim()) return wards.slice(0, 200);
    const q = wardSearch.trim().toLowerCase();
    return wards.filter((w) => (w.ward_name || '').toLowerCase().includes(q) || String(w.ward_id).includes(q)).slice(0, 200);
  }, [wards, wardSearch]);

  const selectedWardName = useMemo(() => {
    const match = wards.find((w) => String(w.ward_id) === String(wardId));
    return match ? match.ward_name : null;
  }, [wards, wardId]);

  const startOtpStep = (citizenId, mobile, dev) => {
    setPendingCitizenId(citizenId);
    setPendingMobile(mobile);
    setDevOtp(dev && dev.dev_mode ? { code: dev.dev_otp, notice: dev.dev_notice } : null);
    setOtpCode('');
    setOtpError(null);
    setStep('otp');
  };

  const handleRegister = async () => {
    setRegisterError(null);
    setRegisterLoading(true);
    try {
      const resp = await fetch('/api/citizens/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mobile_number: mobileNumber,
          preferred_language: language,
          traffic_alerts_enabled: trafficAlerts,
          waste_alerts_enabled: wasteAlerts,
          location_consent: locationConsent,
          ward_id: wardId || null,
        }),
      });
      const data = await resp.json();

      if (resp.status === 409) {
        const existingId = data?.detail?.citizen_id;
        setRegisterError({
          message: data?.detail?.message || 'This mobile number is already registered.',
          existingCitizenId: existingId,
        });
        return;
      }
      if (!resp.ok) {
        setRegisterError({ message: typeof data?.detail === 'string' ? data.detail : 'Registration failed.' });
        return;
      }

      startOtpStep(data.citizen.id, data.citizen.mobile_number, data);
    } catch (e) {
      setRegisterError({ message: `Could not reach the server (${e.message}).` });
    } finally {
      setRegisterLoading(false);
    }
  };

  // "This number is already registered" -> re-send a code to prove it's
  // really this citizen's number, rather than silently logging them in.
  const handleReverifyExisting = async () => {
    if (!registerError?.existingCitizenId) return;
    setRegisterLoading(true);
    try {
      const resp = await fetch(`/api/citizens/${registerError.existingCitizenId}/resend-otp`, { method: 'POST' });
      const data = await resp.json();
      if (!resp.ok) {
        setRegisterError({ message: typeof data?.detail === 'string' ? data.detail : 'Could not resend a code.' });
        return;
      }
      startOtpStep(registerError.existingCitizenId, mobileNumber, data);
    } catch (e) {
      setRegisterError({ message: `Could not reach the server (${e.message}).` });
    } finally {
      setRegisterLoading(false);
    }
  };

  const handleVerify = async () => {
    setOtpError(null);
    setOtpLoading(true);
    try {
      const resp = await fetch('/api/citizens/verify-otp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mobile_number: pendingMobile, otp_code: otpCode }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        setOtpError(typeof data?.detail === 'string' ? data.detail : 'Verification failed.');
        return;
      }
      writeStoredCitizenId(data.citizen.id);
      setCitizen(data.citizen);
      setStep('profile');
    } catch (e) {
      setOtpError(`Could not reach the server (${e.message}).`);
    } finally {
      setOtpLoading(false);
    }
  };

  const handleResend = async () => {
    if (!pendingCitizenId) return;
    setResendLoading(true);
    setOtpError(null);
    try {
      const resp = await fetch(`/api/citizens/${pendingCitizenId}/resend-otp`, { method: 'POST' });
      const data = await resp.json();
      if (!resp.ok) {
        setOtpError(typeof data?.detail === 'string' ? data.detail : 'Could not resend a code.');
        return;
      }
      setDevOtp(data.dev_mode ? { code: data.dev_otp, notice: data.dev_notice } : null);
      setOtpCode('');
    } catch (e) {
      setOtpError(`Could not reach the server (${e.message}).`);
    } finally {
      setResendLoading(false);
    }
  };

  const patchCitizen = async (fields) => {
    if (!citizen) return;
    setPatchError(null);
    try {
      const resp = await fetch(`/api/citizens/${citizen.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(fields),
      });
      const data = await resp.json();
      if (!resp.ok) {
        setPatchError(typeof data?.detail === 'string' ? data.detail : 'Update failed.');
        return;
      }
      setCitizen(data);
    } catch (e) {
      setPatchError(`Could not reach the server (${e.message}).`);
    }
  };

  const checkDeliveries = async () => {
    if (!citizen) return;
    setDeliveriesLoading(true);
    setDeliveriesError(null);
    try {
      const resp = await fetch(`/api/citizens/${citizen.id}/alert-deliveries`);
      const data = await resp.json();
      if (!resp.ok) {
        setDeliveriesError(typeof data?.detail === 'string' ? data.detail : 'Could not check alert status.');
        return;
      }
      setDeliveries(data.deliveries || []);
      setDeliveriesChecked(true);
    } catch (e) {
      setDeliveriesError(`Could not reach the server (${e.message}).`);
    } finally {
      setDeliveriesLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!citizen) return;
    setDeleteLoading(true);
    try {
      const resp = await fetch(`/api/citizens/${citizen.id}`, { method: 'DELETE' });
      if (resp.ok) {
        writeStoredCitizenId(null);
        setCitizen(null);
        setConfirmingDelete(false);
        setMobileNumber('');
        setWardId('');
        setStep('form');
      }
    } finally {
      setDeleteLoading(false);
    }
  };

  const wardPickerField = (currentWardId, onSelect, disabled) => (
    <div className="cc-field">
      <label><MapPin size={11} style={{ verticalAlign: 'middle', marginRight: 3 }} />Your ward / area (optional)</label>
      <div style={{ display: 'flex', gap: '0.5rem' }}>
        <input
          type="text"
          placeholder="Search ward, e.g. Whitefield or 142"
          value={wardSearch}
          onChange={(e) => setWardSearch(e.target.value)}
          disabled={disabled}
        />
      </div>
      <select
        value={currentWardId || ''}
        onChange={(e) => onSelect(e.target.value)}
        disabled={disabled}
        style={{ marginTop: '0.4rem' }}
      >
        <option value="">No ward selected</option>
        {filteredWards.map((w) => (
          <option key={w.ward_id} value={w.ward_id}>{w.ward_name} (#{w.ward_id})</option>
        ))}
      </select>
    </div>
  );

  // ---------------- render: loading ----------------
  if (step === 'loading') {
    return <div className="cc-panel cc-empty"><Loader2 size={14} className="cc-spin" /> Loading your alert preferences…</div>;
  }

  // ---------------- render: registration form ----------------
  if (step === 'form') {
    return (
      <div className="cc-panel">
        <div className="cc-panel-head">
          <p className="cc-panel-title"><Bell size={13} className="cc-icon" /> Register for Citizen Alerts</p>
        </div>
        <p className="cc-panel-sub" style={{ marginBottom: '0.9rem' }}>
          Get bilingual Traffic and Waste alerts for your area. This is a new, foundational sign-up step —
          alert delivery itself (real SMS) is not connected yet; see the notice after you register.
        </p>

        <div className="cc-field" style={{ maxWidth: 320 }}>
          <label><Smartphone size={11} style={{ verticalAlign: 'middle', marginRight: 3 }} />Mobile number</label>
          <input
            type="tel"
            placeholder="e.g. 9876543210"
            value={mobileNumber}
            onChange={(e) => setMobileNumber(e.target.value)}
          />
        </div>

        <div style={{ marginTop: '0.9rem' }}>
          <label style={{ fontSize: '0.76rem', color: 'var(--cc-text-dim)', fontWeight: 600, display: 'block', marginBottom: '0.4rem' }}>
            <Globe size={11} style={{ verticalAlign: 'middle', marginRight: 3 }} />Preferred language
          </label>
          <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
            {LANGUAGES.map((l) => (
              <button
                key={l.code}
                type="button"
                className={`cc-navlink ${language === l.code ? 'active' : ''}`}
                style={{ fontSize: '0.78rem', padding: '0.45rem 0.9rem' }}
                onClick={() => setLanguage(l.code)}
              >
                {l.label}
              </button>
            ))}
          </div>
        </div>

        <div style={{ marginTop: '0.9rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          <ToggleRow icon="🚦" label="Traffic alerts" hint="Unexpected traffic incidents near your area" value={trafficAlerts} onChange={setTrafficAlerts} />
          <ToggleRow icon="🗑️" label="Waste alerts" hint="Rising waste/traffic risk (USI) in your area" value={wasteAlerts} onChange={setWasteAlerts} />
          <ToggleRow
            icon="📍"
            label="Location-based alert consent"
            hint="A preference only — no GPS coordinates are collected here. Your browser's own location permission (used elsewhere in this app) is separate."
            value={locationConsent}
            onChange={setLocationConsent}
          />
        </div>

        <div style={{ marginTop: '0.9rem' }}>{wardPickerField(wardId, setWardId, false)}</div>

        {registerError && (
          <div className="cc-metric-tile" style={{ marginTop: '0.9rem', borderLeft: '3px solid var(--cc-red)' }}>
            <div style={{ color: 'var(--cc-text)', fontSize: '0.82rem' }}>{registerError.message}</div>
            {registerError.existingCitizenId && (
              <button
                type="button"
                className="cc-navlink"
                style={{ marginTop: '0.5rem', fontSize: '0.76rem', padding: '0.35rem 0.7rem' }}
                onClick={handleReverifyExisting}
                disabled={registerLoading}
              >
                This is my number — send a new verification code
              </button>
            )}
          </div>
        )}

        <button
          className="cc-btn-primary"
          style={{ marginTop: '1rem' }}
          onClick={handleRegister}
          disabled={registerLoading || !mobileNumber}
        >
          {registerLoading ? 'Sending…' : 'Send verification code'}
        </button>
      </div>
    );
  }

  // ---------------- render: OTP verification ----------------
  if (step === 'otp') {
    return (
      <div className="cc-panel">
        <div className="cc-panel-head">
          <p className="cc-panel-title"><ShieldCheck size={13} className="cc-icon" /> Verify your mobile number</p>
        </div>

        {devOtp ? (
          <div className="cc-metric-tile" style={{ borderLeft: '3px solid var(--cc-yellow)', marginBottom: '0.9rem' }}>
            <div style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--cc-yellow)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Development Mode — not sent by SMS
            </div>
            <div style={{ marginTop: '0.35rem', fontSize: '0.78rem', color: 'var(--cc-text-dim)' }}>{devOtp.notice}</div>
            <div style={{ marginTop: '0.5rem', fontFamily: 'var(--cc-font-display)', fontSize: '1.3rem', fontWeight: 700, letterSpacing: '0.15em', color: 'var(--cc-text)' }}>
              {devOtp.code}
            </div>
          </div>
        ) : (
          <p className="cc-panel-sub" style={{ marginBottom: '0.9rem' }}>Enter the verification code sent to {pendingMobile}.</p>
        )}

        <div className="cc-field" style={{ maxWidth: 220 }}>
          <label>6-digit code</label>
          <input
            type="text"
            inputMode="numeric"
            maxLength={6}
            value={otpCode}
            onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, ''))}
            placeholder="123456"
          />
        </div>

        {otpError && (
          <div className="cc-metric-tile" style={{ marginTop: '0.7rem', borderLeft: '3px solid var(--cc-red)', color: 'var(--cc-text)', fontSize: '0.82rem' }}>
            {otpError}
          </div>
        )}

        <div style={{ display: 'flex', gap: '0.6rem', marginTop: '1rem', alignItems: 'center' }}>
          <button className="cc-btn-primary" onClick={handleVerify} disabled={otpLoading || otpCode.length !== 6}>
            {otpLoading ? 'Verifying…' : 'Verify'}
          </button>
          <button className="cc-navlink" style={{ fontSize: '0.78rem', padding: '0.45rem 0.9rem' }} onClick={handleResend} disabled={resendLoading}>
            {resendLoading ? 'Resending…' : 'Resend code'}
          </button>
        </div>
      </div>
    );
  }

  // ---------------- render: profile / manage subscription ----------------
  if (step === 'profile' && citizen) {
    const statusPill = citizen.status === 'active' ? 'low' : citizen.status === 'inactive' ? 'neutral' : 'medium';
    const statusLabel = citizen.status === 'active' ? 'Active' : citizen.status === 'inactive' ? 'Inactive' : 'Pending verification';

    return (
      <div className="cc-panel">
        <div className="cc-panel-head">
          <p className="cc-panel-title"><Bell size={13} className="cc-icon" /> My Alert Subscription</p>
          <span className={`cc-pill ${statusPill}`}>{statusLabel}</span>
        </div>

        <div className="cc-metric-tile" style={{ marginBottom: '0.9rem' }}>
          <div className="cc-mt-label">Mobile number</div>
          <div style={{ color: 'var(--cc-text)', fontSize: '0.88rem', marginTop: '0.2rem' }}>{citizen.mobile_number}</div>
        </div>

        {!citizen.mobile_verified && (
          <div className="cc-metric-tile" style={{ marginBottom: '0.9rem', borderLeft: '3px solid var(--cc-orange)' }}>
            <div style={{ fontSize: '0.82rem', color: 'var(--cc-text)' }}>Verification wasn't completed.</div>
            <button
              type="button"
              className="cc-navlink"
              style={{ marginTop: '0.5rem', fontSize: '0.76rem', padding: '0.35rem 0.7rem' }}
              onClick={() => startOtpStep(citizen.id, citizen.mobile_number, null)}
            >
              Finish verification
            </button>
          </div>
        )}

        <div style={{ marginBottom: '0.9rem' }}>
          <label style={{ fontSize: '0.76rem', color: 'var(--cc-text-dim)', fontWeight: 600, display: 'block', marginBottom: '0.4rem' }}>
            <Globe size={11} style={{ verticalAlign: 'middle', marginRight: 3 }} />Preferred language
          </label>
          <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
            {LANGUAGES.map((l) => (
              <button
                key={l.code}
                type="button"
                className={`cc-navlink ${LANGUAGE_CODE_TO_INTERNAL[l.code] === citizen.preferred_language ? 'active' : ''}`}
                style={{ fontSize: '0.78rem', padding: '0.45rem 0.9rem' }}
                onClick={() => patchCitizen({ preferred_language: l.code })}
              >
                {l.label}
              </button>
            ))}
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginBottom: '0.9rem' }}>
          <ToggleRow icon="🚦" label="Traffic alerts" value={citizen.traffic_alerts_enabled} onChange={(v) => patchCitizen({ traffic_alerts_enabled: v })} />
          <ToggleRow icon="🗑️" label="Waste alerts" value={citizen.waste_alerts_enabled} onChange={(v) => patchCitizen({ waste_alerts_enabled: v })} />
          <ToggleRow icon="📍" label="Location-based alert consent" value={citizen.location_consent} onChange={(v) => patchCitizen({ location_consent: v })} />
        </div>

        <div style={{ marginBottom: '0.9rem' }}>
          {wardPickerField(citizen.ward_id, (v) => patchCitizen({ ward_id: v }), false)}
          {citizen.ward_name && (
            <div style={{ fontSize: '0.74rem', color: 'var(--cc-text-faint)', marginTop: '0.3rem' }}>Currently: {citizen.ward_name}</div>
          )}
        </div>

        {patchError && (
          <div className="cc-metric-tile" style={{ marginBottom: '0.9rem', borderLeft: '3px solid var(--cc-red)', fontSize: '0.82rem', color: 'var(--cc-text)' }}>
            {patchError}
          </div>
        )}

        <div className="cc-metric-tile" style={{ marginBottom: '0.9rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.6rem', flexWrap: 'wrap' }}>
            <div className="cc-mt-label">Alert delivery status (simulated)</div>
            <button
              type="button"
              className="cc-navlink"
              style={{ fontSize: '0.74rem', padding: '0.35rem 0.7rem' }}
              onClick={checkDeliveries}
              disabled={deliveriesLoading}
            >
              {deliveriesLoading ? 'Checking…' : 'Check for alerts now'}
            </button>
          </div>
          <div style={{ fontSize: '0.72rem', color: 'var(--cc-text-faint)', marginTop: '0.3rem' }}>
            No real SMS is sent yet -- this shows genuine simulated deliveries recorded against your own
            registration only, never a subscriber or delivery count for anyone else.
          </div>

          {deliveriesError && (
            <div style={{ marginTop: '0.6rem', fontSize: '0.78rem', color: 'var(--cc-red, #d9534f)' }}>{deliveriesError}</div>
          )}

          {deliveriesChecked && !deliveriesError && deliveries.length === 0 && (
            <div style={{ marginTop: '0.6rem', fontSize: '0.8rem', color: 'var(--cc-text-dim)' }}>
              No simulated alerts have been delivered to you yet.
            </div>
          )}

          {deliveries.length > 0 && (
            <div style={{ marginTop: '0.6rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {deliveries.map((d) => (
                <div key={d.id} style={{ borderLeft: '3px solid var(--cc-accent, #4a90d9)', paddingLeft: '0.6rem' }}>
                  <div style={{ fontSize: '0.72rem', color: 'var(--cc-text-faint)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    {d.alert_source === 'traffic' ? 'Traffic incident' : 'Urban Severity (traffic + waste)'} · {new Date(d.delivered_at).toLocaleString()}
                  </div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--cc-text)', marginTop: '0.15rem' }}>
                    Sent in {d.language_sent === 'kn' ? 'Kannada' : 'English'}
                    {d.language_fallback === 'hi_not_yet_supported_sent_en' && ' (Hindi not supported yet -- sent in English)'}
                    {' · '}{d.status === 'SIMULATED_NOT_SENT' ? 'Simulated -- not actually sent by SMS' : d.status}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap' }}>
          {citizen.mobile_verified && (
            <button
              className="cc-navlink"
              style={{ fontSize: '0.78rem', padding: '0.5rem 1rem' }}
              onClick={() => patchCitizen({ status: citizen.status === 'active' ? 'inactive' : 'active' })}
            >
              {citizen.status === 'active' ? 'Deactivate subscription' : 'Activate subscription'}
            </button>
          )}

          {!confirmingDelete ? (
            <button
              className="cc-navlink"
              style={{ fontSize: '0.78rem', padding: '0.5rem 1rem', color: 'var(--cc-red)' }}
              onClick={() => setConfirmingDelete(true)}
            >
              <Trash2 size={12} style={{ verticalAlign: 'middle', marginRight: 4 }} />Remove my registration
            </button>
          ) : (
            <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.78rem', color: 'var(--cc-text-dim)' }}>
              Remove permanently?
              <button className="cc-navlink" style={{ fontSize: '0.76rem', padding: '0.35rem 0.7rem', color: 'var(--cc-red)' }} onClick={handleDelete} disabled={deleteLoading}>
                {deleteLoading ? 'Removing…' : 'Yes, remove'}
              </button>
              <button className="cc-navlink" style={{ fontSize: '0.76rem', padding: '0.35rem 0.7rem' }} onClick={() => setConfirmingDelete(false)}>
                Cancel
              </button>
            </span>
          )}
        </div>
      </div>
    );
  }

  return null;
};

export default CitizenAlertRegistration;
