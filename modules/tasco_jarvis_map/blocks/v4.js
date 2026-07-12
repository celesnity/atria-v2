/* Marlow Bay Agent v4 ("meander") — map-first agent UI.  Phase A: the shell.
 *
 * The agent IS the interface and the MAP answers.  No persistent chat panel —
 * a floating command pill routes intents; every reply materializes as a map
 * artifact (surfaced pins, spotlight, pin-anchored callout, HUD-rail cards).
 * Conversation is transient (a fading card) with a pull-up PiP history.
 *
 * Self-contained block, loaded by dashboard.html in place of the retired
 * group_drive.js.  Reuses the shell only through V4.init(hooks):
 *   {map, applyActionsLegacy, askJarvis, esc, AtriaDash}
 * v4 owns its OWN Leaflet layers (v4PinLayer, v4RouteLayer) so it can tear them
 * down cleanly on toggle — it never persists pins through applyActionsLegacy,
 * whose shell layers have no design-mode scoping and would bleed into legacy.
 *
 * Backends (frozen, eval-gated): jarvis_chat.py, search.py, group_drive.py.
 */
(function () {
  'use strict';

  var H = null;                 // hooks from dashboard.html
  var map = null;               // shared Leaflet map
  var esc = function (s) { return s == null ? '' : String(s); };
  var v4PinLayer = null;        // v4's surfaced pins (violet teardrops)
  var v4RouteLayer = null;      // v4's own dashed route line
  var els = {};                 // cached DOM refs

  var S = {
    msgs: [],                   // [{role:'user'|'ai', text}]
    saved: {},                  // poi_id -> poi
    surfaced: {},               // poi_id -> {poi, marker, n}
    spot: null,                 // {pois, holes:[circle], badges:[el]}
    callout: null,              // {poi, latlng}
    route: null,                // {stops:[poi], mode}
    working: false,
    sessionId: null,
    transTimer: null,
    repoRaf: 0,
    // ── Phase B: team mode (Track-7 sim) ──
    group: null, tl: null, t: 0, playing: false, speed: 1, timer: null,
    delivered: {}, markers: {}, teamChat: [], unread: 0, dockView: 'members',
    sosMember: null, callTimer: null, callSec: 0,
    muted: false, unmuteAt: null, viewAs: 'member', selfWarnUntil: 0,
    summaryShown: false, teamBusy: false, alertMembers: {},
    // ── Phase C: real local voice session (LiveKit console worker) ──
    voice: null,                // {sid, lastSeq, timer} while a mic session is live
  };
  var v4TeamLayer = null, v4TeamRouteLayer = null, v4TeamPoiLayer = null, v4TrafficLayer = null;

  var $ = function (id) { return document.getElementById(id); };
  function el(html) {
    var t = document.createElement('template');
    t.innerHTML = String(html).trim();
    return t.content.firstElementChild;
  }
  function stopProp(e) { e.stopPropagation(); }
  function toast(message, severity) {
    try { H.AtriaDash.toast({ message: message, severity: severity || 'info' }); } catch (x) {}
  }
  // Every floating element stops pointerdown so Leaflet's pointer capture can't
  // eat the click (the layer-safety rule).
  function guard(node) {
    if (node) node.addEventListener('pointerdown', stopProp);
    return node;
  }

  /* ── DOM ──────────────────────────────────────────────────────────────── */
  function buildDom() {
    document.body.appendChild(el(
      '<button id="designToggle" title="Doi giao dien / switch design"></button>'));

    var app = el('<div id="v4App"></div>');

    // spotlight scrim (SVG mask punches holes at result pins)
    app.appendChild(el(
      '<div id="v4Spot">' +
        '<svg><defs><mask id="v4Holes">' +
          '<rect x="0" y="0" width="100%" height="100%" fill="#fff"></rect>' +
        '</mask></defs>' +
        '<rect x="0" y="0" width="100%" height="100%" class="v4-spot-scrim" mask="url(#v4Holes)"></rect>' +
        '</svg>' +
      '</div>'));

    // pin-anchored callout
    app.appendChild(el('<div id="v4Callout"></div>'));

    // HUD rail (route/team/video cards)
    app.appendChild(el('<div id="v4Rail"></div>'));

    // traffic toggle (top-right, left of the shell control column)
    app.appendChild(guard(el('<button id="v4Traffic" title="Traffic">&#9677; Traffic</button>')));

    // PiP history
    app.appendChild(el(
      '<div id="v4Pip">' +
        '<div class="v4-pip-head">' +
          '<span class="v4-pip-title">meander&deg; &mdash; history</span>' +
          '<button id="v4PipClose" title="Collapse">&#9601;</button>' +
        '</div>' +
        '<div class="v4-pip-body" id="v4PipBody"></div>' +
      '</div>'));

    // bottom stack: carousel (spotlight results) + transient reply + command pill
    var bottom = el('<div class="v4-bottom"></div>');
    bottom.appendChild(el('<div id="v4Carousel"></div>'));
    bottom.appendChild(el(
      '<div id="v4Trans">' +
        '<button class="v4-trans-close" id="v4TransClose">&#10005;</button>' +
        '<div class="v4-trans-steps" id="v4TransSteps"></div>' +
        '<div class="v4-trans-text" id="v4TransText"></div>' +
        '<div class="v4-chips" id="v4TransChips"></div>' +
      '</div>'));
    bottom.appendChild(el(
      '<div id="v4Pill">' +
        '<button class="v4-hist-btn" id="v4Hist" title="History">&#8963;</button>' +
        '<button class="v4-orb" id="v4Orb" type="button" ' +
          'title="Gợi ý / Suggestions">&#10022;</button>' +
        '<input id="v4Input" type="text" autocomplete="off" ' +
          'placeholder="Ask the map anything &mdash; or paste a video link&hellip;" />' +
        '<button class="v4-mic" id="v4Mic" title="Voice">&#127908;</button>' +
        '<button class="v4-go" id="v4Go" title="Send">&#8594;</button>' +
      '</div>'));
    app.appendChild(bottom);

    document.body.appendChild(app);

    // cache + guard interactive surfaces
    ['v4Spot', 'v4Callout', 'v4Rail', 'v4Pip', 'v4Carousel', 'v4Trans', 'v4Pill',
     'v4Input', 'v4PipBody', 'v4TransSteps', 'v4TransText', 'v4TransChips']
      .forEach(function (id) { els[id] = $(id); });
    [els.v4Callout, els.v4Rail, els.v4Pip, els.v4Trans, els.v4Pill, els.v4Carousel]
      .forEach(guard);
    // spotlight scrim: click outside a hole dismisses
    els.v4Spot.addEventListener('pointerdown', stopProp);
    els.v4Spot.addEventListener('click', function () { closeSpotlight(); });
  }

  /* ── surfaced pins ─────────────────────────────────────────────────────── */
  function pinIcon(label, saved) {
    return new L.DivIcon({
      html: '<div class="v4-pin' + (saved ? ' saved' : '') + '">' + esc(label) + '</div>',
      className: 'v4-pin-divicon', iconSize: [26, 26], iconAnchor: [13, 26],
    });
  }
  function surfacePin(poi, label) {
    if (poi == null || poi.lat == null) return null;
    var saved = !!S.saved[poi.poi_id];
    var m = new L.Marker([poi.lat, poi.lng],
      { icon: pinIcon(saved ? '♥' : label, saved), title: poi.name, zIndexOffset: 900 });
    m.on('click', function () { openCallout(poi); });
    v4PinLayer.addLayer(m);
    S.surfaced[poi.poi_id] = { poi: poi, marker: m, n: label };
    return m;
  }
  function clearSurfaced(keepSaved) {
    v4PinLayer.clearLayers();
    S.surfaced = {};
    if (keepSaved) {
      Object.keys(S.saved).forEach(function (id) { surfacePin(S.saved[id], '♥'); });
    }
  }
  function pulsePin(poi_id, on) {
    var s = S.surfaced[poi_id];
    if (!s || !s.marker._icon) return;
    var d = s.marker._icon.querySelector('.v4-pin');
    if (d) d.classList.toggle('pulse', !!on);
  }

  /* ── screen-space projection (spotlight holes + callout) ───────────────── */
  function project(lat, lng) { return map.latLngToContainerPoint([lat, lng]); }
  function scheduleReposition() {
    if (S.repoRaf) return;
    S.repoRaf = requestAnimationFrame(function () { S.repoRaf = 0; reposition(); });
  }
  function reposition() {
    if (S.spot) {
      S.spot.pois.forEach(function (p, i) {
        var pt = project(p.lat, p.lng);
        var c = S.spot.holes[i];
        // the numbered pin's body sits ~13px above its bottom-tip anchor —
        // frame the pin body, not the tip.
        if (c) { c.setAttribute('cx', pt.x); c.setAttribute('cy', pt.y - 13); }
      });
    }
    if (S.callout) {
      var q = project(S.callout.latlng[0], S.callout.latlng[1]);
      var co = els.v4Callout;
      // clamp horizontally so the bubble stays on screen; arrow tracks the pin
      var w = co.offsetWidth || 244, half = w / 2;
      var x = Math.max(half + 8, Math.min(q.x, window.innerWidth - half - 8));
      co.style.left = x + 'px';
      co.style.top = (q.y - 16) + 'px';   // sit just above the pin head
    }
  }

  /* ── spotlight (§2.4) ──────────────────────────────────────────────────── */
  function openSpotlight(pois) {
    closeSpotlight();
    if (!pois || !pois.length) return;
    var mask = els.v4Spot.querySelector('#v4Holes');
    var holes = [];
    // Numbered pins carry the index and move natively with the map — the
    // spotlight only punches a hole to frame each; no separate screen-space
    // badge (that doubled the numbering and needed reprojection).
    pois.forEach(function (p) {
      var c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      c.setAttribute('r', 34); c.setAttribute('fill', '#000');
      mask.appendChild(c); holes.push(c);
    });
    S.spot = { pois: pois, holes: holes };
    els.v4Spot.classList.add('on');
    reposition();
  }
  function closeSpotlight() {
    if (!S.spot) return;
    S.spot.holes.forEach(function (c) { if (c.parentNode) c.parentNode.removeChild(c); });
    S.spot = null;
    els.v4Spot.classList.remove('on');
    renderCarousel(null);
  }

  function renderCarousel(pois) {
    var car = els.v4Carousel;
    car.innerHTML = '';
    if (!pois || !pois.length) { car.classList.remove('on'); return; }
    pois.forEach(function (p, i) {
      var meta = (p.rating ? '<span class="star">&#9733;</span> ' + esc(p.rating) + ' &middot; ' : '')
        + esc(p.district || p.detail || p.city || '');
      var card = el(
        '<div class="v4-card">' +
          '<div class="v4-card-top"><span class="v4-card-n">' + (i + 1) + '</span>' +
            '<span class="v4-card-name">' + esc(p.name) + '</span></div>' +
          '<div class="v4-card-meta">' + meta + '</div>' +
          (p.dist_label ? '<div class="v4-card-dist">' + esc(p.dist_label) + '</div>' : '') +
        '</div>');
      card.addEventListener('mouseenter', function () { pulsePin(p.poi_id, true); });
      card.addEventListener('mouseleave', function () { pulsePin(p.poi_id, false); });
      card.addEventListener('click', function () {
        map.flyTo([p.lat, p.lng], Math.max(map.getZoom(), 15));
        openCallout(p);
      });
      car.appendChild(card);
    });
    car.classList.add('on');
  }

  /* ── place callout (§2.6) ──────────────────────────────────────────────── */
  function calloutTldr(poi) {
    // Honest one-liner from the fields jarvis/search return — no fabrication.
    if (poi.summary) return esc(poi.summary);
    var bits = [];
    if (poi.category_label || poi.category) bits.push(esc(poi.category_label || poi.category));
    if (poi.district) bits.push(esc(poi.district));
    if (poi.opening_hours) bits.push(esc(poi.opening_hours));
    return bits.length ? bits.join(' &middot; ') : esc(poi.detail || 'Xem tren ban do / on the map');
  }
  function openCallout(poi) {
    if (!poi || poi.lat == null) return;
    closeCallout();
    var saved = !!S.saved[poi.poi_id];
    var meta = (poi.rating ? '<span class="star">&#9733; ' + esc(poi.rating) + '</span> &middot; ' : '')
      + esc(poi.district || poi.city || poi.detail || '');
    var co = els.v4Callout;
    co.innerHTML =
      '<div class="v4-co-head">' +
        '<span class="v4-co-name">' + esc(poi.name) + '</span>' +
        '<button class="v4-co-save' + (saved ? ' on' : '') + '" title="Save">&#9829;</button>' +
        '<button class="v4-co-pop" title="Pop out">&#9099;</button>' +
        '<button class="v4-co-close" title="Close">&#10005;</button>' +
      '</div>' +
      '<div class="v4-co-body">' +
        '<div class="v4-co-meta">' + meta + '</div>' +
        '<div class="v4-co-tldr"><b>&#10022; tl;dr</b> &mdash; ' + calloutTldr(poi) + '</div>' +
      '</div>' +
      '<div class="v4-co-actions">' +
        '<button class="v4-co-route">Route me there</button>' +
        '<button class="v4-co-stop">+ Stop</button>' +
      '</div>';
    co.querySelector('.v4-co-close').addEventListener('click', closeCallout);
    co.querySelector('.v4-co-save').addEventListener('click', function () { toggleSave(poi, this); });
    co.querySelector('.v4-co-pop').addEventListener('click', function () { openPopout(poi); });
    co.querySelector('.v4-co-route').addEventListener('click', function () { routeToPoi(poi); });
    co.querySelector('.v4-co-stop').addEventListener('click', function () { addStop(poi); });
    guard(co);
    S.callout = { poi: poi, latlng: [poi.lat, poi.lng] };
    // ensure the target pin exists (a lone callout still shows its pin)
    if (!S.surfaced[poi.poi_id]) surfacePin(poi, '◉');
    co.classList.add('on');
    reposition();
  }
  function closeCallout() {
    S.callout = null;
    els.v4Callout.classList.remove('on');
  }
  function toggleSave(poi, btn) {
    if (S.saved[poi.poi_id]) { delete S.saved[poi.poi_id]; if (btn) btn.classList.remove('on'); }
    else { S.saved[poi.poi_id] = poi; if (btn) btn.classList.add('on'); }
    var s = S.surfaced[poi.poi_id];
    if (s && s.marker._icon) {
      var d = s.marker._icon.querySelector('.v4-pin');
      if (d) { d.classList.toggle('saved', !!S.saved[poi.poi_id]); d.textContent = S.saved[poi.poi_id] ? '♥' : s.n; }
    }
  }

  /* ── HUD rail + route card (§2.8) ──────────────────────────────────────── */
  var MODES = [
    { key: 'drive', label: 'Drive', kmh: 34 },
    { key: 'walk', label: 'Walk', kmh: 4.8 },
    { key: 'bike', label: 'Bike', kmh: 15 },
  ];
  function haversineKm(a, b, c, d) {
    var R = 6371, dLat = (c - a) * Math.PI / 180, dLng = (d - b) * Math.PI / 180;
    var s = Math.sin(dLat / 2) * Math.sin(dLat / 2)
      + Math.cos(a * Math.PI / 180) * Math.cos(c * Math.PI / 180)
      * Math.sin(dLng / 2) * Math.sin(dLng / 2);
    return R * 2 * Math.atan2(Math.sqrt(s), Math.sqrt(1 - s));
  }
  function routeKm(stops) {
    var km = 0;
    for (var i = 1; i < stops.length; i++) {
      km += haversineKm(stops[i - 1].lat, stops[i - 1].lng, stops[i].lat, stops[i].lng);
    }
    return km;
  }
  function etaLabel(km, kmh) {
    var min = Math.max(1, Math.round(km / kmh * 60));
    return min >= 60 ? Math.floor(min / 60) + 'h ' + (min % 60) + 'm' : min + ' min';
  }
  function drawV4Route(stops) {
    v4RouteLayer.clearLayers();
    if (stops.length < 2) return;
    var pts = stops.map(function (s) { return [s.lat, s.lng]; });
    var accent = (getComputedStyle(document.documentElement)
      .getPropertyValue('--accent') || '#e2683f').trim();
    v4RouteLayer.addLayer(new L.Polyline(pts,
      { color: accent, weight: 4, opacity: .9, dashArray: '9,10', lineCap: 'round' }));
  }
  function showRouteCard() {
    var st = S.route;
    if (!st || st.stops.length < 2) return;
    var mode = MODES.filter(function (m) { return m.key === st.mode; })[0] || MODES[0];
    var km = routeKm(st.stops);
    var kmh = mode.kmh / (S.traffic ? 1.3 : 1);   // traffic bumps ETA (§2.14)
    var railCard = el('<div class="v4-rail-card" id="v4RouteCard"></div>');
    railCard.innerHTML =
      '<div class="v4-rc-head"><span class="v4-rc-title">Route</span>' +
        '<button class="v4-rc-x" title="Close">&#10005;</button></div>' +
      '<div class="v4-route-eta"><span class="big">' + etaLabel(km, kmh) + '</span>' +
        '<span class="sub">' + km.toFixed(1) + ' km &middot; ' + esc(mode.label)
        + (S.traffic ? ' &middot; &#9677; traffic' : '') + '</span></div>' +
      '<div class="v4-route-stops"></div>' +
      '<div class="v4-route-modes"></div>' +
      '<div class="v4-route-foot">' +
        '<button class="go">Start</button>' +
        (st.stops.length >= 4 ? '<button class="opt">&#10022; Optimize</button>' : '') +
      '</div>';
    var stopsBox = railCard.querySelector('.v4-route-stops');
    st.stops.forEach(function (s, i) {
      var badge = i === 0 ? 'a' : (i === st.stops.length - 1 ? 'b' : '');
      var lbl = i === 0 ? 'A' : (i === st.stops.length - 1 ? 'B' : String(i));
      var row = el(
        '<div class="v4-route-stop"><span class="badge ' + badge + '">' + lbl + '</span>' +
          '<span class="nm">' + esc(s.name) + '</span>' +
          (st.stops.length > 2 ? '<button class="rm" title="Remove">&#10005;</button>' : '') +
        '</div>');
      var rm = row.querySelector('.rm');
      if (rm) rm.addEventListener('click', function () { removeStop(i); });
      stopsBox.appendChild(row);
    });
    var modesBox = railCard.querySelector('.v4-route-modes');
    MODES.forEach(function (m) {
      var b = el('<button class="' + (m.key === st.mode ? 'on' : '') + '">' + m.label + '</button>');
      b.addEventListener('click', function () { S.route.mode = m.key; showRouteCard(); });
      modesBox.appendChild(b);
    });
    railCard.querySelector('.v4-rc-x').addEventListener('click', clearRoute);
    railCard.querySelector('.go').addEventListener('click', function () {
      toast('Bat dau chi duong / navigation (mo phong)', 'success');
    });
    var opt = railCard.querySelector('.opt');
    if (opt) opt.addEventListener('click', function () {
      // greedy nearest-neighbour keeping A fixed and B last
      var s = S.route.stops, a = s[0], b = s[s.length - 1], mid = s.slice(1, -1), out = [a], cur = a;
      while (mid.length) {
        var bi = 0, bd = Infinity;
        mid.forEach(function (m, i) { var d = haversineKm(cur.lat, cur.lng, m.lat, m.lng); if (d < bd) { bd = d; bi = i; } });
        cur = mid.splice(bi, 1)[0]; out.push(cur);
      }
      out.push(b); S.route.stops = out; drawV4Route(out); showRouteCard();
      toast('Da toi uu thu tu diem dung / optimized', 'success');
    });
    guard(railCard);
    var old = $('v4RouteCard'); if (old) old.remove();
    els.v4Rail.insertBefore(railCard, els.v4Rail.firstChild);
    drawV4Route(st.stops);
  }
  function routeToPoi(poi) {
    var from = userAnchor(poi);
    S.route = { stops: [from, poi], mode: 'drive' };
    closeCallout();
    closeSpotlight();   // routing is a new context — clear the multi-result spotlight
    if (S.traffic) drawTraffic();
    map.fitBounds(new L.LatLngBounds([[from.lat, from.lng], [poi.lat, poi.lng]]),
      { padding: [80, 80], maxZoom: 15 });
    showRouteCard();
  }
  function addStop(poi) {
    if (!S.route) { routeToPoi(poi); return; }
    // insert before the final destination
    S.route.stops.splice(S.route.stops.length - 1, 0, poi);
    closeCallout();
    showRouteCard();
  }
  function removeStop(i) {
    if (!S.route) return;
    S.route.stops.splice(i, 1);
    if (S.route.stops.length < 2) { clearRoute(); return; }
    showRouteCard();
  }
  function clearRoute() {
    S.route = null;
    v4RouteLayer.clearLayers();
    var c = $('v4RouteCard'); if (c) c.remove();
  }
  function userAnchor(dest) {
    // A route needs an origin. In priority order:
    //  1) the real device GPS the shell holds (only after the user grants it);
    //  2) a data-derived city anchor = centroid of the real POIs currently on the
    //     map, EXCLUDING the destination — you're browsing that district, so its
    //     centre is a plausible "you are near here" a few km from any one pin;
    //  3) a small deterministic offset from the destination as a last resort.
    // Never map.getCenter(): after we fly to a pin, that IS the pin (0.0 km).
    var name = 'Vi tri cua ban (mo phong) / Your location (approx.)';
    if (H && H.userLoc) {
      var u = H.userLoc();
      if (u && typeof u.lat === 'number') {
        return { poi_id: '__you', name: 'Vi tri cua ban / You', lat: u.lat, lng: u.lng };
      }
    }
    var pts = [];
    Object.keys(S.surfaced).forEach(function (id) { pts.push(S.surfaced[id].poi); });
    Object.keys(S.saved).forEach(function (id) { pts.push(S.saved[id]); });
    if (dest) pts = pts.filter(function (p) { return p && p.poi_id !== dest.poi_id; });
    if (pts.length) {
      var la = 0, ln = 0;
      pts.forEach(function (p) { la += p.lat; ln += p.lng; });
      la /= pts.length; ln /= pts.length;
      if (!dest || haversineKm(la, ln, dest.lat, dest.lng) > 0.15) {
        return { poi_id: '__you', name: name, lat: la, lng: ln };
      }
    }
    // last resort: ~1.3 km south-west of the destination (deterministic, non-zero)
    if (dest) {
      return { poi_id: '__you', name: name,
        lat: dest.lat - 0.009, lng: dest.lng - 0.009 };
    }
    var c = map.getCenter();
    return { poi_id: '__you', name: name, lat: c.lat, lng: c.lng };
  }

  /* ── transient reply (§2.2) + PiP history (§2.3) ───────────────────────── */
  function pushHistory(role, text) {
    if (!text) return;
    S.msgs.push({ role: role, text: text });
    var b = el('<div class="v4-bub ' + role + '"></div>');
    b.textContent = text;
    els.v4PipBody.appendChild(b);
    els.v4PipBody.scrollTop = els.v4PipBody.scrollHeight;
  }
  function clearTransTimer() { if (S.transTimer) { clearTimeout(S.transTimer); S.transTimer = null; } }
  function showTransient(opts) {
    // opts: {steps:[{label,done}], text, chips:[{label,onClick}], fade:true}
    clearTransTimer();
    var t = els.v4Trans;
    t.classList.remove('fading');
    els.v4TransSteps.innerHTML = '';
    (opts.steps || []).forEach(function (st) {
      var row = el('<div class="v4-step' + (st.done ? ' done' : '') + '">' +
        '<span class="v4-step-dot"></span>' +
        '<span>' + esc(st.label) + '</span></div>');
      if (st.done) row.querySelector('.v4-step-dot').innerHTML = '&#10003;';
      els.v4TransSteps.appendChild(row);
    });
    els.v4TransText.innerHTML = opts.text ? esc(opts.text) : '';
    els.v4TransText.style.display = opts.text ? '' : 'none';
    els.v4TransChips.innerHTML = '';
    (opts.chips || []).forEach(function (ch) {
      var c = el('<button class="v4-chip">' + esc(ch.label) + '</button>');
      c.addEventListener('click', ch.onClick);
      els.v4TransChips.appendChild(c);
    });
    t.classList.add('on');
    if (opts.fade !== false) {
      // completion-guaranteed single deadline (never interval-counted)
      S.transTimer = setTimeout(fadeTransient, 9000);
    }
  }
  function fadeTransient() {
    clearTransTimer();
    els.v4Trans.classList.add('fading');
    S.transTimer = setTimeout(function () {
      els.v4Trans.classList.remove('on', 'fading');
    }, 500);
  }
  function hideTransientNow() {
    clearTransTimer();
    els.v4Trans.classList.remove('on', 'fading');
  }

  var IDLE_CHIPS = ['cafe gan day', 'nha thuoc quan 1', 'chi duong den cho Ben Thanh'];
  function showIdle() {
    var chips = IDLE_CHIPS.map(function (q) {
      return { label: q, onClick: function () { submit(q); } };
    });
    chips.push({ label: '👥 Tao nhom Group Drive', onClick: function () { submit('tao nhom'); } });
    showTransient({
      text: 'Hoi toi bat cu dieu gi ve dia diem / Ask me anything about places.',
      chips: chips, fade: false,
    });
  }

  /* ── intents + submit ──────────────────────────────────────────────────── */
  function setWorking(on) {
    S.working = on;
    els.v4Pill.classList.toggle('working', on);
  }
  function submit(text) {
    text = (text || '').trim();
    if (!text || S.working) return;
    els.v4Input.value = '';
    hideTransientNow();
    routeV4(text);   // trip-control > corridor > create-team > jarvis
  }

  function askJarvisV4(text) {
    pushHistory('user', text);
    setWorking(true);
    showTransient({ steps: [{ label: 'Scanning places…' }], fade: false });
    var c = map.getCenter();
    var payload = {
      message: text,
      chat_session_id: S.sessionId,
      interactive: true,
      viewport: { lat: c.lat, lng: c.lng, zoom: map.getZoom() },
      pins: Object.keys(S.surfaced).map(function (id, i) {
        return { n: i + 1, poi_id: id, name: S.surfaced[id].poi.name };
      }),
    };
    H.AtriaDash.json('jarvis_chat.py', [], { stdin: JSON.stringify(payload), timeout_ms: 110000 })
      .then(function (res) {
        setWorking(false);
        if (res.session_id) S.sessionId = res.session_id;
        if (res.error && !res.reply) {
          showTransient({ text: 'Jarvis khong phan hoi / unreachable: ' + res.error });
          pushHistory('ai', 'Jarvis unreachable: ' + res.error);
          return;
        }
        renderAgentReply(text, res);
      })
      .catch(function (e) {
        setWorking(false);
        showTransient({ text: 'Jarvis loi / error: ' + e });
        pushHistory('ai', 'Jarvis error: ' + e);
      });
  }

  // Turn a jarvis_chat response into map artifacts (§2.4/2.6/2.8) + a transient.
  function renderAgentReply(query, res) {
    var pins = [], route = null;
    (res.map_actions || []).forEach(function (a) {
      if (a.type === 'pins') pins = pins.concat(a.items || []);
      else if (a.type === 'route') route = a;
    });
    var reply = res.reply || '';
    pushHistory('ai', reply);
    if (S.speakNext) { S.speakNext = false; if (reply) speak(reply); }   // general-voice reply

    // surface pins (empty-map policy: only what the agent returned, plus saved)
    clearSurfaced(true);
    closeSpotlight(); closeCallout();

    if (pins.length > 1) {
      pins.forEach(function (p, i) { surfacePin(p, String(i + 1)); });
      openSpotlight(pins);
      renderCarousel(pins);
      map.fitBounds(new L.LatLngBounds(pins.map(function (p) { return [p.lat, p.lng]; })),
        { padding: [70, 70], maxZoom: 15 });
    } else if (pins.length === 1) {
      surfacePin(pins[0], '1');
      map.flyTo([pins[0].lat, pins[0].lng], Math.max(map.getZoom(), 15));
      openCallout(pins[0]);
    }

    if (route && route.from && route.to) {
      var to = { poi_id: 'dest', name: (pins[0] && pins[0].name) || 'Diem den / Destination',
                 lat: route.to.lat, lng: route.to.lng };
      var from = { poi_id: '__you', name: 'Vi tri cua ban / You', lat: route.from.lat, lng: route.from.lng };
      S.route = { stops: [from, to], mode: 'drive' };
      showRouteCard();
    }

    var chips = [];
    if (pins.length) chips.push({ label: '⊕ Save top pick', onClick: function () { toggleSave(pins[0]); toast('Da luu / saved', 'success'); } });
    showTransient({
      text: reply || (pins.length ? pins.length + ' ket qua tren ban do' : 'Xong.'),
      chips: chips,
      fade: true,
    });
  }

  /* ── design toggle (mirrors v3 setDesign/wire; owns v4 teardown) ───────── */
  function teardownV4Artifacts() {
    voiceStopSession();                        // end any live mic session
    if ($('v4Voice')) $('v4Voice').classList.remove('on');
    hideTransientNow();
    closeSpotlight();
    closeCallout();
    clearRoute();
    if (S.group) leaveGroup();
    clearPopouts();
    if (v4TrafficLayer) { map.removeLayer(v4TrafficLayer); v4TrafficLayer = null; }
    S.traffic = false; if ($('v4Traffic')) $('v4Traffic').classList.remove('on');
    if (S.proactiveTimer) { clearTimeout(S.proactiveTimer); S.proactiveTimer = null; }
    clearSurfaced(false);
    // clear anything v4 pushed into the SHELL's layers (belt-and-suspenders:
    // v4 doesn't persist via applyActionsLegacy, but a stray focus/anchor could
    // linger — the shell's clear contract wipes ai/route/anchor layers).
    try { H.applyActionsLegacy([{ type: 'clear', what: 'all' }]); } catch (x) {}
    els.v4Pip.classList.remove('on');
  }
  function setDesign(mode) {
    var isV4 = mode !== 'legacy';
    document.body.classList.toggle('design-v4', isV4);
    $('designToggle').textContent = isV4
      ? '↺ Giao dien cu / legacy' : '✦ Giao dien moi / v4';
    if (isV4) { map.invalidateSize(); showIdle(); scheduleProactive(); }
    else { teardownV4Artifacts(); }
  }
  function wire() {
    $('designToggle').addEventListener('click', function () {
      setDesign(document.body.classList.contains('design-v4') ? 'legacy' : 'v4');
    });
    els.v4Input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') submit(e.target.value);
    });
    // the suggestion bar is re-summonable: tap the orb or focus the empty pill
    // (it used to appear once and be unrecoverable once dismissed/overwritten).
    function reSummonIdle() {
      if (!S.working && !els.v4Input.value.trim()
          && !els.v4Trans.classList.contains('on')) showIdle();
    }
    $('v4Orb').addEventListener('click', reSummonIdle);
    els.v4Input.addEventListener('focus', reSummonIdle);
    $('v4Go').addEventListener('click', function () { submit(els.v4Input.value); });
    $('v4Mic').addEventListener('click', function () {
      if (S.tl) openVoicePicker();                       // team voice commands (Phase B)
      else openGeneralVoice();                            // general voice (Phase C)
    });
    $('v4Traffic').addEventListener('click', toggleTraffic);
    $('v4Hist').addEventListener('click', function () { els.v4Pip.classList.toggle('on'); });
    // team overlay controls
    $('v4SosResolve').addEventListener('click', resolveSos);
    $('v4CallEnd').addEventListener('click', endCall);
    $('v4CallMute').addEventListener('click', function () { this.textContent = this.textContent === '🔇' ? '🔈' : '🔇'; });
    $('v4CallLoc').addEventListener('click', function () { if (S.sosMember) locateMember(S.sosMember); });
    $('v4VoiceClose').addEventListener('click', function () {
      voiceStopSession(); $('v4Voice').classList.remove('on');
    });
    $('v4TeamStrip').addEventListener('click', function () { renderTeamCard(); $('v4TeamStrip').classList.remove('on'); });
    $('v4PipClose').addEventListener('click', function () { els.v4Pip.classList.remove('on'); });
    $('v4TransClose').addEventListener('click', hideTransientNow);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && document.body.classList.contains('design-v4')) {
        closeSpotlight(); closeCallout();
      }
    });
    // screen-space overlays track pan; hide during the CSS zoom animation and
    // re-punch on zoomend (the fixed layer can't follow the transform).
    map.on('move', scheduleReposition);
    map.on('zoomstart', function () {
      // member-pin CSS transitions fight Leaflet's zoom animation — suspend them
      document.body.classList.remove('v4-smooth');
      if (S.spot) els.v4Spot.style.opacity = '0';
      els.v4Callout.style.transition = 'none';
      els.v4Callout.style.opacity = '0';
    });
    map.on('zoomend', function () {
      if (S.playing) document.body.classList.add('v4-smooth');
      if (S.spot) els.v4Spot.style.opacity = '';
      els.v4Callout.style.transition = '';
      els.v4Callout.style.opacity = '';
      reposition();
    });
    // background-tab throttling would skew the sim clock — pause when hidden
    document.addEventListener('visibilitychange', function () { if (document.hidden) pause(); });
  }

  /* ══════════════════════════════════════════════════════════════════════
     Phase B — team mode + safety.  Reuses the Track-7 backend (group_drive.py
     create/timeline/voice/along) verbatim; only the UI is reimplemented for the
     map-first model.  Sim-clock logic + detection gating are ported unchanged
     (drift = double-fired / dropped safety alerts).  Team artifacts live in
     v4's own layers + rail cards, torn down on toggle like every v4 artifact.
     ══════════════════════════════════════════════════════════════════════ */
  var TICK_MS = 700;   // wall ms per sim minute at ×1

  function speak(text) {
    try {
      if (window.speechSynthesis && window.SpeechSynthesisUtterance) {
        var u = new SpeechSynthesisUtterance(text); u.lang = 'vi-VN';
        window.speechSynthesis.speak(u);
      }
    } catch (e) { /* sandbox may deny — silent degrade */ }
  }
  function selfId() { return S.group ? S.group.self_member_id : null; }
  function memberById(id) { return S.group && S.group.members.filter(function (m) { return m.member_id === id; })[0]; }
  function privacyHidden(m) {
    return S.viewAs === 'member' && m.privacy === 'leader_only' && m.member_id !== selfId();
  }
  function tickOf(id) {
    if (!S.tl) return null;
    var tick = S.tl.ticks[Math.min(S.t, S.tl.ticks.length - 1)];
    return tick.members.filter(function (x) { return x.member_id === id; })[0];
  }
  function pinState(id, tick) {
    if (S.sosMember === id) return 'sos';
    if (privacyHidden(memberById(id))) return 'stale';
    if (!tick || !tick.gps_ok) return 'stale';
    if (id === selfId() && S.selfWarnUntil && S.t < S.selfWarnUntil) return 'warn';
    if (tick.status !== 'on_route' || tick.eta_gap_min >= 5 || tick.gap_km >= 3) return 'warn';
    return '';
  }
  function memberIcon(m, state) {
    var cls = 'v4-member-pin ' + (state || '') + (m.member_id === selfId() ? ' self' : '');
    return new L.DivIcon({
      className: 'v4-pin-icon', iconSize: [30, 30], iconAnchor: [15, 15],
      html: '<div class="' + cls + '"><span class="ring"></span>'
        + '<div class="av" style="background:' + m.color + '">' + esc(m.initial) + '</div>'
        + '<div class="lbl"><span class="ld"></span>' + esc(m.name) + '</div></div>',
    });
  }
  function memberStatusLine(m, tick) {
    if (!tick) return { txt: 'san sang / ready', cls: '' };
    var st = tick.status, gap = tick.gap_km;
    if (S.sosMember === m.member_id) return { txt: 'KHAN CAP — ' + gap + ' km', cls: 'sos' };
    if (st === 'off_route') return { txt: 'chech tuyen · lech ' + tick.eta_gap_min + ' phut', cls: 'warn' };
    if (st === 'stopped') return { txt: 'dang dung · cach doan ' + gap + ' km', cls: 'warn' };
    if (st === 'needs_charging') return { txt: 'pin yeu · can sac', cls: 'warn' };
    if (tick.eta_gap_min >= 5 || gap >= 3) return { txt: 'tut lai ' + gap + ' km · cham ' + tick.eta_gap_min + ' phut', cls: 'warn' };
    return { txt: 'dang chay · cach doan ' + gap + ' km', cls: '' };
  }

  /* ── team DOM (strip + SOS banner + call/voice overlays) ───────────────── */
  function buildTeamDom() {
    var app = $('v4App');
    app.appendChild(guard(el(
      '<div id="v4TeamStrip"><div class="avs" id="v4StripAvs"></div>'
      + '<span class="lbl" id="v4StripLabel">&#9679; 0 live</span></div>')));
    app.appendChild(guard(el(
      '<div id="v4Sos"><span class="fdot"></span><span class="txt" id="v4SosText"></span>'
      + '<button class="call" id="v4SosCall">&#9990; Call</button>'
      + '<button class="resolve" id="v4SosResolve">Resolve</button></div>')));
    app.appendChild(guard(el(
      '<div id="v4Call" class="v4-overlay"><div class="v4-call-card">'
      + '<div class="v4-call-avwrap"><div class="v4-call-ring"></div>'
      +   '<div class="v4-call-av" id="v4CallAv"></div></div>'
      + '<div class="v4-call-name" id="v4CallName"></div>'
      + '<div class="v4-call-status" id="v4CallStatus">dang goi&hellip;</div>'
      + '<div class="v4-wave" id="v4CallWave"><i></i><i></i><i></i><i></i><i></i></div>'
      + '<div class="v4-call-btns">'
      +   '<button class="v4-call-btn" id="v4CallMute" title="Mute">&#128263;</button>'
      +   '<button class="v4-call-btn end" id="v4CallEnd" title="End">&#9990;</button>'
      +   '<button class="v4-call-btn" id="v4CallLoc" title="Locate">&#8982;</button>'
      + '</div></div></div>')));
    app.appendChild(guard(el(
      '<div id="v4Voice" class="v4-overlay"><div class="v4-call-card">'
      + '<div class="v4-voice-orb">&#10022;</div>'
      + '<div class="v4-voice-state" id="v4VoiceState">DANG NGHE&hellip;</div>'
      + '<div class="v4-wave ai on"><i></i><i></i><i></i><i></i><i></i></div>'
      + '<div class="v4-voice-chips" id="v4VoiceChips"></div>'
      + '<button class="v4-call-btn" id="v4VoiceClose" title="Close">&#10005;</button>'
      + '</div></div>')));
  }

  /* ── team rail card + strip + chat ─────────────────────────────────────── */
  function railCardShell(id, title, extra) {
    var c = el('<div class="v4-rail-card" id="' + id + '"></div>');
    c.appendChild(el('<div class="v4-rc-head"><span class="v4-rc-title">' + esc(title) + '</span>'
      + (extra || '') + '<button class="v4-rc-x" title="Close">&#10005;</button></div>'));
    return guard(c);
  }
  function railUpsert(card) {
    var old = $(card.id);
    if (old) old.replaceWith(card);   // in place — keep rail order stable across re-renders
    else els.v4Rail.appendChild(card);
  }
  function memberRowV4(m, tick) {
    var line = memberStatusLine(m, tick);
    var hidden = privacyHidden(m);
    var self = m.member_id === selfId();
    var row = el('<div class="v4-mrow' + (S.alertMembers[m.member_id] ? ' alert' : '') + '"></div>');
    row.appendChild(el('<div class="v4-av" style="background:' + m.color
      + (hidden ? ';opacity:.4' : '') + '">' + esc(m.initial) + '</div>'));
    var mid = el('<div class="mid"></div>');
    mid.appendChild(el('<div class="v4-mname">' + esc(m.name)
      + (self ? ' <span style="color:var(--muted);font-weight:600">&middot; you</span>'
             : ' <span class="v4-mlive">&#9679; LIVE</span>')
      + (m.role === 'leader' ? ' <span style="font-size:9px;color:var(--accent-ink)">&#128081;</span>' : '') + '</div>'));
    mid.appendChild(el('<div class="v4-mstatus ' + line.cls + '">'
      + (hidden ? 'chi chia se voi truong doan &#128274;' : esc(m.vehicle_label) + ' &middot; ' + esc(line.txt)) + '</div>'));
    row.appendChild(mid);
    if (!self) {
      var call = el('<button class="v4-mbtn" title="Call">&#9990;</button>');
      call.addEventListener('click', function () { startCall(m); });
      row.appendChild(call);
    }
    var loc = el('<button class="v4-mbtn" title="Locate">&#8982;</button>');
    loc.addEventListener('click', function () { locateMember(m.member_id); });
    row.appendChild(loc);
    if (!self) {
      var sos = el('<button class="v4-mbtn sosbtn">SOS</button>');
      sos.addEventListener('click', function () { triggerSos(m); });
      row.appendChild(sos);
    }
    return row;
  }
  function renderTeamCard() {
    if (!S.group) return;
    var g = S.group;
    var card = railCardShell('v4TeamCard', g.trip_name,
      '<button class="v4-team-invite" id="v4Invite" title="Copy invite">' + esc(g.join_code) + ' &#9099;</button>');
    if (S.dockView === 'chat') {
      var chat = el('<div class="v4-tchat" id="v4TChat"></div>');
      (S.teamChat || []).forEach(function (msg) { chat.appendChild(teamMsgEl(msg)); });
      card.appendChild(chat);
      var inp = el('<div class="v4-tchat-input"><input id="v4TInput" placeholder="Message the team&hellip;" />'
        + '<button id="v4TSend">&#8594;</button></div>');
      card.appendChild(inp);
    } else {
      g.members.forEach(function (m) { card.appendChild(memberRowV4(m, tickOf(m.member_id))); });
    }
    var unread = S.unread ? ' <span class="unread">(' + S.unread + ')</span>' : '';
    var foot = el('<div class="v4-team-foot">'
      + '<button id="v4FitAll">&#8982; Fit all</button>'
      + '<button id="v4ChatBtn">&#128172; ' + (S.dockView === 'chat' ? 'Members' : 'Chat' + unread) + '</button></div>');
    card.appendChild(foot);
    railUpsert(card);
    // wire
    card.querySelector('.v4-rc-x').addEventListener('click', function () {
      $('v4TeamCard').remove(); renderTeamStrip(true);
    });
    $('v4Invite').addEventListener('click', function () {
      toast('Da sao chep ma moi ' + g.join_code + ' / invite copied', 'success');
    });
    $('v4FitAll').addEventListener('click', fitTeam);
    $('v4ChatBtn').addEventListener('click', function () {
      S.dockView = S.dockView === 'chat' ? 'members' : 'chat';
      if (S.dockView === 'chat') { S.unread = 0; }
      renderTeamCard();
    });
    if (S.dockView === 'chat') {
      var ch = $('v4TChat'); if (ch) ch.scrollTop = ch.scrollHeight;
      $('v4TSend').addEventListener('click', function () { sendTeamMsg($('v4TInput').value); });
      $('v4TInput').addEventListener('keydown', function (e) { if (e.key === 'Enter') sendTeamMsg(e.target.value); });
    }
  }
  function renderTeamStrip(on) {
    var strip = $('v4TeamStrip'), avs = $('v4StripAvs');
    if (!S.group) { strip.classList.remove('on'); return; }
    avs.innerHTML = '';
    S.group.members.forEach(function (m) {
      avs.appendChild(el('<div class="v4-av" style="background:' + m.color + '">' + esc(m.initial) + '</div>'));
    });
    $('v4StripLabel').innerHTML = '&#9679; ' + S.group.members.length + ' live';
    strip.classList.toggle('on', !!on);
  }
  function teamMsgEl(msg) {
    if (msg.who === 'sys') return el('<div class="v4-tmsg sys">' + esc(msg.text) + '</div>');
    var me = msg.who === 'me', m = me ? null : memberById(msg.who);
    var d = el('<div class="v4-tmsg' + (me ? ' me' : '') + '"></div>');
    if (m) d.appendChild(el('<div class="who" style="color:' + m.color + '">' + esc(m.name) + '</div>'));
    d.appendChild(el('<div class="bub">' + esc(msg.text) + '</div>'));
    return d;
  }
  function pushTeamMsg(who, text) {
    S.teamChat = S.teamChat || [];
    S.teamChat.push({ who: who, text: text });
    if (S.dockView === 'chat' && $('v4TeamCard')) renderTeamCard();
    else { S.unread++; if ($('v4TeamCard')) renderTeamCard(); }
  }
  function sendTeamMsg(v) {
    v = (v || '').trim(); if (!v) return;
    pushTeamMsg('me', v);
    var leader = S.group.members.filter(function (m) { return m.role === 'leader'; })[0];
    setTimeout(function () { pushTeamMsg(leader.member_id, 'Ok, da nhan! / got it'); }, 900);
    renderTeamCard();
  }

  /* ── team map layers ───────────────────────────────────────────────────── */
  function drawTeam() {
    var tl = S.tl;
    [v4TeamLayer, v4TeamRouteLayer, v4TeamPoiLayer].forEach(function (l) { if (l) map.removeLayer(l); });
    v4TeamLayer = new L.LayerGroup().addTo(map);
    v4TeamRouteLayer = new L.LayerGroup().addTo(map);
    v4TeamPoiLayer = new L.LayerGroup().addTo(map);
    S.markers = {};
    v4TeamRouteLayer.addLayer(new L.Polyline(tl.route.polyline,
      { color: '#8b6fd8', weight: 4, opacity: .55, dashArray: '8 7' }));
    tl.route.waypoints.forEach(function (w) {
      if (w.type === 'Start' || w.type === 'Destination') {
        v4TeamRouteLayer.addLayer(new L.Marker([w.lat, w.lng], {
          icon: new L.DivIcon({ className: 'v4-pin-icon', iconSize: [26, 26], iconAnchor: [13, 24],
            html: '<div class="v4-poi-pin" style="background:' + (w.type === 'Start' ? '#5d8bc4' : 'var(--accent)')
              + '"><span>' + (w.type === 'Start' ? '🚩' : '🏁') + '</span></div>' }),
          title: w.name }));
      }
    });
    S.group.members.forEach(function (m) {
      var tk = tickOf(m.member_id); if (!tk) return;
      var mk = new L.Marker([tk.lat, tk.lng],
        { icon: memberIcon(m, pinState(m.member_id, tk)), title: m.name, zIndexOffset: 900 });
      v4TeamLayer.addLayer(mk); S.markers[m.member_id] = mk;
    });
    fitTeam();
  }
  function fitTeam() {
    var pts = [];
    Object.keys(S.markers).forEach(function (id) { var ll = S.markers[id].getLatLng(); pts.push([ll.lat, ll.lng]); });
    if (pts.length) map.fitBounds(new L.LatLngBounds(pts), { padding: [80, 80], maxZoom: 12 });
  }
  function locateMember(id) {
    var mk = S.markers[id];
    if (mk) { var ll = mk.getLatLng(); map.flyTo([ll.lat, ll.lng], Math.max(map.getZoom(), 12)); }
  }
  function showRegroupPoi(rec, fromId) {
    v4TeamPoiLayer.clearLayers();
    v4TeamPoiLayer.addLayer(new L.Marker([rec.lat, rec.lng], {
      icon: new L.DivIcon({ className: 'v4-pin-icon', iconSize: [26, 26], iconAnchor: [13, 24],
        html: '<div class="v4-poi-pin"><span>🅿</span></div>' }),
      title: rec.poi_name, zIndexOffset: 950 }));
    var pts = [[rec.lat, rec.lng]], mk = fromId && S.markers[fromId];
    if (mk) {
      var ll = mk.getLatLng();
      v4TeamPoiLayer.addLayer(new L.Polyline([[ll.lat, ll.lng], [rec.lat, rec.lng]],
        { color: '#4f9464', weight: 3, opacity: .8, dashArray: '4 6' }));
      pts.push([ll.lat, ll.lng]);
    }
    map.fitBounds(new L.LatLngBounds(pts), { padding: [80, 80], maxZoom: 13 });
  }

  /* ── sim clock ─────────────────────────────────────────────────────────── */
  function refreshPins() {
    S.group.members.forEach(function (m) {
      var mk = S.markers[m.member_id], tk = tickOf(m.member_id);
      if (!mk || !tk) return;
      if (!privacyHidden(m) || S.viewAs === 'leader') mk.setLatLng([tk.lat, tk.lng]);
      mk.setIcon(memberIcon(m, pinState(m.member_id, tk)));
    });
  }
  function renderSimCard() {
    var card = el('<div class="v4-rail-card" id="v4SimCard"></div>');
    var hh = String(Math.floor(S.t / 60)).padStart(2, '0'), mm = String(S.t % 60).padStart(2, '0');
    card.innerHTML =
      '<div class="v4-sim"><span class="tag">SIM</span>'
      + '<button class="v4-sim-btn" id="v4Play" title="Play/pause">' + (S.playing ? '&#10074;&#10074;' : '&#9654;') + '</button>'
      + '<button class="v4-sim-btn dark" id="v4EndTrip" title="End trip">&#9197;</button>'
      + '<button class="v4-speed" id="v4Speed">&times;' + S.speed + '</button>'
      + '<span class="v4-clock" id="v4Clock">' + hh + ':' + mm + '<small> / ' + S.tl.trip.duration_min + 'p</small></span>'
      + '<input type="range" class="v4-scrub" id="v4Scrub" min="0" max="' + S.tl.trip.duration_min + '" value="' + S.t + '" /></div>';
    guard(card);
    railUpsert(card);
    $('v4Play').addEventListener('click', function () { if (S.playing) pause(); else play(); });
    $('v4EndTrip').addEventListener('click', endTrip);
    $('v4Speed').addEventListener('click', function () {
      S.speed = S.speed >= 4 ? 1 : S.speed * 2; this.innerHTML = '&times;' + S.speed;
      if (S.playing) { clearInterval(S.timer); S.timer = setInterval(tickForward, TICK_MS / S.speed); }
    });
    $('v4Scrub').addEventListener('input', function () { pause(); setTick(parseInt(this.value, 10), true); });
  }
  function updateSimClock() {
    var cl = $('v4Clock'), sc = $('v4Scrub'), pl = $('v4Play');
    if (!cl) return;
    var hh = String(Math.floor(S.t / 60)).padStart(2, '0'), mm = String(S.t % 60).padStart(2, '0');
    cl.innerHTML = hh + ':' + mm + '<small> / ' + S.tl.trip.duration_min + 'p</small>';
    if (sc) sc.value = S.t;
    if (pl) pl.innerHTML = S.playing ? '&#10074;&#10074;' : '&#9654;';
  }
  function setTick(t, silent) {
    S.t = Math.max(0, Math.min(t, S.tl.trip.duration_min));
    refreshPins();
    if ($('v4TeamCard') && S.dockView === 'members') renderTeamCard();
    updateSimClock();
    if (S.muted && S.unmuteAt != null && S.t >= S.unmuteAt) {
      S.muted = false; S.unmuteAt = null;
      pushTeamMsg('sys', '🔔 Da bat lai thong bao day du');
    }
    S.tl.detections.forEach(function (d) {
      if (silent) { if (d.t <= S.t) S.delivered[d.det_id] = true; }
      else if (d.t === S.t) deliverDetection(d);
    });
    if (S.t >= S.tl.trip.duration_min) endSim();
  }
  function tickForward() { setTick(S.t + 1); }
  function play() {
    if (S.playing || !S.tl) return;
    if (S.t >= S.tl.trip.duration_min) { setTick(0, true); S.delivered = {}; }
    S.playing = true;
    document.body.classList.add('v4-smooth');
    S.timer = setInterval(tickForward, TICK_MS / S.speed);
    updateSimClock();
  }
  function pause() {
    S.playing = false;
    document.body.classList.remove('v4-smooth');
    clearInterval(S.timer);
    updateSimClock();
  }
  function endTrip() {
    if (!S.tl || S.summaryShown) return;
    pause();
    pushTeamMsg('sys', '🏁 Chuyen di ket thuc — cam on ca doan!');
    setTick(S.tl.trip.duration_min, true);
  }
  function endSim() {
    pause();
    if (S.summaryShown) return;
    S.summaryShown = true;
    var sum = S.tl.summary;
    pushHistory('ai', sum.headline_vi);
    showTransient({
      text: 'Chuyen di mo phong ket thuc.\n' + sum.headline_vi,
      chips: [
        { label: '↻ Replay', onClick: function () { S.summaryShown = false; S.delivered = {}; setTick(0, true); play(); } },
        { label: '✕ Leave group', onClick: leaveGroup },
      ], fade: false,
    });
    speak('Chuyen di mo phong da ket thuc.');
    H.AtriaDash.json('group_drive.py', ['polish'],
      { stdin: JSON.stringify({ texts: [sum.headline_vi], lang: 'vi' }), timeout_ms: 50000 })
      .then(function (res) {
        if (res && res.polished && res.texts && res.texts[0] && $('v4Trans').classList.contains('on')) {
          els.v4TransText.textContent = 'Chuyen di mo phong ket thuc.\n' + res.texts[0] + '  (✦ AI)';
        }
      }).catch(function () { /* templates stand */ });
  }
  function leaveGroup() {
    pause();
    [v4TeamLayer, v4TeamRouteLayer, v4TeamPoiLayer].forEach(function (l) { if (l) map.removeLayer(l); });
    v4TeamLayer = v4TeamRouteLayer = v4TeamPoiLayer = null;
    S.markers = {}; S.tl = null; S.group = null; S.teamChat = []; S.sosMember = null;
    S.muted = false; S.unmuteAt = null; S.summaryShown = false; S.delivered = {};
    S.t = 0; S.unread = 0; S.alertMembers = {}; S.dockView = 'members';
    if (S.traffic && v4TrafficLayer) { map.removeLayer(v4TrafficLayer); v4TrafficLayer = null; S.traffic = false; if ($('v4Traffic')) $('v4Traffic').classList.remove('on'); }
    document.body.classList.remove('v4-smooth');
    ['v4TeamCard', 'v4SimCard'].forEach(function (id) { var e = $(id); if (e) e.remove(); });
    $('v4TeamStrip').classList.remove('on');
    $('v4Sos').classList.remove('on');
    $('v4Call').classList.remove('on');
    $('v4Voice').classList.remove('on');
  }

  /* ── safety: alerts / SOS / calls ──────────────────────────────────────── */
  var CANNED_REPLY = {
    wrong_turn: 'Xin loi ca doan, toi re nham — dang quay lai tuyen!',
    falling_behind: 'Toi bi ket xe, moi nguoi cu giu toc do nhe.',
    group_split: 'Toi hoi tut lai, se gap moi nguoi o diem tap ket.',
    unexpected_stop: 'Toi phai dung khan — se nhan lai ngay.',
    gps_loss: '(mat tin hieu...)',
    low_battery: 'Pin xe toi yeu, can ghe tram sac gan nhat.',
    rest_request: 'Cho toi nghi 10 phut o diem dung toi nhe?',
    delay_building: 'Duong dong qua, toi cham mat vai phut.',
  };
  function deliverDetection(det) {
    if (S.delivered[det.det_id]) return;
    S.delivered[det.det_id] = true;
    var m = memberById(det.member_id);
    // mark the member row amber + pulse the pin
    S.alertMembers[det.member_id] = true;
    if ($('v4TeamCard') && S.dockView === 'members') renderTeamCard();
    pulseMemberPin(det.member_id, true);
    // build transient chips from the detection's action chips
    var chips = (det.chips || []).map(function (c) {
      return { label: c.label, onClick: function () {
        if (c.act === 'call' && m) startCall(m);
        if (c.act === 'locate') locateMember(c.member_id);
        if (c.act === 'route_poi' && det.recommend) showRegroupPoi(det.recommend, det.member_id);
      } };
    });
    chips.push({ label: 'He is fine', onClick: function () { clearAlert(det.member_id); } });
    var head = (m ? m.name + ' · ' : '') + det.severity.toUpperCase() + ' · P' + det.priority;
    pushHistory('ai', head + ' — ' + det.message_vi);
    showTransient({ steps: [{ label: head, done: true }], text: det.message_vi, chips: chips, fade: det.priority < 70 });
    // priority policy: ONE modal surface max
    if (det.priority >= 70) { toast('⚠ ' + det.message_vi, 'error'); speak(det.message_vi); }
    else if (S.muted) { /* muted: transient + history only */ }
    else if (det.priority >= 40) { toast(det.message_vi, 'info'); }
    if (m && CANNED_REPLY[det.type]) pushTeamMsg(det.member_id, CANNED_REPLY[det.type]);
  }
  function pulseMemberPin(id, on) {
    var mk = S.markers[id];
    if (!mk || !mk._icon) return;
    var p = mk._icon.querySelector('.v4-member-pin');
    if (p && on) p.classList.add('warn');
  }
  function clearAlert(id) {
    delete S.alertMembers[id];
    if ($('v4TeamCard') && S.dockView === 'members') renderTeamCard();
    refreshPins();
    hideTransientNow();
  }
  function triggerSos(m) {
    S.sosMember = m.member_id;
    $('v4SosText').textContent = 'KHAN CAP — vi tri cua ' + m.name + ' da chia se cho ca doan';
    $('v4Sos').classList.add('on');
    refreshPins();
    if ($('v4TeamCard')) renderTeamCard();
    pushTeamMsg('sys', '🚨 SOS: ' + m.name + ' can ho tro');
    speak('Khan cap. ' + m.name + ' can ho tro.');
    $('v4SosCall').onclick = function () { startCall(m); };
    locateMember(m.member_id);
  }
  function resolveSos() {
    if (!S.sosMember) return;
    var m = memberById(S.sosMember);
    S.sosMember = null;
    $('v4Sos').classList.remove('on');
    refreshPins();
    if ($('v4TeamCard')) renderTeamCard();
    pushTeamMsg('sys', '✅ SOS cua ' + m.name + ' da xu ly');
  }
  function startCall(m) {
    $('v4CallAv').style.background = m.color;
    $('v4CallAv').textContent = m.initial;
    $('v4CallName').textContent = m.name + ' · ' + m.vehicle_label;
    var st = $('v4CallStatus'); st.textContent = 'dang goi…'; st.classList.remove('live');
    $('v4CallWave').classList.remove('on');
    $('v4Call').classList.add('on');
    S.callSec = 0; clearInterval(S.callTimer); clearTimeout(S.callTimer);
    S.callTimer = setTimeout(function () {
      st.classList.add('live'); $('v4CallWave').classList.add('on');
      S.callTimer = setInterval(function () {
        S.callSec++;
        st.textContent = 'da ket noi · ' + Math.floor(S.callSec / 60) + ':'
          + String(S.callSec % 60).padStart(2, '0') + ' (mo phong)';
      }, 1000);
    }, 1400);
  }
  function endCall() { clearInterval(S.callTimer); clearTimeout(S.callTimer); $('v4Call').classList.remove('on'); }

  /* ── voice (simulated) ─────────────────────────────────────────────────── */
  function openVoicePicker() {
    if (!S.tl) { toast('Tao nhom truoc de dung lenh thoai / create a team first', 'info'); return; }
    $('v4VoiceState').textContent = 'DANG NGHE…';
    var box = $('v4VoiceChips'); box.innerHTML = '';
    S.tl.voice_commands.forEach(function (vc) {
      var b = el('<button class="v4-chip">🎙 ' + esc(vc.text_vi) + '</button>');
      b.addEventListener('click', function () { runVoice(vc.text_vi); });
      box.appendChild(b);
    });
    $('v4Voice').classList.add('on');
  }
  function runVoice(text) {
    $('v4VoiceState').textContent = 'DANG XU LY…';
    H.AtriaDash.json('group_drive.py', ['voice', '--text', text, '--trip', S.group.trip_id])
      .then(function (res) {
        $('v4VoiceState').textContent = 'DANG TRA LOI…';
        pushHistory('user', '🎙 ' + text);
        pushHistory('ai', res.reply_vi);
        showTransient({ text: res.reply_vi, fade: true });
        (res.map_actions || []).forEach(function (a) {
          if (a.type === 'route_poi') showRegroupPoi({ poi_name: a.name, lat: a.lat, lng: a.lng, poi_id: a.poi_id, safe_stop_score: 1 }, selfId());
        });
        applyVoiceAction(res.structured_action, text);
        speak(res.reply_vi);
        setTimeout(function () { $('v4Voice').classList.remove('on'); }, 900);
      })
      .catch(function (e) { $('v4Voice').classList.remove('on'); toast('Loi lenh thoai: ' + e, 'error'); });
  }
  function applyVoiceAction(act, spokenText) {
    if (!act || !S.tl) return;
    var self = memberById(selfId());
    var leader = S.group.members.filter(function (m) { return m.role === 'leader'; })[0];
    switch (act.action) {
      case 'notify_group':
        pushTeamMsg('me', spokenText);
        setTimeout(function () { pushTeamMsg(leader.member_id, 'Ok, ca nhom se cho / got it 👍'); }, 900);
        toast('Da gui vao chat doan — mo 💬 de xem', 'success');
        break;
      case 'share_eta': {
        var tk = tickOf(selfId()); var eta = tk ? tk.eta_gap_min : 0;
        pushTeamMsg('me', 'ETA cua toi: ' + (eta >= 1 ? 'cham ' + Math.round(eta) + ' phut' : 'dung ke hoach') + ' (phut ' + S.t + ')');
        break;
      }
      case 'request_rest_stop':
        pushTeamMsg('me', spokenText);
        setTimeout(function () { pushTeamMsg(leader.member_id, 'Ok, nghi o diem dung an toan ke tiep nhe'); }, 900);
        break;
      case 'report_wrong_turn':
        pushTeamMsg('me', spokenText); S.selfWarnUntil = S.t + 3; refreshPins();
        break;
      case 'emergency_check': triggerSos(self); break;
      case 'continue_without_member':
        pushTeamMsg('sys', '➡ ' + self.name + ' tach doan tam thoi — nhom tiep tuc'); break;
      case 'mute_noncritical': {
        S.muted = true;
        var wp = (S.tl.route.waypoints || []).filter(function (w) { return /exit|junction/i.test(w.type) && w.planned_arrival_min > S.t; })[0];
        S.unmuteAt = wp ? wp.planned_arrival_min : S.tl.trip.duration_min;
        pushTeamMsg('sys', '🔕 Thong bao khong khan cap tat den ' + (wp ? wp.name : 'cuoi chuyen'));
        break;
      }
      default: break;
    }
  }

  /* ── trip-corridor search (along) → spotlight ──────────────────────────── */
  function alongSearch(text) {
    if (S.teamBusy) return;
    S.teamBusy = true;
    pushHistory('user', text);
    setWorking(true);
    showTransient({ steps: [{ label: 'Scanning along the route…' }], fade: false });
    H.AtriaDash.json('group_drive.py', ['along', '--trip', S.group.trip_id, '--query', text])
      .then(function (res) {
        setWorking(false);
        if (!res.ok || !res.results) { showTransient({ text: 'Khong tim duoc doc tuyen: ' + (res.error || 'loi') }); return; }
        clearSurfaced(true); closeSpotlight(); closeCallout();
        var pins = res.results.map(function (r, i) {
          return { poi_id: r.poi_id || ('along' + i), name: r.name, lat: r.lat, lng: r.lng,
            rating: r.rating, detail: (r.detail || r.category || '') + ' · km ' + r.route_km,
            dist_label: r.detour_km ? 'lech ' + r.detour_km + ' km' : null };
        });
        pins.forEach(function (p, i) { surfacePin(p, String(i + 1)); });
        if (pins.length > 1) {
          openSpotlight(pins); renderCarousel(pins);
          map.fitBounds(new L.LatLngBounds(pins.map(function (p) { return [p.lat, p.lng]; })), { padding: [80, 80], maxZoom: 14 });
        } else if (pins.length === 1) { openCallout(pins[0]); map.flyTo([pins[0].lat, pins[0].lng], 14); }
        pushHistory('ai', res.reply_vi);
        showTransient({ text: res.reply_vi, fade: true });
      })
      .catch(function (e) { setWorking(false); showTransient({ text: 'Loi tim doc tuyen: ' + e }); })
      .then(function () { S.teamBusy = false; });
  }

  /* ── create-team flow ──────────────────────────────────────────────────── */
  function pickScenario() {
    setWorking(true);
    showTransient({ steps: [{ label: 'Loading Track-7 scenarios…' }], fade: false });
    H.AtriaDash.json('group_drive.py', ['users']).then(function (res) {
      setWorking(false);
      var chips = res.scenarios.map(function (sc) {
        return { label: sc.trip_name + ' (' + sc.vehicle_count + ')', onClick: function () { createGroup(sc.trip_id); } };
      });
      showTransient({ text: 'Chon mot kich ban Group Drive / choose a scenario:', chips: chips, fade: false });
    }).catch(function (e) { setWorking(false); showTransient({ text: 'Khong tai duoc: ' + e }); });
  }
  function createGroup(tripId) {
    var seed = Math.floor(Math.random() * 900) + 1;
    setWorking(true);
    showTransient({ steps: [{ label: 'Assembling team…' }], fade: false });
    H.AtriaDash.json('group_drive.py', ['timeline', '--trip', tripId, '--seed', String(seed)])
      .then(function (tl) {
        setWorking(false);
        S.tl = tl; S.group = tl.group; S.t = 0; S.delivered = {}; S.summaryShown = false;
        S.alertMembers = {}; S.dockView = 'members'; S.unread = 0;
        S.teamChat = [{ who: 'sys', text: 'Nhom ' + tl.group.join_code + ' da tao — mo phong' }];
        var self = memberById(selfId());
        drawTeam();
        renderTeamCard();
        renderSimCard();
        renderTeamStrip(false);
        setTick(0, true);
        pushHistory('ai', 'Nhom da san sang! Ban la ' + self.name + '.');
        showTransient({
          text: 'Nhom ' + tl.group.trip_name + ' san sang — chon ngau nhien ' + tl.group.members.length
            + ' nguoi. Ban la ' + self.name + ' (' + self.vehicle_label + ').',
          chips: [{ label: '▶ Start drive', onClick: play }], fade: false,
        });
        speak('Nhom ' + tl.group.trip_name + ' da san sang.');
      })
      .catch(function (e) { setWorking(false); showTransient({ text: 'Khong tao duoc nhom: ' + e }); });
  }

  /* ── intent routing (trip-control > corridor > create-team > jarvis) ────── */
  var CTRL_END = /(ket thuc|end trip|dung chuyen|stop trip)/;
  var CTRL_PAUSE = /(tam dung|\bpause\b)/;
  var CTRL_RESUME = /(tiep tuc|\bresume\b|\bcontinue\b)/;
  var ROUTE_WORDS = /(tren duong|tren tuyen|tren doan|doc duong|doc tuyen|team trip|trip nay|chuyen di|chuyen nay|on the (way|route|trip)|along the route)/;
  var CREATE_TEAM = /(tao nhom|tao doan|tao chuyen|chuyen di nhom|group drive|create (a )?(team|group|trip)|start a drive)/;
  // group-drive situational Q&A -> the AI Trip Coordinator (backend group_drive.py
  // coordinate). Covers the challenge's Public-Evaluation scenarios: member/vehicle
  // refs, deviation/behind/stop/gps/battery, regroup, privacy, summary, prioritise,
  // predictive risk. Place-search phrases don't match, so they still go to jarvis.
  var COORD_WORDS = new RegExp([
    're sai', 're nham', 'lac duong', 'di nham', 'chech tuyen',
    'tut lai', 'tut doan', 'cham hon', 'cham \\d', 'delay',
    'dung bat thuong', 'unexpected stop', 'mat tin hieu', 'khong co gps', '\\bgps\\b',
    'tap ket', 'regroup', 'diem dung an toan', 'safe stop',
    'pin yeu', 'diem sac', 'can sac', 'low battery',
    'yeu cau nghi', 'nghi \\d', 'need a break',
    'rieng tu', 'privacy', 'chi chia se',
    'tom tat', '\\bsummary\\b',
    'cung luc', 'tin nhan xa hoi', 'social message',
    'doi den khi', 'nen doi', 'truoc khi tach', 'wait until',
    'ai nen lam gi', 'can canh bao', 'khu pho co',
    '\\bcar [0-9a-d]\\b', '\\bbike \\d', '\\bvan \\d', '\\bev \\d', '\\bxe [0-9a-z]\\b',
  ].join('|'), 'i');
  function fold(s) {
    return String(s || '').toLowerCase().replace(/đ/g, 'd')
      .normalize('NFD').replace(/[̀-ͯ]/g, '');
  }
  function routeV4(text) {
    var f = fold(text);
    if (isVideoIntent(text)) { resolveVideo(text); return; }   // paste a link / video caption
    if (S.tl) {
      if (CTRL_END.test(f)) { pushHistory('user', text); showTransient({ text: 'Ok, ket thuc chuyen di.', fade: true }); endTrip(); return; }
      if (CTRL_PAUSE.test(f)) { pushHistory('user', text); pause(); showTransient({ text: 'Da tam dung — go "tiep tuc" de chay tiep.', fade: true }); return; }
      if (CTRL_RESUME.test(f) && f.indexOf('khong can') < 0 && f.indexOf('without') < 0 && !S.summaryShown) {
        pushHistory('user', text); play(); showTransient({ text: 'Tiep tuc mo phong!', fade: true }); return;
      }
      if (ROUTE_WORDS.test(f)) { alongSearch(text); return; }
    }
    if (CREATE_TEAM.test(f)) { pushHistory('user', text); pickScenario(); return; }
    if (S.group || COORD_WORDS.test(f)) { askCoordinator(text); return; }
    askJarvisV4(text);
  }

  /* ── AI Trip Coordinator (backend group_drive.py coordinate) ────────────── */
  var COORD_TYPE_LABEL = {
    wrong_turn: 'Chệch tuyến / Wrong turn', falling_behind: 'Tụt lại / Falling behind',
    group_split: 'Tách đoàn / Group split', delay_building: 'Chậm dần / Delay building',
    unexpected_stop: 'Dừng bất thường / Unexpected stop', gps_loss: 'Mất GPS / GPS weak',
    low_battery: 'Pin yếu / Low battery', rest_request: 'Xin nghỉ / Rest request',
    heavy_rain: 'Mưa lớn / Heavy rain',
  };
  function coordTypeLabel(t) { return COORD_TYPE_LABEL[t] || t; }
  function inferTripUI(f) {
    // an explicit vehicle reference names the trip even mid-session; only when the
    // query has none do we fall back to the active trip, then TRIP001.
    if (/\bev \d|pin yeu|diem sac|charg/.test(f)) return 'TRIP005';
    if (/\bvan \d/.test(f)) return 'TRIP003';
    if (/\bbike \d/.test(f)) return 'TRIP002';
    if (/\bcar [a-d]\b|pho co/.test(f)) return 'TRIP004';
    if (/\bcar \d/.test(f)) return 'TRIP001';
    if (S.group) return S.group.trip_id;
    return 'TRIP001';
  }
  function askCoordinator(text) {
    pushHistory('user', text);
    setWorking(true);
    showTransient({ steps: [{ label: 'Đang phân tích tình huống đoàn xe…' }], fade: false });
    var tripId = inferTripUI(fold(text));
    // pass the raw query as --member too; the backend resolves a vehicle label /
    // name / M0xx from it, or falls back to ALL.
    H.AtriaDash.json('group_drive.py',
      ['coordinate', '--trip', tripId, '--member', text, '--text', text],
      { timeout_ms: 60000 })
      .then(function (res) {
        setWorking(false);
        if (!res || res.ok === false) {
          showTransient({ text: 'Coordinator lỗi: ' + ((res && res.error) || 'unknown'), fade: true });
          return;
        }
        renderCoordinatorReply(res);
      })
      .catch(function (e) { setWorking(false); showTransient({ text: 'Coordinator lỗi: ' + e, fade: true }); });
  }
  function renderCoordinatorReply(res) {
    var reply = res.reply_vi || res.reply_en || '';
    pushHistory('ai', reply);
    renderCoordCard(res);
    var chips = [];
    var rec = res.recommend;
    if (rec && rec.lat != null) {
      var poi = { poi_id: rec.poi_id, name: rec.poi_name, lat: rec.lat, lng: rec.lng,
                  rating: rec.safe_stop_score, category: rec.poi_type };
      chips.push({ label: '⚑ Tập kết: ' + rec.poi_name, onClick: function () {
        clearSurfaced(true); closeSpotlight(); surfacePin(poi, '⚑'); routeToPoi(poi);
      } });
    }
    if (res.intent === 'create_trip') {
      chips.push({ label: '▶ Mở nhóm mô phỏng', onClick: function () { pickScenario(); } });
    }
    showTransient({ text: reply, chips: chips, fade: true });
    if (res.speak) speak(res.speak);   // voice-first, low-distraction
  }
  function renderCoordCard(res) {
    var card = railCardShell('v4CoordCard', '✦ AI Trip Coordinator');
    var body = el('<div class="v4-coord-body"></div>');
    var s = res.situation;
    if (s) {
      var sev = s.severity || '';
      body.appendChild(el('<div class="v4-coord-sit ' + esc(sev) + '">'
        + '<span class="cat">' + esc(coordTypeLabel(s.type)) + '</span>'
        + '<span class="pr">P' + (s.priority != null ? s.priority : '') + ' · ' + esc(sev) + '</span></div>'));
      body.appendChild(el('<div class="v4-coord-who">' + esc(s.vehicle_label || s.member_id || '')
        + (s.t != null ? ' · phút ' + s.t : '') + '</div>'));
      if (s.signal) body.appendChild(el('<div class="v4-coord-sig">' + esc(s.signal) + '</div>'));
    }
    if (res.false_emergency_avoided) {
      body.appendChild(el('<div class="v4-coord-sig good">✓ Không báo động khẩn — chỉ mất tín hiệu, đã báo trưởng đoàn.</div>'));
    }
    if (res.privacy) {
      body.appendChild(el('<div class="v4-coord-sit"><span class="cat">🔒 Privacy: '
        + esc(res.privacy.mode) + '</span></div>'));
      var opts = el('<div class="v4-coord-opts"></div>');
      (res.privacy.options || []).forEach(function (o) {
        opts.appendChild(el('<span class="v4-coord-opt">' + esc(o.replace(/_/g, ' ')) + '</span>'));
      });
      body.appendChild(opts);
    }
    if (res.prioritized) {
      var list = el('<div class="v4-coord-prio"></div>');
      res.prioritized.forEach(function (it, i) {
        list.appendChild(el('<div class="prow ' + esc(it.category) + '">'
          + '<span class="rk">' + (i + 1) + '</span>'
          + '<span class="ct">' + esc(it.category) + '</span>'
          + '<span class="pv">P' + it.priority + '</span></div>'));
      });
      body.appendChild(list);
    }
    if (res.summary) {
      var sm = res.summary;
      body.appendChild(el('<div class="v4-coord-sig">' + sm.events_total + ' sự kiện · '
        + sm.regroups + ' tập kết · ' + (sm.deviations || 0) + ' lệch tuyến · '
        + (sm.delays || 0) + ' chậm · ' + (sm.safety_incidents || 0) + ' an toàn</div>'));
    }
    if (res.predictive && res.predictive.proactive) {
      body.appendChild(el('<div class="v4-coord-sig warn">⚠ Rủi ro tách đoàn đang tăng ('
        + res.predictive.gap_min + ' phút) — nên tập kết chủ động.</div>'));
    }
    var rec = res.recommend;
    if (rec) {
      body.appendChild(el('<div class="v4-coord-rec"><span class="pin">⚑</span> '
        + esc(rec.poi_name) + ' · <span class="sf">an toàn ' + esc(String(rec.safe_stop_score)) + '</span></div>'));
    }
    card.appendChild(body);
    card.querySelector('.v4-rc-x').addEventListener('click', function () { card.remove(); });
    railUpsert(card);
  }

  /* ══════════════════════════════════════════════════════════════════════
     Phase C — video->location, general voice, proactivity, traffic, pop-outs.
     ══════════════════════════════════════════════════════════════════════ */
  var URL_RE = /https?:\/\/\S+/i;
  function isVideoIntent(text) {
    return URL_RE.test(text) || /\b(video|tiktok|reel|reels|douyin|clip)\b/i.test(text);
  }
  function resolveVideo(text) {
    pushHistory('user', text);
    setWorking(true);
    showTransient({ steps: [
      { label: 'Reading the video…' }, { label: 'Matching location…' },
    ], fade: false });
    H.AtriaDash.json('video_resolve.py', [], { stdin: JSON.stringify({ text: text }), timeout_ms: 30000 })
      .then(function (res) {
        setWorking(false);
        pushHistory('ai', res.reply_vi || res.reply_en || '');
        if (res.matched && res.poi) {
          var poi = res.poi;
          clearSurfaced(true); closeSpotlight();
          surfacePin(poi, '▶');
          map.flyTo([poi.lat, poi.lng], Math.max(map.getZoom(), 15));
          openCallout(poi);
          renderVideoCard(res);
          showTransient({ text: res.reply_vi, fade: true });
        } else {
          // honest miss — never fabricate a pin
          showTransient({ text: res.reply_vi || 'Khong khop duoc dia diem tu video.', fade: false });
        }
      })
      .catch(function (e) { setWorking(false); showTransient({ text: 'Loi doc video: ' + e }); });
  }
  function renderVideoCard(res) {
    var poi = res.poi, low = res.confidence < 0.7;
    var card = railCardShell('v4VideoCard', 'From a video');
    card.appendChild(el(
      '<div class="v4-video-thumb"><span class="play">&#9654;</span>'
      + '<span class="src">' + esc(res.source) + '</span>'
      + (res.creator ? '<span class="creator">' + esc(res.creator) + '</span>' : '') + '</div>'));
    var body = el('<div class="v4-video-body"></div>');
    if (res.query) body.appendChild(el('<div class="v4-video-cap">&ldquo;' + esc(res.query) + '&rdquo;</div>'));
    body.appendChild(el('<div class="v4-video-place"><span class="nm">&#8982; ' + esc(poi.name) + '</span>'
      + '<span class="badge' + (low ? ' low' : '') + '">' + Math.round(res.confidence * 100) + '% match</span></div>'));
    var go = el('<button class="v4-video-go">Take me there</button>');
    go.addEventListener('click', function () { map.flyTo([poi.lat, poi.lng], 16); openCallout(poi); });
    body.appendChild(go);
    card.appendChild(body);
    card.querySelector('.v4-rc-x').addEventListener('click', function () { card.remove(); });
    railUpsert(card);
  }

  /* ── general voice: REAL local mic session ─────────────────────────────────
     The mic button starts a local LiveKit console worker (voice/agent.py) via the
     voice_session.py bridge — it captures the OS mic, does OpenAI STT -> the map's
     own Jarvis brain -> OpenAI TTS on the OS speakers, and publishes each turn to
     Redis. We poll `status` and render the transcript + map artifacts here (the
     WORKER speaks, so we never call speak()). If the voice env isn't installed or
     the bridge errors, we fall back to the suggestion chips so the button always
     does something. (The iframe sandbox blocks a browser mic — hence the worker.) */
  var VOICE_STATE_LABEL = {
    listening: 'DANG NGHE… / LISTENING',
    thinking: 'DANG XU LY… / THINKING',
    speaking: 'DANG TRA LOI… / SPEAKING',
    error: 'LOI GIONG NOI / VOICE ERROR',
    stopped: 'DA DUNG / STOPPED',
  };

  function ensureSid() {
    if (!S.sessionId) {
      S.sessionId = 'v4-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8);
    }
    return S.sessionId;
  }

  // Fallback (voice env missing / bridge error): the old simulated picker.
  function openVoiceSuggestions(note) {
    $('v4VoiceState').textContent = note || 'GOI Y / SUGGESTIONS';
    var box = $('v4VoiceChips'); box.innerHTML = '';
    IDLE_CHIPS.forEach(function (q) {
      var b = el('<button class="v4-chip">🎙 ' + esc(q) + '</button>');
      b.addEventListener('click', function () {
        S.speakNext = true;
        setTimeout(function () { $('v4Voice').classList.remove('on'); submit(q); }, 300);
      });
      box.appendChild(b);
    });
    $('v4Voice').classList.add('on');
  }

  function openGeneralVoice() {
    if (S.voice) return;                       // a session is already live
    var sid = ensureSid();
    $('v4VoiceChips').innerHTML = '';
    $('v4VoiceState').textContent = 'DANG KHOI DONG… / STARTING';
    $('v4Voice').classList.add('on');
    var c = map.getCenter();
    var vp = JSON.stringify({ lat: c.lat, lng: c.lng, zoom: map.getZoom() });
    H.AtriaDash.json('voice_session.py', ['start', '--session', sid, '--viewport', vp],
      { timeout_ms: 20000 })
      .then(function (res) {
        if (!res || !res.ok) { openVoiceSuggestions('VOICE OFFLINE — GOI Y'); return; }
        S.voice = { sid: sid, lastSeq: (res.seq || 0), timer: null };
        $('v4VoiceState').textContent = VOICE_STATE_LABEL.listening;
        S.voice.timer = setInterval(voicePoll, 1200);
      })
      .catch(function () { openVoiceSuggestions('VOICE OFFLINE — GOI Y'); });
  }

  function voicePoll() {
    var v = S.voice; if (!v) return;
    H.AtriaDash.json('voice_session.py', ['status', '--session', v.sid], { timeout_ms: 8000 })
      .then(function (st) {
        if (!S.voice) return;                  // session closed while polling
        if (st.state && VOICE_STATE_LABEL[st.state]) {
          $('v4VoiceState').textContent = VOICE_STATE_LABEL[st.state];
        }
        if (st.running === false) {            // worker died / never came up
          voiceStopSession(true);
          openVoiceSuggestions('VOICE OFFLINE — GOI Y');
          return;
        }
        var seq = st.seq || 0;
        if (seq > v.lastSeq && st.state === 'speaking' && st.reply) {
          v.lastSeq = seq;
          voiceApplyTurn(st);
        }
      })
      .catch(function () { /* transient bridge hiccup — keep polling */ });
  }

  // Render one completed voice turn exactly like a typed turn (pins/route/reply),
  // but WITHOUT speaking — the worker already spoke via OpenAI TTS.
  function voiceApplyTurn(st) {
    var transcript = st.transcript || '';
    if (transcript) pushHistory('user', transcript);
    S.speakNext = false;
    renderAgentReply(transcript, {
      reply: st.reply, map_actions: st.map_actions || [], session_id: st.session_id,
    });
    if (S.voice) $('v4VoiceState').textContent = VOICE_STATE_LABEL.listening;
  }

  function voiceStopSession(skipStopCall) {
    var v = S.voice; S.voice = null;
    if (!v) return;
    if (v.timer) clearInterval(v.timer);
    if (!skipStopCall) {
      H.AtriaDash.json('voice_session.py', ['stop', '--session', v.sid], { timeout_ms: 8000 })
        .catch(function () {});
    }
  }

  /* ── proactivity (§2.13): one gentle timer-driven nudge ────────────────── */
  function scheduleProactive() {
    if (S.proactiveTimer) return;
    S.proactiveTimer = setTimeout(function () {
      // stay quiet if the user is busy: a trip, an open overlay, or mid-reply
      if (!document.body.classList.contains('design-v4')) return;
      if (S.tl || S.working || $('v4Voice').classList.contains('on')) return;
      showTransient({
        text: '☀ Troi dep o trung tam — gio la luc ly tuong de di dao. Ban muon goi y quan ca phe co san ngoai troi khong?',
        chips: [{ label: 'Cafe san vuon gan day', onClick: function () { submit('cafe san vuon'); } }],
        fade: true,
      });
      // the nudge auto-fades (~9.5s); don't leave the pill empty — bring the
      // idle suggestions back once it's gone, so they're never orphaned.
      S.proactiveRestore = setTimeout(function () {
        if (document.body.classList.contains('design-v4') && !S.tl && !S.working
            && !els.v4Trans.classList.contains('on')) showIdle();
      }, 10200);
    }, 20000);
  }

  /* ── traffic (§2.14): simulated congestion + ETA bump ──────────────────── */
  function activeRoutePts() {
    if (S.route && S.route.stops.length >= 2) return S.route.stops.map(function (s) { return [s.lat, s.lng]; });
    if (S.tl && S.tl.route && S.tl.route.polyline) return S.tl.route.polyline;
    return null;
  }
  function drawTraffic() {
    if (v4TrafficLayer) { map.removeLayer(v4TrafficLayer); v4TrafficLayer = null; }
    var pts = activeRoutePts();
    if (!pts) return;
    v4TrafficLayer = new L.LayerGroup().addTo(map);
    // congest the middle ~40% of the route
    var a = Math.floor(pts.length * 0.3), b = Math.max(a + 1, Math.floor(pts.length * 0.7));
    var seg = pts.slice(a, b + 1);
    if (seg.length >= 2) {
      v4TrafficLayer.addLayer(new L.Polyline(seg,
        { color: '#c4574a', weight: 7, opacity: .85, dashArray: '2 9', lineCap: 'round' }));
      var mid = seg[Math.floor(seg.length / 2)];
      v4TrafficLayer.addLayer(new L.Marker(mid, {
        icon: new L.DivIcon({ className: 'v4-traffic-badge', iconSize: [0, 0],
          html: '<div class="b">&#9677; slow &middot; +traffic</div>' }), zIndexOffset: 500 }));
    }
  }
  function toggleTraffic() {
    S.traffic = !S.traffic;
    $('v4Traffic').classList.toggle('on', S.traffic);
    if (S.traffic) {
      if (!activeRoutePts()) { toast('Chua co lo trinh — tao route de xem giao thong', 'info'); S.traffic = false; $('v4Traffic').classList.remove('on'); return; }
      drawTraffic();
      toast('Giao thong: dong o giua tuyen · ETA +~30%', 'info');
    } else if (v4TrafficLayer) { map.removeLayer(v4TrafficLayer); v4TrafficLayer = null; }
    if ($('v4RouteCard')) showRouteCard();   // reflect the ETA bump
  }

  /* ── pop-out compare windows (§2.7) ────────────────────────────────────── */
  var v4PopN = 0, v4PopZ = 1040;
  function openPopout(poi) {
    v4PopN++;
    var id = 'v4Pop' + v4PopN;
    var offset = 30 + (v4PopN % 5) * 26;
    var win = el('<div class="v4-pop" id="' + id + '" style="left:' + (60 + offset) + 'px;top:' + (90 + offset) + 'px"></div>');
    win.innerHTML =
      '<div class="v4-pop-head"><span class="t">' + esc(poi.name) + '</span>'
      + '<button class="close" title="Close">&#10005;</button></div>'
      + '<div class="v4-pop-thumb">&#9737;</div>'
      + '<div class="v4-pop-body">'
      +   '<div class="v4-pop-meta">' + (poi.rating ? '<span class="star">&#9733; ' + esc(poi.rating) + '</span> &middot; ' : '')
      +     esc(poi.district || poi.city || poi.detail || '') + '</div>'
      +   '<div class="v4-pop-tldr"><b>&#10022; tl;dr</b> &mdash; ' + calloutTldr(poi) + '</div>'
      +   '<button class="v4-pop-route">Route me there</button>'
      + '</div>';
    guard(win);
    $('v4App').appendChild(win);
    win.style.zIndex = ++v4PopZ;
    win.addEventListener('pointerdown', function () { if (v4PopZ < 1044) win.style.zIndex = ++v4PopZ; else win.style.zIndex = v4PopZ; });
    win.querySelector('.close').addEventListener('click', function () { win.remove(); });
    win.querySelector('.v4-pop-route').addEventListener('click', function () { routeToPoi(poi); });
    enablePopDrag(win, win.querySelector('.v4-pop-head'));
  }
  function enablePopDrag(win, head) {
    var dragging = false, sx = 0, sy = 0, ox = 0, oy = 0;
    head.addEventListener('pointerdown', function (e) {
      if (e.target.closest('button')) return;
      dragging = true;
      var r = win.getBoundingClientRect(); ox = r.left; oy = r.top; sx = e.clientX; sy = e.clientY;
      try { head.setPointerCapture(e.pointerId); } catch (x) {}
    });
    head.addEventListener('pointermove', function (e) {
      if (!dragging) return;
      var nx = Math.max(4, Math.min(ox + (e.clientX - sx), window.innerWidth - win.offsetWidth - 4));
      var ny = Math.max(4, Math.min(oy + (e.clientY - sy), window.innerHeight - 60));
      win.style.left = nx + 'px'; win.style.top = ny + 'px';
    });
    function end(e) { if (!dragging) return; dragging = false; try { head.releasePointerCapture(e.pointerId); } catch (x) {} }
    head.addEventListener('pointerup', end);
    head.addEventListener('pointercancel', end);
  }
  function clearPopouts() {
    Array.prototype.slice.call(document.querySelectorAll('.v4-pop')).forEach(function (w) { w.remove(); });
  }

  window.V4 = {
    loaded: true,
    hooks: null,
    init: function (hooks) {
      H = hooks; this.hooks = hooks;
      map = hooks.map;
      if (hooks.esc) esc = hooks.esc;
      v4PinLayer = new L.LayerGroup().addTo(map);
      v4RouteLayer = new L.LayerGroup().addTo(map);
      buildDom();
      buildTeamDom();
      wire();
      setDesign(location.hash === '#legacy' ? 'legacy' : 'v4');
      document.documentElement.setAttribute('data-v4', 'ready');
    },
  };
})();
