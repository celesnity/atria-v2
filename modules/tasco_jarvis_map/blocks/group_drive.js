/* Group Drive — Marlow Bay Agent v3 "new design" + simulated convoy demo.
   Loaded by dashboard.html; everything here is additive. The legacy dashboard
   keeps working untouched — dashboard.html only calls GroupDrive.init(hooks)
   when this script loaded, and the design toggle just swaps a body class.

   Simulation only (not hosted): ONE bridge call (group_drive.py timeline)
   returns the whole replay; playback is a local per-sim-minute clock. The AI
   coordinator's detections/regroups/priorities are computed server-side by
   rules over telemetry (eval-gated against the Track-7 gold sheets).

   hooks = { map, applyActionsLegacy, askJarvis, esc, AtriaDash } */
(function () {
  'use strict';

  var H = null;                 // hooks from dashboard.html
  var S = {
    group: null,                // create result
    tl: null,                   // timeline payload
    users: null,                // persona pool + scenarios
    t: 0, playing: false, speed: 1, timer: null,
    delivered: {},              // det_id -> true
    viewAs: 'member',           // 'member' | 'leader' (privacy demo)
    dockView: 'members', unread: 0,
    chatSession: null, busy: false,
    markers: {},                // member_id -> L.Marker
    layer: null, routeLayer: null, poiLayer: null,
    sosMember: null, callTimer: null, callSec: 0,
    dockRowEls: {},             // member_id -> {status}
  };
  var TICK_MS = 700;            // wall ms per sim minute at ×1

  function $(id) { return document.getElementById(id); }
  function esc(s) { return H.esc(String(s == null ? '' : s)); }
  function el(html) {
    var t = document.createElement('template');
    t.innerHTML = html.trim();
    return t.content.firstChild;
  }
  function fold(s) {
    // lowercase + strip diacritics + đ→d (mirror of the backend _fold)
    return String(s || '').toLowerCase().replace(/đ/g, 'd')
      .normalize('NFD').replace(/[̀-ͯ]/g, '');
  }
  function vehGlyph(type) {
    var t = String(type || '').toLowerCase();
    if (t.indexOf('motor') >= 0 || t.indexOf('bike') >= 0) return '🏍';
    if (t.indexOf('van') >= 0) return '🚐';
    if (t.indexOf('ev') >= 0) return '🔋';
    return '🚗';
  }
  function speak(text) {
    // voice-first is simulated; real TTS is a guarded bonus (sandbox may deny)
    try {
      if (window.speechSynthesis && window.SpeechSynthesisUtterance) {
        var u = new SpeechSynthesisUtterance(text);
        u.lang = 'vi-VN';
        window.speechSynthesis.speak(u);
      }
    } catch (e) { /* silent degrade */ }
  }

  /* ── DOM ──────────────────────────────────────────────────────────────── */
  function buildDom() {
    document.body.appendChild(el(
      '<button id="designToggle" title="Đổi giao diện / switch design"></button>'));
    var app = el('<div id="gdApp"></div>');
    app.appendChild(el(
      '<aside id="gdPanel" aria-label="Jarvis agent">'
      + '<div class="gd-head" id="gdHead">'
      +   '<div class="gd-orb">✦</div>'
      +   '<div><div class="gd-brand">Jarvis Map<span class="deg">°</span></div>'
      +   '<div class="gd-status" id="gdStatus"><span class="dot"></span><span id="gdStatusTxt">đang theo dõi bản đồ / watching the map</span></div></div>'
      +   '<button class="gd-min" id="gdMin" title="Thu gọn / minimize">–</button>'
      + '</div>'
      + '<div id="gdMsgs"></div>'
      + '<div class="gd-compose">'
      +   '<div class="gd-vchips" id="gdVchips" style="display:none"></div>'
      +   '<div class="gd-input-row">'
      +     '<input id="gdInput" placeholder="Hỏi Jarvis về địa điểm, đoàn xe… / ask Jarvis" />'
      +     '<button class="gd-mic" id="gdMic" title="Lệnh thoại / voice command">🎙</button>'
      +     '<button class="gd-send" id="gdSend" title="Gửi / send">→</button>'
      +   '</div>'
      + '</div>'
      + '<div class="gd-foot">Tasco · Jarvis Map — mô phỏng Group Drive (dữ liệu Track-7, không phải vị trí thật)</div>'
      + '</aside>'));
    app.appendChild(el(
      '<div id="gdTeamStrip" title="Đoàn xe / team"><div class="gd-strip-avs" id="gdStripAvs"></div>'
      + '<span class="gd-strip-label" id="gdStripLabel">● 0 live</span></div>'));
    app.appendChild(el(
      '<div id="gdDock">'
      + '<div class="gd-dock-head"><span id="gdDockTitle">Đoàn xe</span>'
      +   '<div class="gd-dock-tabs">'
      +     '<button class="gd-dock-tab on" id="gdTabMembers">Thành viên</button>'
      +     '<button class="gd-dock-tab" id="gdTabChat">💬 Chat<span id="gdUnread"></span></button>'
      +   '</div></div>'
      + '<div class="gd-dock-body" id="gdDockBody"></div>'
      + '<div class="gd-dock-foot">'
      +   '<button class="gd-dock-btn" id="gdFitAll">⌖ Toàn đoàn</button>'
      +   '<button class="gd-dock-btn" id="gdViewAs">👁 Xem: thành viên</button>'
      + '</div></div>'));
    app.appendChild(el(
      '<div id="gdSosBanner"><span class="fdot"></span><span id="gdSosText"></span>'
      + '<button id="gdSosCall">✆ Gọi</button><button id="gdSosResolve">Đã xử lý</button></div>'));
    app.appendChild(el(
      '<div id="gdTicker"><span class="spin"></span><span id="gdTickerTxt"></span></div>'));
    app.appendChild(el(
      '<div id="gdCallOverlay"><div class="gd-call-card">'
      + '<div class="gd-call-avwrap"><div class="gd-call-ring"></div><div class="gd-call-av" id="gdCallAv"></div></div>'
      + '<div class="gd-call-name" id="gdCallName"></div>'
      + '<div class="gd-call-status" id="gdCallStatus">đang gọi…</div>'
      + '<div class="gd-wave" id="gdCallWave" style="visibility:hidden"><i></i><i></i><i></i><i></i><i></i></div>'
      + '<div class="gd-call-btns">'
      +   '<button class="gd-call-btn" id="gdCallMute" title="Tắt tiếng">🔇</button>'
      +   '<button class="gd-call-btn end" id="gdCallEnd" title="Kết thúc">✆</button>'
      + '</div></div></div>'));
    app.appendChild(el(
      '<div id="gdVoiceOverlay"><div class="gd-call-card">'
      + '<div class="gd-voice-orb">✦</div>'
      + '<div class="gd-voice-state" id="gdVoiceState">ĐANG NGHE…</div>'
      + '<div class="gd-wave ai" id="gdVoiceWave"><i></i><i></i><i></i><i></i><i></i></div>'
      + '<div id="gdVoiceChips" class="gd-chips" style="justify-content:center"></div>'
      + '<div style="margin-top:12px"><button class="gd-call-btn" id="gdVoiceClose" title="Đóng">✕</button></div>'
      + '</div></div>'));
    app.appendChild(el(
      '<div id="gdSimBar"><span class="gd-sim-tag">SIM</span>'
      + '<button class="gd-sim-btn" id="gdPlay" title="Phát / tạm dừng">▶</button>'
      + '<button class="gd-sim-btn" id="gdEnd" title="Kết thúc chuyến / end trip" '
      + 'style="background:var(--ink)">⏭</button>'
      + '<button class="gd-speed" id="gdSpeed">×1</button>'
      + '<input type="range" id="gdScrub" min="0" max="90" value="0" />'
      + '<span class="gd-clock" id="gdClock">00:00<small> / 90p</small></span></div>'));
    document.body.appendChild(app);
  }

  /* ── design toggle ────────────────────────────────────────────────────── */
  function setDesign(mode) {
    var isNew = mode !== 'legacy';
    document.body.classList.toggle('design-new', isNew);
    $('designToggle').textContent = isNew
      ? '↺ Giao diện cũ / legacy' : '✦ Giao diện mới / new design';
    if (!isNew) pause();
    // the map is full-bleed in both designs; sizes can differ after a swap
    setTimeout(function () { H.map.invalidateSize(); }, 120);
  }

  /* ── chat stream ──────────────────────────────────────────────────────── */
  function gdMsg(kind, text, opts) {
    opts = opts || {};
    var div = document.createElement('div');
    div.className = 'gd-msg ' + kind;
    if (text) div.textContent = text;
    if (opts.widget) div.appendChild(opts.widget);
    if (opts.chips && opts.chips.length) {
      var box = document.createElement('div');
      box.className = 'gd-chips';
      opts.chips.forEach(function (c) {
        var b = document.createElement('button');
        b.className = 'gd-chip' + (c.accent ? ' accent' : '');
        b.textContent = c.label;
        b.addEventListener('click', function () { c.onClick(b); });
        box.appendChild(b);
      });
      div.appendChild(box);
    }
    if (opts.src) div.appendChild(el('<span class="gd-src">' + esc(opts.src) + '</span>'));
    $('gdMsgs').appendChild(div);
    $('gdMsgs').scrollTop = $('gdMsgs').scrollHeight;
    return div;
  }
  function showTyping() {
    hideTyping();
    $('gdMsgs').appendChild(el(
      '<div class="gd-typing" id="gdTyping"><span></span><span></span><span></span></div>'));
    $('gdMsgs').scrollTop = $('gdMsgs').scrollHeight;
  }
  function hideTyping() { var t = $('gdTyping'); if (t) t.remove(); }
  function setStatus(txt, busy) {
    $('gdStatusTxt').textContent = txt;
    $('gdStatus').classList.toggle('busy', !!busy);
  }
  function ticker(text, ttlMs) {
    $('gdTickerTxt').textContent = text;
    $('gdTicker').classList.add('on');
    if (ticker._t) clearTimeout(ticker._t);
    if (ttlMs !== 0) {
      ticker._t = setTimeout(function () { $('gdTicker').classList.remove('on'); },
        ttlMs || 3200);
    }
  }

  /* ── widgets ──────────────────────────────────────────────────────────── */
  function memberStatusLine(m, tick) {
    if (!tick) return { txt: 'sẵn sàng / ready', cls: '' };
    var st = tick.status, gap = tick.gap_km;
    if (S.sosMember === m.member_id) {
      return { txt: 'KHẨN CẤP — ' + gap + ' km', cls: 'sos' };
    }
    if (st === 'off_route') return { txt: 'chệch tuyến · lệch ' + tick.eta_gap_min + ' phút', cls: 'warn' };
    if (st === 'stopped') return { txt: 'đang dừng · cách đoàn ' + gap + ' km', cls: 'warn' };
    if (st === 'needs_charging') return { txt: 'pin yếu · cần sạc', cls: 'warn' };
    if (tick.eta_gap_min >= 5 || gap >= 3) {
      return { txt: 'tụt lại ' + gap + ' km · chậm ' + tick.eta_gap_min + ' phút', cls: 'warn' };
    }
    return { txt: 'đang chạy · cách đoàn ' + gap + ' km', cls: '' };
  }
  function privacyHidden(m) {
    return S.viewAs === 'member' && m.privacy === 'leader_only'
      && m.member_id !== selfId();
  }
  function selfId() { return S.group ? S.group.self_member_id : null; }

  function memberRow(m, tick) {
    var line = memberStatusLine(m, tick);
    var hidden = privacyHidden(m);
    var row = el('<div class="gd-member-row"></div>');
    row.appendChild(el('<div class="gd-av" style="background:' + m.color
      + (hidden ? ';opacity:.4' : '') + '">' + esc(m.initial) + '</div>'));
    var mid = el('<div></div>');
    var self = m.member_id === selfId();
    mid.appendChild(el('<div class="gd-m-name">' + esc(m.name)
      + (self ? ' <span style="color:var(--muted);font-size:9.5px">· bạn</span>'
        : ' <span class="gd-m-live">● LIVE</span>')
      + (m.role === 'leader' ? ' <span style="font-size:9px;color:var(--accent-ink)">👑 trưởng đoàn</span>' : '')
      + '</div>'));
    mid.appendChild(el('<div class="gd-m-status ' + line.cls + '">'
      + (hidden ? 'chỉ chia sẻ với trưởng đoàn 🔒' : esc(m.vehicle_label) + ' · ' + esc(line.txt))
      + '</div>'));
    row.appendChild(mid);
    var acts = el('<div class="gd-m-acts"></div>');
    if (!self) {
      var call = el('<button class="gd-m-btn call" title="Gọi / call">✆</button>');
      call.addEventListener('click', function () { startCall(m); });
      acts.appendChild(call);
    }
    var loc = el('<button class="gd-m-btn loc" title="Xem trên bản đồ / locate">⌖</button>');
    loc.addEventListener('click', function () { locateMember(m.member_id); });
    acts.appendChild(loc);
    if (!self) {
      var sos = el('<button class="gd-m-sos">SOS</button>');
      sos.addEventListener('click', function () { triggerSos(m); });
      acts.appendChild(sos);
    }
    row.appendChild(acts);
    return row;
  }

  function teamWidget() {
    var g = S.group;
    var w = el('<div class="gd-widget"></div>');
    w.appendChild(el('<div class="gd-w-title">' + esc(g.trip_name)
      + ' · <span class="live">' + g.members.length + ' live</span></div>'));
    var inv = el('<div class="gd-invite" title="Sao chép mã mời">' + esc(g.join_code) + ' ⧉</div>');
    inv.addEventListener('click', function () {
      H.AtriaDash.toast({ message: 'Đã sao chép mã mời ' + g.join_code + ' — gửi cho đoàn của bạn', severity: 'success' });
    });
    w.appendChild(inv);
    g.members.forEach(function (m) { w.appendChild(memberRow(m, tickOf(m.member_id))); });
    return w;
  }

  function alertWidget(det) {
    var g = S.group;
    var m = g.members.find(function (x) { return x.member_id === det.member_id; });
    var w = el('<div class="gd-widget gd-alert ' + det.severity + '"></div>');
    var head = el('<div class="gd-a-head"></div>');
    head.appendChild(el('<span class="gd-a-sev">' + esc(det.severity) + ' · P' + det.priority + '</span>'));
    if (m) head.appendChild(el('<span class="gd-m-name">' + esc(m.name) + ' · ' + esc(m.vehicle_label) + '</span>'));
    head.appendChild(el('<span class="gd-a-t">phút ' + det.t + '</span>'));
    w.appendChild(head);
    w.appendChild(el('<div style="font-size:12.5px">' + esc(det.message_vi) + '</div>'));
    w.appendChild(el('<div style="font-size:10.5px;color:var(--muted)">' + esc(det.message_en) + '</div>'));
    if (det.recommend) {
      w.appendChild(el('<div class="gd-a-reco">Đề xuất: <b>' + esc(det.recommend.poi_name)
        + '</b> (an toàn ' + Math.round(det.recommend.safe_stop_score * 100) + '%)</div>'));
    }
    return w;
  }

  function summaryWidget(sum) {
    var w = el('<div class="gd-widget"></div>');
    w.appendChild(el('<div class="gd-w-title">Tóm tắt chuyến đi / trip summary</div>'));
    var grid = el('<div class="gd-sum-grid"></div>');
    [[sum.duration_min + "'", 'mô phỏng'], [sum.events_total, 'sự kiện'],
     [sum.regroups, 'đề xuất tập kết']].forEach(function (c) {
      grid.appendChild(el('<div class="gd-sum-cell"><div class="gd-sum-num">' + c[0]
        + '</div><div class="gd-sum-lab">' + c[1] + '</div></div>'));
    });
    w.appendChild(grid);
    sum.per_member.forEach(function (pm) {
      var m = S.group.members.find(function (x) { return x.member_id === pm.member_id; });
      if (!m) return;
      w.appendChild(el('<div class="gd-member-row"><div class="gd-av" style="background:'
        + m.color + '">' + esc(m.initial) + '</div><div><div class="gd-m-name">'
        + esc(m.name) + '</div><div class="gd-m-status">đúng tuyến ' + pm.on_route_pct
        + '% · xa nhất ' + pm.max_gap_km + ' km · ' + pm.events + ' sự kiện</div></div></div>'));
    });
    return w;
  }

  /* ── map: members / route / POIs ─────────────────────────────────────── */
  function memberIcon(m, state) {
    var cls = 'gd-member-pin ' + (state || '')
      + (m.member_id === selfId() ? ' self' : '');
    return new L.DivIcon({
      className: 'gd-pin-icon',
      iconSize: [30, 30], iconAnchor: [15, 15],
      html: '<div class="' + cls + '"><span class="ring"></span>'
        + '<div class="av" style="background:' + m.color + '">' + esc(m.initial) + '</div>'
        + '<div class="lbl"><span class="ld"></span>' + esc(m.name) + '</div></div>',
    });
  }
  function tickOf(memberId) {
    if (!S.tl) return null;
    var tick = S.tl.ticks[Math.min(S.t, S.tl.ticks.length - 1)];
    return tick.members.find(function (x) { return x.member_id === memberId; });
  }
  function pinState(memberId, tick) {
    if (S.sosMember === memberId) return 'sos';
    if (privacyHidden(memberById(memberId))) return 'stale';
    if (!tick || !tick.gps_ok) return 'stale';
    if (memberId === selfId() && S.selfWarnUntil && S.t < S.selfWarnUntil) return 'warn';
    if (tick.status !== 'on_route' || tick.eta_gap_min >= 5 || tick.gap_km >= 3) return 'warn';
    return '';
  }
  function memberById(id) {
    return S.group.members.find(function (m) { return m.member_id === id; });
  }

  function drawScenario() {
    var tl = S.tl;
    if (S.layer) { H.map.removeLayer(S.layer); }
    if (S.routeLayer) { H.map.removeLayer(S.routeLayer); }
    if (S.poiLayer) { H.map.removeLayer(S.poiLayer); }
    S.layer = new L.LayerGroup().addTo(H.map);
    S.routeLayer = new L.LayerGroup().addTo(H.map);
    S.poiLayer = new L.LayerGroup().addTo(H.map);
    S.markers = {};
    S.routeLayer.addLayer(new L.Polyline(tl.route.polyline, {
      color: '#8b6fd8', weight: 4, opacity: .55, dashArray: '8 7',
    }));
    tl.route.waypoints.forEach(function (w) {
      if (w.type === 'Start' || w.type === 'Destination') {
        S.routeLayer.addLayer(new L.Marker([w.lat, w.lng], {
          icon: new L.DivIcon({
            className: 'gd-pin-icon', iconSize: [26, 26], iconAnchor: [13, 24],
            html: '<div class="gd-poi-pin" style="background:'
              + (w.type === 'Start' ? '#5d8bc4' : 'var(--accent)') + '"><span>'
              + (w.type === 'Start' ? '🚩' : '🏁') + '</span></div>',
          }),
          title: w.name,
        }));
      }
    });
    S.group.members.forEach(function (m) {
      var tk = tickOf(m.member_id);
      if (!tk) return;
      var mk = new L.Marker([tk.lat, tk.lng], {
        icon: memberIcon(m, pinState(m.member_id, tk)),
        title: m.name, zIndexOffset: 900,
      });
      S.layer.addLayer(mk);
      S.markers[m.member_id] = mk;
    });
    fitGroup();
  }
  function fitGroup() {
    var pts = [];
    Object.keys(S.markers).forEach(function (id) {
      var ll = S.markers[id].getLatLng();
      pts.push([ll.lat, ll.lng]);
    });
    if (pts.length) {
      H.map.fitBounds(new L.LatLngBounds(pts), { padding: [70, 70], maxZoom: 12 });
    }
  }
  function locateMember(id) {
    var mk = S.markers[id];
    if (mk) {
      var ll = mk.getLatLng();
      H.map.flyTo([ll.lat, ll.lng], Math.max(H.map.getZoom(), 12));
    }
  }
  function showRegroupPoi(rec, fromMemberId) {
    S.poiLayer.clearLayers();
    S.poiLayer.addLayer(new L.Marker([rec.lat, rec.lng], {
      icon: new L.DivIcon({
        className: 'gd-pin-icon', iconSize: [26, 26], iconAnchor: [13, 24],
        html: '<div class="gd-poi-pin"><span>🅿</span></div>',
      }),
      title: rec.poi_name, zIndexOffset: 950,
    }));
    var pts = [[rec.lat, rec.lng]];
    var mk = fromMemberId && S.markers[fromMemberId];
    if (mk) {
      var ll = mk.getLatLng();
      // mock routing per the dataset README: a dashed direct connector
      S.poiLayer.addLayer(new L.Polyline([[ll.lat, ll.lng], [rec.lat, rec.lng]], {
        color: '#4f9464', weight: 3, opacity: .8, dashArray: '4 6',
      }));
      pts.push([ll.lat, ll.lng]);
    }
    H.map.fitBounds(new L.LatLngBounds(pts), { padding: [80, 80], maxZoom: 13 });
    ticker('Điểm tập kết: ' + rec.poi_name, 4200);
  }

  /* ── team strip + dock ────────────────────────────────────────────────── */
  function renderStrip() {
    var g = S.group;
    var avs = $('gdStripAvs');
    avs.innerHTML = '';
    g.members.forEach(function (m) {
      avs.appendChild(el('<div class="gd-av" style="background:' + m.color + '">'
        + esc(m.initial) + '</div>'));
    });
    $('gdStripLabel').textContent = '● ' + g.members.length + ' live';
    $('gdTeamStrip').classList.add('on');
  }
  function renderDock() {
    var body = $('gdDockBody');
    body.innerHTML = '';
    S.dockRowEls = {};
    if (S.dockView === 'members') {
      S.group.members.forEach(function (m) {
        body.appendChild(memberRow(m, tickOf(m.member_id)));
      });
    } else {
      (S.teamChat || []).forEach(function (msg) { body.appendChild(teamMsgEl(msg)); });
      var inp = el('<div class="gd-input-row" style="margin-top:6px">'
        + '<input id="gdTeamInput" placeholder="Nhắn cả đoàn…" style="flex:1;min-width:0;'
        + 'border:1.4px solid var(--line);background:var(--surface2);color:var(--ink);'
        + 'border-radius:999px;padding:6px 11px;font:600 11.5px Nunito,sans-serif;outline:none">'
        + '<button class="gd-send" style="width:28px;height:28px;font-size:12px" id="gdTeamSend">→</button></div>');
      body.appendChild(inp);
      $('gdTeamSend').addEventListener('click', sendTeamMsg);
      $('gdTeamInput').addEventListener('keydown', function (e) {
        if (e.key === 'Enter') sendTeamMsg();
      });
      body.scrollTop = body.scrollHeight;
    }
  }
  function teamMsgEl(msg) {
    if (msg.who === 'sys') {
      return el('<div class="gd-tmsg sys">' + esc(msg.text) + '</div>');
    }
    var me = msg.who === 'me';
    var m = me ? null : memberById(msg.who);
    var d = el('<div class="gd-tmsg' + (me ? ' me' : '') + '"></div>');
    if (m) {
      d.appendChild(el('<div class="who" style="color:' + m.color + '">' + esc(m.name) + '</div>'));
    }
    d.appendChild(el('<div class="bub">' + esc(msg.text) + '</div>'));
    return d;
  }
  function pushTeamMsg(who, text) {
    S.teamChat = S.teamChat || [];
    S.teamChat.push({ who: who, text: text });
    if (S.dockView === 'chat' && $('gdDock').classList.contains('open')) {
      renderDock();
    } else {
      S.unread++;
      $('gdUnread').textContent = ' ' + S.unread;
    }
  }
  function sendTeamMsg() {
    var inp = $('gdTeamInput');
    var v = (inp.value || '').trim();
    if (!v) return;
    inp.value = '';
    pushTeamMsg('me', v);
    // scripted acknowledgement (simulation): the leader answers
    var leader = S.group.members.find(function (m) { return m.role === 'leader'; });
    setTimeout(function () {
      pushTeamMsg(leader.member_id, 'Ok, đã nhận! / got it');
    }, 900);
    renderDock();
  }

  /* ── alerts: prioritized delivery (minimal driver distraction) ────────── */
  var CANNED_REPLY = {
    wrong_turn: 'Xin lỗi cả đoàn, tôi rẽ nhầm — đang quay lại tuyến!',
    falling_behind: 'Tôi bị kẹt xe, mọi người cứ giữ tốc độ nhé.',
    group_split: 'Tôi hơi tụt lại, sẽ gặp mọi người ở điểm tập kết.',
    unexpected_stop: 'Tôi phải dừng khẩn — sẽ nhắn lại ngay.',
    gps_loss: '(mất tín hiệu…)',
    low_battery: 'Pin xe tôi yếu, cần ghé trạm sạc gần nhất.',
    rest_request: 'Cho tôi nghỉ 10 phút ở điểm dừng tới nhé?',
    delay_building: 'Đường đông quá, tôi chậm mất vài phút.',
  };
  function deliverDetection(det) {
    if (S.delivered[det.det_id]) return;
    S.delivered[det.det_id] = true;
    var m = memberById(det.member_id);
    var chips = (det.chips || []).map(function (c) {
      return {
        label: c.label,
        accent: c.act === 'route_poi',
        onClick: function () {
          if (c.act === 'call' && m) startCall(m);
          if (c.act === 'locate') locateMember(c.member_id);
          if (c.act === 'route_poi' && det.recommend) {
            showRegroupPoi(det.recommend, det.member_id);
          }
        },
      };
    });
    // priority policy: ONE modal surface max. High → toast + voice + bubble;
    // medium → toast + bubble; low → bubble + ticker only.
    // While muted (VC005) non-critical alerts stay silent: bubble + ticker only.
    gdMsg('ai', '', { widget: alertWidget(det), chips: chips });
    if (det.priority >= 70) {
      H.AtriaDash.toast({ message: '⚠ ' + det.message_vi, severity: 'error' });
      speak(det.message_vi);
    } else if (S.muted) {
      ticker('🔕 ' + det.message_vi, 3600);
    } else if (det.priority >= 40) {
      H.AtriaDash.toast({ message: det.message_vi, severity: 'info' });
    } else {
      ticker(det.message_vi, 3600);
    }
    if (m && CANNED_REPLY[det.type]) {
      pushTeamMsg(det.member_id, CANNED_REPLY[det.type]);
    }
    setStatus('phát hiện: ' + det.type.replace(/_/g, ' '), true);
    setTimeout(function () {
      setStatus('đang theo dõi đoàn xe / watching your convoy', false);
    }, 2600);
  }

  /* ── SOS + calls ──────────────────────────────────────────────────────── */
  function triggerSos(m) {
    S.sosMember = m.member_id;
    $('gdSosText').textContent = 'KHẨN CẤP — vị trí của ' + m.name + ' đã chia sẻ cho cả đoàn';
    $('gdSosBanner').classList.add('on');
    refreshPins();
    renderDock();
    pushTeamMsg('sys', '🚨 SOS: ' + m.name + ' cần hỗ trợ');
    speak('Khẩn cấp. ' + m.name + ' cần hỗ trợ.');
    $('gdSosCall').onclick = function () { startCall(m); };
    locateMember(m.member_id);
  }
  function resolveSos() {
    if (!S.sosMember) return;
    var m = memberById(S.sosMember);
    S.sosMember = null;
    $('gdSosBanner').classList.remove('on');
    refreshPins();
    renderDock();
    pushTeamMsg('sys', '✅ SOS của ' + m.name + ' đã xử lý');
  }
  function startCall(m) {
    $('gdCallAv').style.background = m.color;
    $('gdCallAv').textContent = m.initial;
    $('gdCallName').textContent = m.name + ' · ' + m.vehicle_label;
    $('gdCallStatus').textContent = 'đang gọi…';
    $('gdCallStatus').classList.remove('live');
    $('gdCallWave').style.visibility = 'hidden';
    $('gdCallOverlay').classList.add('on');
    S.callSec = 0;
    clearInterval(S.callTimer);
    S.callTimer = setTimeout(function () {
      $('gdCallStatus').classList.add('live');
      $('gdCallWave').style.visibility = 'visible';
      S.callTimer = setInterval(function () {
        S.callSec++;
        var mm = String(Math.floor(S.callSec / 60));
        var ss = String(S.callSec % 60).padStart(2, '0');
        $('gdCallStatus').textContent = 'đã kết nối · ' + mm + ':' + ss + ' (mô phỏng)';
      }, 1000);
    }, 1400);
  }
  function endCall() {
    clearInterval(S.callTimer);
    clearTimeout(S.callTimer);
    $('gdCallOverlay').classList.remove('on');
  }

  /* ── voice commands (simulated voice-first) ──────────────────────────── */
  function openVoice() {
    if (!S.tl) {
      H.AtriaDash.toast({ message: 'Tạo nhóm trước để dùng lệnh thoại', severity: 'info' });
      return;
    }
    $('gdVoiceState').textContent = 'ĐANG NGHE…';
    var box = $('gdVoiceChips');
    box.innerHTML = '';
    S.tl.voice_commands.forEach(function (vc) {
      var b = el('<button class="gd-chip">' + esc(vc.text_vi) + '</button>');
      b.addEventListener('click', function () { runVoice(vc.text_vi); });
      box.appendChild(b);
    });
    $('gdVoiceOverlay').classList.add('on');
  }
  function runVoice(text) {
    $('gdVoiceState').textContent = 'ĐANG XỬ LÝ…';
    H.AtriaDash.json('group_drive.py',
      ['voice', '--text', text, '--trip', S.group.trip_id])
      .then(function (res) {
        $('gdVoiceState').textContent = 'ĐANG TRẢ LỜI…';
        gdMsg('user', '🎙 ' + text);
        gdMsg('ai', res.reply_vi + '\n' + res.reply_en,
          { src: 'voice · ' + res.intent + ' · ưu tiên ' + res.priority });
        (res.map_actions || []).forEach(function (a) {
          if (a.type === 'route_poi') {
            showRegroupPoi({ poi_name: a.name, lat: a.lat, lng: a.lng,
              poi_id: a.poi_id, safe_stop_score: 1 }, selfId());
          }
        });
        applyVoiceAction(res.structured_action, text);
        speak(res.reply_vi);
        setTimeout(function () { $('gdVoiceOverlay').classList.remove('on'); }, 900);
      })
      .catch(function (e) {
        $('gdVoiceOverlay').classList.remove('on');
        H.AtriaDash.toast({ message: 'Lỗi lệnh thoại: ' + e, severity: 'error' });
      });
  }

  /* a voice command must have a VISIBLE group effect, not just a reply —
     team-chat messages, mute state, SOS, pin state (all labeled simulation) */
  function applyVoiceAction(act, spokenText) {
    if (!act || !S.tl) return;
    var self = memberById(selfId());
    var leader = S.group.members.find(function (m) { return m.role === 'leader'; });
    switch (act.action) {
      case 'notify_group':
        pushTeamMsg('me', spokenText);
        setTimeout(function () {
          pushTeamMsg(leader.member_id, 'Ok, cả nhóm sẽ chờ / got it 👍');
        }, 900);
        H.AtriaDash.toast({ message: 'Đã gửi vào chat đoàn — mở 💬 để xem', severity: 'success' });
        break;
      case 'share_eta': {
        var tk = tickOf(selfId());
        var eta = tk ? tk.eta_gap_min : 0;
        pushTeamMsg('me', 'ETA của tôi: ' + (eta >= 1
          ? 'chậm ' + Math.round(eta) + ' phút so với kế hoạch'
          : 'đúng kế hoạch') + ' (phút ' + S.t + ')');
        break;
      }
      case 'request_rest_stop':
        pushTeamMsg('me', spokenText);
        setTimeout(function () {
          pushTeamMsg(leader.member_id, 'Ok, nghỉ ở điểm dừng an toàn kế tiếp nhé');
        }, 900);
        break;
      case 'report_wrong_turn':
        pushTeamMsg('me', spokenText);
        S.selfWarnUntil = S.t + 3;   // brief warn ring on your own pin
        refreshPins();
        break;
      case 'emergency_check':
        triggerSos(self);
        break;
      case 'continue_without_member':
        pushTeamMsg('sys', '➡ ' + self.name + ' tách đoàn tạm thời — nhóm tiếp tục');
        break;
      case 'mute_noncritical': {
        S.muted = true;
        // "until the highway exit": next Exit/Junction waypoint after now
        var wp = (S.tl.route.waypoints || []).find(function (w) {
          return /exit|junction/i.test(w.type) && w.planned_arrival_min > S.t;
        });
        S.unmuteAt = wp ? wp.planned_arrival_min : S.tl.trip.duration_min;
        pushTeamMsg('sys', '🔕 Thông báo không khẩn cấp tắt đến '
          + (wp ? wp.name : 'cuối chuyến') + ' (phút ' + S.unmuteAt + ')');
        ticker('🔕 Đã tắt thông báo không khẩn cấp', 3600);
        break;
      }
      default:
        break;
    }
  }
  function renderVoiceChips() {
    var box = $('gdVchips');
    box.innerHTML = '';
    if (!S.tl) { box.style.display = 'none'; return; }
    box.style.display = 'flex';
    S.tl.voice_commands.slice(0, 4).forEach(function (vc) {
      var b = el('<button class="gd-vchip">🎙 ' + esc(vc.text_vi) + '</button>');
      b.addEventListener('click', function () { runVoice(vc.text_vi); });
      box.appendChild(b);
    });
  }

  /* ── sim clock ────────────────────────────────────────────────────────── */
  function refreshPins() {
    S.group.members.forEach(function (m) {
      var mk = S.markers[m.member_id];
      var tk = tickOf(m.member_id);
      if (!mk || !tk) return;
      if (!privacyHidden(m) || S.viewAs === 'leader') mk.setLatLng([tk.lat, tk.lng]);
      mk.setIcon(memberIcon(m, pinState(m.member_id, tk)));
    });
  }
  function setTick(t, silent) {
    S.t = Math.max(0, Math.min(t, S.tl.trip.duration_min));
    refreshPins();
    if ($('gdDock').classList.contains('open') && S.dockView === 'members') renderDock();
    $('gdScrub').value = S.t;
    var hh = String(Math.floor(S.t / 60)).padStart(2, '0');
    var mm = String(S.t % 60).padStart(2, '0');
    $('gdClock').innerHTML = hh + ':' + mm
      + '<small> / ' + S.tl.trip.duration_min + 'p</small>';
    if (S.muted && S.unmuteAt != null && S.t >= S.unmuteAt) {
      S.muted = false;
      S.unmuteAt = null;
      pushTeamMsg('sys', '🔔 Đã bật lại thông báo đầy đủ');
      ticker('🔔 Thông báo đã bật lại', 3200);
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
    document.body.classList.add('gd-smooth');
    $('gdPlay').textContent = '❚❚';
    S.timer = setInterval(tickForward, TICK_MS / S.speed);
  }
  function pause() {
    S.playing = false;
    document.body.classList.remove('gd-smooth');
    if ($('gdPlay')) $('gdPlay').textContent = '▶';
    clearInterval(S.timer);
  }
  function endTrip() {
    // "kết thúc chuyến đi": stop the clock, skip ahead, summarize
    if (!S.tl || S.summaryShown) return;
    pause();
    pushTeamMsg('sys', '🏁 Chuyến đi kết thúc — cảm ơn cả đoàn!');
    setTick(S.tl.trip.duration_min, true);   // marks the rest delivered; endSim runs
  }
  function leaveGroup() {
    pause();
    if (S.layer) H.map.removeLayer(S.layer);
    if (S.routeLayer) H.map.removeLayer(S.routeLayer);
    if (S.poiLayer) H.map.removeLayer(S.poiLayer);
    S.layer = S.routeLayer = S.poiLayer = null;
    S.markers = {};
    S.tl = null; S.group = null; S.teamChat = [];
    S.sosMember = null; S.muted = false; S.unmuteAt = null;
    S.summaryShown = false; S.delivered = {}; S.t = 0; S.unread = 0;
    $('gdUnread').textContent = '';
    $('gdTeamStrip').classList.remove('on');
    $('gdDock').classList.remove('open');
    $('gdSosBanner').classList.remove('on');
    $('gdSimBar').classList.remove('on');
    $('gdVchips').style.display = 'none';
    document.body.classList.remove('gd-live');
    setStatus('đang theo dõi bản đồ / watching the map', false);
    gdMsg('ai', 'Đã rời nhóm — bản đồ trở lại bình thường. Tạo nhóm mới bất cứ lúc nào!', {
      chips: [{
        label: '✚ Tạo nhóm Group Drive', accent: true,
        onClick: function () { pickScenario(); },
      }],
    });
  }
  function endSim() {
    pause();
    if (S.summaryShown) return;
    S.summaryShown = true;
    var bubble = gdMsg('ai', 'Chuyến đi mô phỏng đã kết thúc — đây là tóm tắt:\n'
      + S.tl.summary.headline_vi, {
      widget: summaryWidget(S.tl.summary),
      chips: [{
        label: '↻ Phát lại / replay',
        onClick: function () {
          S.summaryShown = false;
          S.delivered = {};
          setTick(0, true);
          play();
        },
      }, {
        label: '✕ Rời nhóm / leave group',
        onClick: function () { leaveGroup(); },
      }],
    });
    speak('Chuyến đi mô phỏng đã kết thúc.');
    // deterministic templates are the source of truth; the LLM only rephrases
    // when reachable (graceful no-op offline) — user-chosen policy
    H.AtriaDash.json('group_drive.py', ['polish'], {
      stdin: JSON.stringify({ texts: [S.tl.summary.headline_vi], lang: 'vi' }),
      timeout_ms: 50000,
    }).then(function (res) {
      if (res && res.polished && res.texts && res.texts[0] && bubble.firstChild) {
        bubble.firstChild.textContent = 'Chuyến đi mô phỏng đã kết thúc — đây là tóm tắt:\n'
          + res.texts[0];
        bubble.appendChild(el('<span class="gd-src">✦ diễn đạt bởi AI · số liệu từ mô phỏng</span>'));
      }
    }).catch(function () { /* templates stand */ });
  }

  /* ── create-group flow ────────────────────────────────────────────────── */
  function welcome() {
    gdMsg('ai',
      'Xin chào! Tôi là Jarvis — trợ lý bản đồ và đoàn xe.\n'
      + 'Hỏi tôi về địa điểm ở Việt Nam, hoặc tạo một nhóm Group Drive mô phỏng '
      + '(chọn ngẫu nhiên 4 thành viên từ 8 người dùng demo).',
      {
        chips: [
          {
            label: '✚ Tạo nhóm Group Drive', accent: true,
            onClick: function () { pickScenario(); },
          },
          {
            label: '🔍 Tìm cafe gần đây',
            onClick: function () { sendToJarvis('cafe gần đây'); },
          },
        ],
      });
  }
  function pickScenario() {
    ticker('Đang tải kịch bản & người dùng…', 0);
    H.AtriaDash.json('group_drive.py', ['users']).then(function (res) {
      S.users = res;
      $('gdTicker').classList.remove('on');
      var w = el('<div class="gd-widget"></div>');
      w.appendChild(el('<div class="gd-w-title">Chọn kịch bản / choose a scenario</div>'));
      res.scenarios.forEach(function (sc, i) {
        var row = el('<div class="gd-row"><div class="gd-row-n">' + (i + 1) + '</div>'
          + '<div><div class="gd-row-name">' + esc(sc.trip_name) + '</div>'
          + '<div class="gd-row-meta">' + esc(sc.scenario) + ' · ' + sc.vehicle_count
          + ' xe · ' + esc(sc.origin) + ' → ' + esc(sc.destination) + '</div></div></div>');
        row.addEventListener('click', function () { createGroup(sc.trip_id); });
        w.appendChild(row);
      });
      gdMsg('ai', 'Chọn một kịch bản Track-7 (mặc định: chuyến gia đình Hà Nội → Hạ Long):',
        { widget: w });
    }).catch(function (e) {
      $('gdTicker').classList.remove('on');
      gdMsg('ai', 'Không tải được dữ liệu demo: ' + e, {});
    });
  }
  function createGroup(tripId) {
    var seed = Math.floor(Math.random() * 900) + 1;   // demo seed; sim itself is deterministic per seed
    ticker('Đang lập nhóm — chọn ngẫu nhiên thành viên…', 0);
    setStatus('đang lập nhóm…', true);
    H.AtriaDash.json('group_drive.py',
      ['timeline', '--trip', tripId, '--seed', String(seed)])
      .then(function (tl) {
        $('gdTicker').classList.remove('on');
        S.tl = tl;
        S.group = tl.group;
        S.t = 0;
        S.delivered = {};
        S.summaryShown = false;
        S.teamChat = [{ who: 'sys', text: 'Nhóm ' + tl.group.join_code + ' đã tạo — mô phỏng' }];
        var self = memberById(selfId());
        gdMsg('ai',
          'Nhóm đã sẵn sàng! Tôi chọn ngẫu nhiên ' + tl.group.members.length
          + ' người từ nhóm demo. Bạn là ' + self.name + ' (' + self.vehicle_label + ').\n'
          + 'Tôi sẽ theo dõi cả đoàn và cảnh báo khi có sự cố.',
          {
            widget: teamWidget(),
            chips: [{
              label: '▶ Bắt đầu mô phỏng', accent: true,
              onClick: function () { play(); },
            }],
          });
        renderStrip();
        renderDock();
        renderVoiceChips();
        drawScenario();
        document.body.classList.add('gd-live');   // base POI pins recede
        $('gdSimBar').classList.add('on');
        $('gdScrub').max = tl.trip.duration_min;
        setTick(0, true);
        setStatus('đang theo dõi đoàn xe / watching your convoy', false);
        speak('Nhóm ' + tl.group.trip_name + ' đã sẵn sàng.');
      })
      .catch(function (e) {
        $('gdTicker').classList.remove('on');
        setStatus('đang theo dõi bản đồ', false);
        gdMsg('ai', 'Không tạo được nhóm: ' + e, {});
      });
  }

  /* ── composer routing: trip control > corridor search > jarvis ────────── */
  // controlled vocab (folded) — verbs/relations only, never place names
  var CTRL_END = /(ket thuc|end trip|dung chuyen|stop trip)/;
  var CTRL_PAUSE = /(tam dung|\bpause\b)/;
  var CTRL_RESUME = /(tiep tuc|\bresume\b|\bcontinue\b)/;
  var ROUTE_WORDS = /(tren duong|tren tuyen|tren doan|doc duong|doc tuyen|team trip|trip nay|chuyen di|chuyen nay|on the (way|route|trip)|along the route)/;

  function routeMessage(text) {
    var f = fold(text);
    if (S.tl) {
      if (CTRL_END.test(f)) {
        gdMsg('user', text);
        gdMsg('ai', 'Ok, mình kết thúc chuyến đi và tổng kết lại nhé.');
        endTrip();
        return;
      }
      if (CTRL_PAUSE.test(f)) {
        gdMsg('user', text);
        pause();
        gdMsg('ai', 'Đã tạm dừng mô phỏng — gõ "tiếp tục" hoặc nhấn ▶ để chạy tiếp.');
        return;
      }
      if (CTRL_RESUME.test(f) && f.indexOf('khong can') < 0
          && f.indexOf('without') < 0 && !S.summaryShown) {
        gdMsg('user', text);
        play();
        gdMsg('ai', 'Tiếp tục mô phỏng!');
        return;
      }
      if (ROUTE_WORDS.test(f)) { alongSearch(text); return; }
    }
    sendToJarvis(text);
  }

  /* ── trip-corridor search ("có quán cafe nào trên đường không?") ──────── */
  function alongSearch(text) {
    if (S.busy) return;
    S.busy = true;
    gdMsg('user', text);
    showTyping();
    setStatus('đang tìm dọc tuyến…', true);
    H.AtriaDash.json('group_drive.py',
      ['along', '--trip', S.group.trip_id, '--query', text])
      .then(function (res) {
        hideTyping();
        if (!res.ok || !res.results) {
          gdMsg('ai', 'Không tìm được dọc tuyến: ' + (res.error || 'lỗi'), {});
          return;
        }
        // numbered pins on the map via the legacy pins action (external:true
        // keeps them out of the jarvis chat-context pin list)
        H.applyActionsLegacy([{
          type: 'pins', fit: true,
          items: res.results.map(function (r, i) {
            return { n: i + 1, name: r.name, lat: r.lat, lng: r.lng,
              rating: r.rating, detail: r.detail, external: true };
          }),
        }]);
        var w = el('<div class="gd-widget"></div>');
        res.results.forEach(function (r, i) {
          var row = el('<div class="gd-row"><div class="gd-row-n">' + (i + 1) + '</div>'
            + '<div><div class="gd-row-name">' + esc(r.name)
            + (r.rating ? ' <span style="color:var(--star)">★' + esc(r.rating) + '</span>' : '')
            + '</div><div class="gd-row-meta">' + esc(r.detail || r.category || '')
            + ' · km ' + r.route_km + (r.detour_km ? ' · lệch tuyến ' + r.detour_km + ' km' : '')
            + '</div></div></div>');
          row.addEventListener('click', function () {
            H.map.flyTo([r.lat, r.lng], Math.max(H.map.getZoom(), 14));
          });
          w.appendChild(row);
        });
        gdMsg('ai', res.reply_vi + '\n' + res.reply_en, {
          widget: w,
          src: res.fallback ? 'điểm dừng an toàn trên tuyến · dữ liệu tuyến Track-7'
            : 'dọc tuyến ±5km · dữ liệu bản đồ',
        });
      })
      .catch(function (e) {
        hideTyping();
        gdMsg('ai', 'Lỗi tìm dọc tuyến: ' + e, {});
      })
      .then(function () {
        S.busy = false;
        setStatus('đang theo dõi đoàn xe / watching your convoy', false);
      });
  }

  /* ── jarvis passthrough (chat-first search in the new design) ─────────── */
  function sendToJarvis(text) {
    if (S.busy) return;
    S.busy = true;
    gdMsg('user', text);
    showTyping();
    setStatus('đang tìm…', true);
    var c = H.map.getCenter();
    H.AtriaDash.json('jarvis_chat.py', [], {
      stdin: JSON.stringify({
        message: text,
        chat_session_id: S.chatSession,
        interactive: true,
        viewport: { lat: c.lat, lng: c.lng, zoom: H.map.getZoom() },
        pins: [],
      }),
      timeout_ms: 110000,
    }).then(function (res) {
      hideTyping();
      if (res.session_id) S.chatSession = res.session_id;
      if (res.error && !res.reply) {
        gdMsg('ai', 'Jarvis không phản hồi: ' + res.error, {});
      } else {
        H.applyActionsLegacy(res.map_actions || []);
        gdMsg('ai', res.reply || '(không có trả lời)', {
          src: res.source === 'fast' ? 'instant · local search' : null,
        });
      }
    }).catch(function (e) {
      hideTyping();
      gdMsg('ai', 'Lỗi Jarvis: ' + e, {});
    }).then(function () {
      S.busy = false;
      setStatus(S.tl ? 'đang theo dõi đoàn xe / watching your convoy'
        : 'đang theo dõi bản đồ / watching the map', false);
    });
  }

  /* ── panel drag ───────────────────────────────────────────────────────── */
  function enableDrag() {
    var head = $('gdHead');
    var panel = $('gdPanel');
    var sx = 0, sy = 0, ox = 0, oy = 0, dragging = false;
    head.addEventListener('pointerdown', function (e) {
      if (e.target.closest('button')) return;
      dragging = true;
      sx = e.clientX; sy = e.clientY;
      var r = panel.getBoundingClientRect();
      ox = r.left; oy = r.top;
      head.setPointerCapture(e.pointerId);
    });
    head.addEventListener('pointermove', function (e) {
      if (!dragging) return;
      var nx = Math.max(4, Math.min(ox + e.clientX - sx, window.innerWidth - 80));
      var ny = Math.max(4, Math.min(oy + e.clientY - sy, window.innerHeight - 60));
      panel.style.left = nx + 'px';
      panel.style.top = ny + 'px';
    });
    head.addEventListener('pointerup', function () { dragging = false; });
  }

  /* ── wiring ───────────────────────────────────────────────────────────── */
  function wire() {
    $('designToggle').addEventListener('click', function () {
      setDesign(document.body.classList.contains('design-new') ? 'legacy' : 'new');
    });
    $('gdSend').addEventListener('click', function () {
      var v = $('gdInput').value.trim();
      if (v) { $('gdInput').value = ''; routeMessage(v); }
    });
    $('gdInput').addEventListener('keydown', function (e) {
      if (e.key === 'Enter') {
        var v = $('gdInput').value.trim();
        if (v) { $('gdInput').value = ''; routeMessage(v); }
      }
    });
    $('gdMic').addEventListener('click', openVoice);
    $('gdVoiceClose').addEventListener('click', function () {
      $('gdVoiceOverlay').classList.remove('on');
    });
    $('gdMin').addEventListener('click', function () {
      $('gdPanel').classList.add('collapsed');
      ticker('Nhấn ✦ Giao diện… để mở lại panel — hoặc phím J', 4200);
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'j' || e.key === 'J') {
        if (document.body.classList.contains('design-new')) {
          $('gdPanel').classList.remove('collapsed');
        }
      }
    });
    $('gdTeamStrip').addEventListener('click', function () {
      $('gdDock').classList.toggle('open');
      if ($('gdDock').classList.contains('open')) renderDock();
    });
    $('gdTabMembers').addEventListener('click', function () {
      S.dockView = 'members';
      $('gdTabMembers').classList.add('on');
      $('gdTabChat').classList.remove('on');
      renderDock();
    });
    $('gdTabChat').addEventListener('click', function () {
      S.dockView = 'chat';
      S.unread = 0;
      $('gdUnread').textContent = '';
      $('gdTabChat').classList.add('on');
      $('gdTabMembers').classList.remove('on');
      renderDock();
    });
    $('gdFitAll').addEventListener('click', fitGroup);
    $('gdViewAs').addEventListener('click', function () {
      S.viewAs = S.viewAs === 'member' ? 'leader' : 'member';
      $('gdViewAs').textContent = S.viewAs === 'member'
        ? '👁 Xem: thành viên' : '👑 Xem: trưởng đoàn';
      refreshPins();
      renderDock();
      H.AtriaDash.toast({
        message: S.viewAs === 'leader'
          ? 'Góc nhìn trưởng đoàn — thấy mọi thành viên (kể cả "chỉ trưởng đoàn")'
          : 'Góc nhìn thành viên — thành viên đặt riêng tư bị ẩn/mờ',
        severity: 'info',
      });
    });
    $('gdSosResolve').addEventListener('click', resolveSos);
    $('gdCallEnd').addEventListener('click', endCall);
    $('gdCallMute').addEventListener('click', function () {
      this.textContent = this.textContent === '🔇' ? '🔈' : '🔇';
    });
    $('gdPlay').addEventListener('click', function () {
      if (S.playing) pause(); else play();
    });
    $('gdEnd').addEventListener('click', endTrip);
    $('gdSpeed').addEventListener('click', function () {
      S.speed = S.speed >= 4 ? 1 : S.speed * 2;
      this.textContent = '×' + S.speed;
      if (S.playing) { clearInterval(S.timer); S.timer = setInterval(tickForward, TICK_MS / S.speed); }
    });
    $('gdScrub').addEventListener('input', function () {
      pause();
      setTick(parseInt(this.value, 10), true);
    });
    // marker CSS transitions fight Leaflet's zoom animation — suspend them
    H.map.on('zoomstart', function () { document.body.classList.remove('gd-smooth'); });
    H.map.on('zoomend', function () {
      if (S.playing) document.body.classList.add('gd-smooth');
    });
    // background-tab timer throttling would skew the clock — just pause
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) pause();
    });
  }

  window.GroupDrive = {
    loaded: true,
    hooks: null,
    init: function (hooks) {
      this.hooks = H = hooks;
      buildDom();
      wire();
      enableDrag();
      setDesign(location.hash === '#legacy' ? 'legacy' : 'new');
      welcome();
      document.documentElement.setAttribute('data-gd', 'ready');
    },
    suspend: function () { pause(); },
    resume: function () {},
  };
})();
