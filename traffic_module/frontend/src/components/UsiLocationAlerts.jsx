import React, { useEffect, useRef, useState } from 'react';
import { MapPin, Loader2, RefreshCw } from 'lucide-react';

// ================================================================
// "Current/Selected Area" detector -- the ONLY place in the app that
// talks to the browser Geolocation API. Both the USI page and the
// main Alerts tab render this same component so there is a single
// location system, not two.
//
// This component does not keep its own notion of "the detected area"
// for display -- it always shows `selectedArea` (the one shared
// source of truth owned by App.js / passed down as a prop). On a
// successful detection it calls `onSelectArea(area)`, exactly the
// same callback a search or a chip click already uses, so the USI
// score, the map, and the alerts section all move together with
// location the same way they already move together with search.
//
// Reuses, without modifying:
//   - navigator.geolocation (real browser permission prompt, never bypassed)
//   - GET /api/reverse-geocode?lat=&lon= -> the existing server-side
//     nearest-known-USI-area match (haversine, computed in
//     integration_bridge/ward data -- never recomputed or guessed here)
//
// Privacy: latitude/longitude are read once inside the getCurrentPosition
// success callback, used only to build the reverse-geocode request, and
// never stored or rendered. No GPS history. No phone number involved.
//
// Two distinct, opt-in mount-time behaviors (both off unless a caller
// asks for them, both guarded so they only ever run once on first mount
// and only when nothing is selected yet):
//   - `autoDetectOnMount` (default true): PASSIVE. If the browser already
//     has geolocation permission granted from an earlier visit, detect
//     silently rather than making the person click a button for
//     something they already agreed to. Never shows a permission prompt
//     on its own. Used by the USI page's locator.
//   - `autoRequestOnMount` (default false): ACTIVE. Immediately calls the
//     same requestLocation() a click would -- which shows the real
//     browser permission prompt if the person hasn't decided yet. Used
//     only by the Alerts tab, which is meant to use the person's current
//     area automatically without requiring a click.
//
// Both of the above are marked `auto` internally. An `auto` detection
// never overwrites a manually selected area -- not only is it skipped
// if one was already selected at mount (the `selectedArea` check
// below), it is ALSO skipped if the person searches for (or otherwise
// selects) an area while the detection is still in flight: browser
// geolocation + the reverse-geocode fetch can take a second or more,
// and a manual search started during that window must win. This is
// enforced with a ref that always holds the latest `selectedArea`
// (`selectedAreaRef`), checked right before an `auto` detection would
// apply its result -- never checked for a manual button click, which
// always applies immediately since that is a deliberate, in-the-moment
// choice by the person.
// ================================================================

const MAX_NEAREST_AREA_KM = 5;

const CurrentAreaLocator = ({ selectedArea, onSelectArea, autoDetectOnMount = true, autoRequestOnMount = false }) => {
  // idle | requesting | resolving | permission_denied | unavailable | no_coverage | error
  const [status, setStatus] = useState('idle');

  // Avoids applying a stale geolocation result if the user starts a new
  // detect/refresh (or searches elsewhere) before an earlier browser
  // geolocation call finishes.
  const requestIdRef = useRef(0);

  // Always holds the latest `selectedArea`, independent of render timing --
  // read (never relied on for re-rendering) inside the async geolocation/
  // reverse-geocode callbacks so an in-flight AUTOMATIC detection can tell
  // whether the person has since picked an area some other way (search, a
  // chip, etc.) and, if so, back off instead of clobbering that choice.
  const selectedAreaRef = useRef(selectedArea);
  useEffect(() => {
    selectedAreaRef.current = selectedArea;
  }, [selectedArea]);

  const requestLocation = (auto = false) => {
    if (!navigator.geolocation) {
      setStatus('unavailable');
      return;
    }
    const thisRequestId = ++requestIdRef.current;
    setStatus('requesting');

    navigator.geolocation.getCurrentPosition(
      async (position) => {
        if (thisRequestId !== requestIdRef.current) return;
        setStatus('resolving');
        try {
          // Read once here to ask the existing reverse-geocode endpoint for
          // the nearest known area, then immediately discarded -- never
          // stored, never rendered.
          const { latitude, longitude } = position.coords;
          const resp = await fetch(`/api/reverse-geocode?lat=${latitude}&lon=${longitude}`);
          if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
          const data = await resp.json();
          if (thisRequestId !== requestIdRef.current) return;

          if (!data.nearest_known_location || data.nearest_known_location_distance_km > MAX_NEAREST_AREA_KM) {
            setStatus('no_coverage');
            return;
          }

          // An automatic (mount-triggered) detection must never override an
          // area the person has since selected some other way (e.g. they
          // searched while this request was still in flight). A manual
          // button click (auto === false) always applies its result --
          // that is an explicit, in-the-moment choice, including
          // "Refresh Location" when an area is already selected.
          if (auto && selectedAreaRef.current) {
            setStatus('idle');
            return;
          }

          setStatus('idle');
          // Single shared selection state -- the same callback search and
          // chip-click already use, so USI + map + alerts all follow.
          if (onSelectArea) onSelectArea(data.nearest_known_location);
        } catch (e) {
          if (thisRequestId !== requestIdRef.current) return;
          setStatus('error');
        }
      },
      (err) => {
        if (thisRequestId !== requestIdRef.current) return;
        setStatus(err.code === 1 ? 'permission_denied' : 'unavailable');
      },
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 }
    );
  };

  // On first mount only, if nothing is selected yet: either passively
  // check for already-granted permission (autoDetectOnMount) or actively
  // request location right away (autoRequestOnMount) -- see the two
  // behaviors documented above the component. Both pass auto=true so a
  // manual search started while this is still resolving always wins (see
  // the selectedAreaRef check inside requestLocation above).
  useEffect(() => {
    let cancelled = false;
    if (!selectedArea) {
      if (autoRequestOnMount) {
        requestLocation(true);
      } else if (autoDetectOnMount && navigator.permissions && navigator.permissions.query) {
        navigator.permissions.query({ name: 'geolocation' })
          .then((result) => {
            if (cancelled || result.state !== 'granted') return;
            requestLocation(true);
          })
          .catch(() => {});
      }
    }
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const isBusy = status === 'requesting' || status === 'resolving';

  return (
    <div className="cc-panel" style={{ marginBottom: '1rem' }}>
      <div className="cc-panel-head">
        <p className="cc-panel-title"><MapPin size={13} className="cc-icon" /> Current Area</p>
      </div>

      {selectedArea && (
        <div style={{ fontSize: '0.9rem', color: 'var(--cc-text)', marginBottom: '0.3rem' }}>
          📍 Current / Selected Area: <strong>{selectedArea}</strong>
        </div>
      )}

      {isBusy && (
        <div className="cc-empty" style={{ textAlign: 'left', padding: '0.5rem 0' }}>
          <Loader2 size={13} className="cc-spin" style={{ verticalAlign: 'middle', marginRight: '0.4rem' }} />
          Detecting your current area...
        </div>
      )}

      {!isBusy && !selectedArea && status === 'idle' && (
        <>
          <p className="cc-panel-sub" style={{ marginBottom: '0.75rem' }}>
            Allow location access to see USI and civic alerts for your current area.
          </p>
          <button className="cc-btn-primary" onClick={() => requestLocation(false)}>
            📍 Use My Current Location
          </button>
        </>
      )}

      {!isBusy && status === 'permission_denied' && (
        <>
          <div className="cc-empty" style={{ textAlign: 'left', padding: '0.5rem 0' }}>
            Location permission was denied. You can search for an area instead.
          </div>
          <button className="cc-navlink" onClick={() => requestLocation(false)}>Try Again</button>
        </>
      )}

      {!isBusy && status === 'unavailable' && (
        <>
          <div className="cc-empty" style={{ textAlign: 'left', padding: '0.5rem 0' }}>
            Current location is temporarily unavailable. Please try again.
          </div>
          <button className="cc-navlink" onClick={() => requestLocation(false)}>Try Again</button>
        </>
      )}

      {!isBusy && status === 'no_coverage' && (
        <>
          <div className="cc-empty" style={{ textAlign: 'left', padding: '0.5rem 0' }}>
            Your current location could not be matched to a supported Bengaluru area.
          </div>
          <button className="cc-navlink" onClick={() => requestLocation(false)}>Try Again</button>
        </>
      )}

      {!isBusy && status === 'error' && (
        <>
          <div className="cc-empty" style={{ textAlign: 'left', padding: '0.5rem 0' }}>
            Current location is temporarily unavailable. Please try again.
          </div>
          <button className="cc-navlink" onClick={() => requestLocation(false)}>Try Again</button>
        </>
      )}

      {!isBusy && selectedArea && status === 'idle' && (
        <button
          className="cc-navlink"
          style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}
          onClick={() => requestLocation(false)}
        >
          <RefreshCw size={12} /> Refresh Location
        </button>
      )}
    </div>
  );
};

export default CurrentAreaLocator;
