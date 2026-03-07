const CONTACT = {
  email: "Danahabuhalifa@gmail.com",
  phone: "+96565680561",
  instagram: "https://www.instagram.com/danahabuhalifa?fbclid=IwY2xjawQED-NleHRuA2FlbQIxMABicmlkETJ1aUpIZU5lTXNuZG5QUlE1c3J0YwZhcHBfaWQQMjIyMDM5MTc4ODIwMDg5MgABHlCH7g6wZGnIx0IDpSMBTQrfjc_4k3ayRuk0Watt-edFAbk1TEIFe3HUa6L4_aem_r9f5gyDDkSSFROG0DuXngQ",
  facebook: "https://www.facebook.com/share/18Kqdw7vME/",
  location: "Kuwait",
};

const ICONS = {
  mail: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1zm0 2v.6l8 4.8 8-4.8V8l-8 4.8L4 8z"/></svg>',
  phone: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6.6 10.8a15.7 15.7 0 0 0 6.6 6.6l2.2-2.2a1 1 0 0 1 1-.24c1.06.34 2.2.52 3.36.52a1 1 0 0 1 1 1V20a1 1 0 0 1-1 1C11.16 21 3 12.84 3 2a1 1 0 0 1 1-1h3.54a1 1 0 0 1 1 1c0 1.16.18 2.3.52 3.36a1 1 0 0 1-.24 1L6.6 8.58z"/></svg>',
  pin: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2a7 7 0 0 1 7 7c0 4.8-7 13-7 13S5 13.8 5 9a7 7 0 0 1 7-7zm0 9.5A2.5 2.5 0 1 0 12 6a2.5 2.5 0 0 0 0 5.5z"/></svg>',
  instagram: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 2h10a5 5 0 0 1 5 5v10a5 5 0 0 1-5 5H7a5 5 0 0 1-5-5V7a5 5 0 0 1 5-5zm0 2a3 3 0 0 0-3 3v10a3 3 0 0 0 3 3h10a3 3 0 0 0 3-3V7a3 3 0 0 0-3-3zm5 3.2A4.8 4.8 0 1 1 7.2 12 4.8 4.8 0 0 1 12 7.2zm0 2A2.8 2.8 0 1 0 14.8 12 2.8 2.8 0 0 0 12 9.2zm5.2-2.3a1.1 1.1 0 1 1-1.1 1.1 1.1 1.1 0 0 1 1.1-1.1z"/></svg>',
  facebook: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M13.5 22v-8h2.7l.5-3h-3.2V9.2c0-.9.3-1.6 1.7-1.6h1.7V4.9A22.5 22.5 0 0 0 16 4c-2.6 0-4.3 1.6-4.3 4.5V11H9v3h2.7v8z"/></svg>',
};

const USER_SETTINGS_KEY = "dana_user_dashboard_settings_v1";
const USER_ROUTINE_KEY = "dana_user_routine_v1";
const USER_PROFILE_KEY = "dana_user_profile_v1";
const DEVICE_CONTROL_KEY = "dana_device_controls_v1";
const DEVICE_STATUS_ONLINE_MS = 30 * 1000;
const DEVICE_STATUS_STALE_MS = 5 * 60 * 1000;

async function apiFetch(url, options = {}) {
  const merged = {
    credentials: "include",
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  };
  return fetch(url, merged);
}

async function hydrateSpotifyPlaybackStatus(preferred = "") {
  const playbackStatus = document.getElementById("spotify-playback-status");
  if (!playbackStatus) return;
  if (preferred) {
    playbackStatus.textContent = preferred;
    return;
  }
  try {
    const res = await spotifyPlaybackStatus();
    if (res.status === 401) {
      redirectToLogin("user");
      return;
    }
    if (!res.ok) {
      playbackStatus.textContent = "Playback status unavailable right now.";
      return;
    }
    const payload = await res.json().catch(() => ({}));
    if (!payload?.connected) {
      playbackStatus.textContent = "Connect Spotify to control playback.";
      return;
    }
    const track = String(payload?.track_name || "").trim();
    const artist = String(payload?.artist || "").trim();
    const mode = payload?.is_playing ? "Playing" : "Paused";
    if (!track) {
      playbackStatus.textContent = `${mode}. No active track reported.`;
      return;
    }
    playbackStatus.textContent = `${mode}: ${track}${artist ? ` - ${artist}` : ""}`;
  } catch (_err) {
    playbackStatus.textContent = "Playback status unavailable right now.";
  }
}

function readLocalState(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch (_err) {
    return fallback;
  }
}

function writeLocalState(key, payload) {
  try {
    localStorage.setItem(key, JSON.stringify(payload));
  } catch (_err) {
    // Ignore localStorage errors.
  }
}

function redirectToLogin(role = "user") {
  const next = encodeURIComponent(location.pathname || "/user-dashboard");
  location.href = `/login?role=${role}&next=${next}`;
}

function setContactStrip() {
  const target = document.getElementById("contact-strip");
  if (!target) return;
  target.innerHTML = `
    <span class="contact-item"><span class="contact-icon icon-svg">${ICONS.mail}</span><a href="mailto:${CONTACT.email}">${CONTACT.email}</a></span>
    <span class="contact-item"><span class="contact-icon icon-svg">${ICONS.phone}</span>${CONTACT.phone}</span>
    <span class="contact-item"><span class="contact-icon icon-svg">${ICONS.pin}</span>${CONTACT.location}</span>
    <a class="contact-item contact-link" href="${CONTACT.instagram}" target="_blank" rel="noreferrer"><span class="contact-icon icon-svg">${ICONS.instagram}</span>Instagram</a>
    <a class="contact-item contact-link" href="${CONTACT.facebook}" target="_blank" rel="noreferrer"><span class="contact-icon icon-svg">${ICONS.facebook}</span>Facebook</a>
  `;
}

function initCinematicSheen() {
  document.body.classList.add("app-sheen");
  window.setTimeout(() => document.body.classList.remove("app-sheen"), 1400);
}

function setMetricLoading(elements, loading) {
  elements.forEach((el) => {
    if (!el) return;
    el.classList.toggle("is-loading", loading);
    if (loading) {
      el.dataset.prevValue = el.textContent;
      el.textContent = "...";
    } else if (el.dataset.prevValue && el.textContent === "...") {
      el.textContent = el.dataset.prevValue;
    }
  });
}

function renderSleepInsights(settings) {
  const style = String(settings?.response_style || "balanced");
  const engagement = String(settings?.engagement_level || "high");
  const windDown = Number(settings?.wind_down_minutes || 45);
  const partnerOn = Boolean(settings?.partner_mode_enabled);

  const base = style === "coaching" ? 72 : style === "calm" ? 69 : 74;
  const lift = engagement === "high" ? 6 : engagement === "medium" ? 3 : 1;
  const weekendMod = partnerOn ? 2 : 0;
  const bars = [
    base - 7,
    base - 2,
    base - 9,
    base + 1,
    base + lift,
    base - 1 + weekendMod,
    base + 2 + weekendMod,
  ];

  bars.forEach((value, idx) => {
    const bar = document.getElementById(`insight-bar-${idx + 1}`);
    if (!bar) return;
    bar.style.height = `${Math.max(25, Math.min(98, value))}%`;
  });

  const duration = document.getElementById("insight-duration");
  const consistency = document.getElementById("insight-consistency");
  const wakes = document.getElementById("insight-wakes");

  if (duration) {
    duration.className = `status ${windDown <= 50 ? "good" : "warn"}`;
    duration.textContent = windDown <= 50 ? "Strong" : "Inconsistent";
  }
  if (consistency) {
    const quality = style === "balanced" ? "good" : "warn";
    consistency.className = `status ${quality}`;
    consistency.textContent = quality === "good" ? "Anchored" : "Needs anchor";
  }
  if (wakes) {
    const wakeClass = partnerOn ? "good" : "warn";
    wakes.className = `status ${wakeClass}`;
    wakes.textContent = partnerOn ? "Low" : "Moderate";
  }
}

function parseIsoToMs(value) {
  const raw = String(value || "").trim();
  if (!raw) return null;
  const parsed = Date.parse(raw);
  if (!Number.isFinite(parsed)) return null;
  return parsed;
}

function formatRelativeAge(ageMs) {
  if (!Number.isFinite(ageMs)) return "Unknown";
  const safeAge = Math.max(0, ageMs);
  if (safeAge < 1000) return "just now";
  if (safeAge < 60 * 1000) return `${Math.floor(safeAge / 1000)} sec ago`;
  if (safeAge < 60 * 60 * 1000) return `${Math.floor(safeAge / (60 * 1000))} min ago`;
  if (safeAge < 24 * 60 * 60 * 1000) return `${Math.floor(safeAge / (60 * 60 * 1000))} hr ago`;
  return `${Math.floor(safeAge / (24 * 60 * 60 * 1000))} day ago`;
}

function formatUpdatedAt(updatedAt) {
  const parsedMs = parseIsoToMs(updatedAt);
  if (parsedMs === null) return "Unknown";
  const relative = formatRelativeAge(Date.now() - parsedMs);
  const absolute = new Date(parsedMs).toLocaleString();
  return `${relative} (${absolute})`;
}

function normalizeDeviceSource(source) {
  const raw = String(source || "").trim();
  if (!raw) return "Unknown";
  return raw.replace(/_/g, " ");
}

function mapDeviceStatus(statePayload) {
  const updatedAt = String(statePayload?.updated_at || "").trim();
  const parsedMs = parseIsoToMs(updatedAt);
  const stale = Boolean(statePayload?.stale);
  const deviceOnline = Boolean(statePayload?.device_online);
  const source = normalizeDeviceSource(statePayload?.source);

  let statusKey = "offline";
  if (parsedMs !== null) {
    const ageMs = Math.max(0, Date.now() - parsedMs);
    if (ageMs < DEVICE_STATUS_ONLINE_MS) {
      statusKey = "online";
    } else if (ageMs <= DEVICE_STATUS_STALE_MS) {
      statusKey = "stale";
    } else {
      statusKey = "offline";
    }
  } else if (deviceOnline) {
    statusKey = "online";
  } else if (stale) {
    statusKey = "stale";
  }

  const label = statusKey === "online" ? "Online" : statusKey === "stale" ? "Stale" : "Offline";
  return {
    statusKey,
    label,
    source,
    deviceOnline,
    lastUpdatedText: formatUpdatedAt(updatedAt),
  };
}

function bindDeviceStatusDiagnostics() {
  const trigger = document.getElementById("device-status-trigger");
  const diagnostics = document.getElementById("device-status-diagnostics");
  if (!trigger || !diagnostics) return;
  if (trigger.dataset.bound === "1") return;
  trigger.dataset.bound = "1";
  trigger.addEventListener("click", () => {
    const expanded = trigger.getAttribute("aria-expanded") === "true";
    trigger.setAttribute("aria-expanded", expanded ? "false" : "true");
    diagnostics.hidden = expanded;
  });
}

function renderDeviceStatus(meta) {
  const trigger = document.getElementById("device-status-trigger");
  const statusText = document.getElementById("device-status-text");
  const diagLabel = document.getElementById("device-status-diag-label");
  const diagUpdated = document.getElementById("device-status-diag-updated");
  const diagSource = document.getElementById("device-status-diag-source");
  const diagOnline = document.getElementById("device-status-diag-online");
  if (!trigger || !statusText || !diagLabel || !diagUpdated || !diagSource || !diagOnline) return;

  trigger.classList.remove("device-status-online", "device-status-stale", "device-status-offline");
  trigger.classList.add(`device-status-${meta.statusKey}`);
  statusText.textContent = `Device ${meta.label.toLowerCase()} - tap for diagnostics`;

  diagLabel.textContent = meta.label;
  diagUpdated.textContent = meta.lastUpdatedText;
  diagSource.textContent = meta.source;
  diagOnline.textContent = meta.deviceOnline ? "Yes" : "No";
}

async function hydrateDeviceStatusIndicator() {
  if (!location.pathname.includes("user-dashboard")) return;
  bindDeviceStatusDiagnostics();

  let payload = {};
  try {
    const res = await loadBedStateFromApi();
    if (res.status === 401) {
      redirectToLogin("user");
      return;
    }
    if (res.ok) {
      payload = await res.json().catch(() => ({}));
    }
  } catch (_err) {
    payload = {};
  }

  renderDeviceStatus(mapDeviceStatus(payload));
}

async function initRoutinePlanner(defaults) {
  const form = document.getElementById("routine-form");
  if (!form || !location.pathname.includes("user-dashboard")) return;

  const bedtime = document.getElementById("routine-bedtime");
  const wake = document.getElementById("routine-wake");
  const weekends = document.getElementById("routine-weekends");
  const status = document.getElementById("routine-status");
  const reset = document.getElementById("routine-reset");
  if (!bedtime || !wake || !weekends || !status || !reset) return;

  const baseline = {
    bedtime: String(defaults?.bedtime || "22:30"),
    wake: String(defaults?.wake || "07:00"),
    weekends: Boolean(defaults?.weekends ?? true),
  };
  let active = { ...baseline };
  try {
    const res = await loadRoutineFromApi();
    if (res.status === 401) {
      redirectToLogin("user");
      return;
    }
    if (res.ok) {
      const payload = await res.json().catch(() => ({}));
      active = { ...active, ...(payload?.routine || {}) };
    } else {
      active = { ...active, ...readLocalState(USER_ROUTINE_KEY, baseline) };
    }
  } catch (_err) {
    active = { ...active, ...readLocalState(USER_ROUTINE_KEY, baseline) };
  }

  bedtime.value = String(active?.bedtime || baseline.bedtime);
  wake.value = String(active?.wake || baseline.wake);
  weekends.checked = Boolean(active?.weekends ?? baseline.weekends);

  form.onsubmit = async (evt) => {
    evt.preventDefault();
    const next = {
      bedtime: String(bedtime.value || baseline.bedtime),
      wake: String(wake.value || baseline.wake),
      weekends: weekends.checked,
    };
    status.textContent = "Saving routine...";
    try {
      const res = await persistRoutineToApi(next);
      if (res.status === 401) {
        redirectToLogin("user");
        return;
      }
      if (!res.ok) {
        writeLocalState(USER_ROUTINE_KEY, next);
        status.textContent = "Routine saved locally on this browser.";
        return;
      }
      const payload = await res.json().catch(() => ({}));
      const saved = payload?.routine || next;
      writeLocalState(USER_ROUTINE_KEY, saved);
      status.textContent = `Routine saved: ${saved.bedtime} to ${saved.wake}${saved.weekends ? " (weekends included)" : ""}.`;
    } catch (_err) {
      writeLocalState(USER_ROUTINE_KEY, next);
      status.textContent = "Network issue: routine saved locally.";
    }
  };

  reset.onclick = async () => {
    status.textContent = "Resetting routine...";
    try {
      const res = await persistRoutineToApi(baseline);
      if (res.status === 401) {
        redirectToLogin("user");
        return;
      }
      if (!res.ok) {
        writeLocalState(USER_ROUTINE_KEY, baseline);
        bedtime.value = baseline.bedtime;
        wake.value = baseline.wake;
        weekends.checked = baseline.weekends;
        status.textContent = "Routine reset locally.";
        return;
      }
      writeLocalState(USER_ROUTINE_KEY, baseline);
      bedtime.value = baseline.bedtime;
      wake.value = baseline.wake;
      weekends.checked = baseline.weekends;
      status.textContent = "Routine reset to recommended defaults.";
    } catch (_err) {
      writeLocalState(USER_ROUTINE_KEY, baseline);
      bedtime.value = baseline.bedtime;
      wake.value = baseline.wake;
      weekends.checked = baseline.weekends;
      status.textContent = "Network issue: routine reset locally.";
    }
  };
}

async function initProfilePanel(baseProfile) {
  const form = document.getElementById("profile-form");
  if (!form || !location.pathname.includes("user-dashboard")) return;

  const displayName = document.getElementById("profile-display-name");
  const timezone = document.getElementById("profile-timezone");
  const push = document.getElementById("profile-push");
  const email = document.getElementById("profile-email");
  const status = document.getElementById("profile-status");
  if (!displayName || !timezone || !push || !email || !status) return;

  const baseline = {
    display_name: String(baseProfile?.display_name || "User"),
    timezone: String(baseProfile?.timezone || "Asia/Kuwait"),
    push_enabled: Boolean(baseProfile?.push_enabled ?? true),
    email_enabled: Boolean(baseProfile?.email_enabled ?? false),
  };
  let active = { ...baseline };
  try {
    const res = await loadProfileFromApi();
    if (res.status === 401) {
      redirectToLogin("user");
      return;
    }
    if (res.ok) {
      const payload = await res.json().catch(() => ({}));
      active = { ...active, ...(payload?.profile || {}) };
    } else {
      active = { ...active, ...readLocalState(USER_PROFILE_KEY, baseline) };
    }
  } catch (_err) {
    active = { ...active, ...readLocalState(USER_PROFILE_KEY, baseline) };
  }

  displayName.value = String(active?.display_name || baseline.display_name);
  timezone.value = String(active?.timezone || baseline.timezone);
  push.checked = Boolean(active?.push_enabled ?? baseline.push_enabled);
  email.checked = Boolean(active?.email_enabled ?? baseline.email_enabled);

  form.onsubmit = async (evt) => {
    evt.preventDefault();
    status.textContent = "Saving profile...";
    const next = {
      display_name: String(displayName.value || baseline.display_name),
      timezone: String(timezone.value || baseline.timezone),
      push_enabled: push.checked,
      email_enabled: email.checked,
    };

    try {
      const res = await persistProfileToApi(next);
      if (res.status === 401) {
        redirectToLogin("user");
        return;
      }
      const payload = res.ok ? await res.json().catch(() => ({})) : {};
      const saved = res.ok ? (payload?.profile || next) : next;
      writeLocalState(USER_PROFILE_KEY, saved);
      const sessionUser = document.getElementById("session-user");
      if (sessionUser) sessionUser.textContent = saved.display_name;
      status.textContent = res.ok ? "Profile updated." : "Profile saved locally on this browser.";
    } catch (_err) {
      writeLocalState(USER_PROFILE_KEY, next);
      const sessionUser = document.getElementById("session-user");
      if (sessionUser) sessionUser.textContent = next.display_name;
      status.textContent = "Network issue: profile saved locally.";
    }
  };
}

async function initDeviceControls() {
  const lightsBtn = document.getElementById("device-toggle-lights");
  const audioBtn = document.getElementById("device-toggle-audio");
  const alarmBtn = document.getElementById("device-toggle-alarm");
  const lightLevel = document.getElementById("device-light-level");
  const status = document.getElementById("device-control-status");
  if (!lightsBtn || !audioBtn || !alarmBtn || !lightLevel || !status) return;

  const baseline = {
    lights_on: false,
    audio_on: false,
    alarm_on: true,
    light_level: 65,
  };
  const state = { ...baseline };
  try {
    const res = await loadDeviceControlsFromApi();
    if (res.status === 401) {
      redirectToLogin("user");
      return;
    }
    if (res.ok) {
      const payload = await res.json().catch(() => ({}));
      Object.assign(state, payload?.controls || {});
    } else {
      Object.assign(state, readLocalState(DEVICE_CONTROL_KEY, baseline));
    }
  } catch (_err) {
    Object.assign(state, readLocalState(DEVICE_CONTROL_KEY, baseline));
  }

  const syncUi = () => {
    lightsBtn.textContent = state.lights_on ? "Turn Off" : "Turn On";
    audioBtn.textContent = state.audio_on ? "Pause" : "Play";
    alarmBtn.textContent = state.alarm_on ? "Disable" : "Enable";
    lightLevel.value = String(state.light_level);
    status.textContent = `Lights ${state.lights_on ? "on" : "off"}, audio ${state.audio_on ? "playing" : "paused"}, alarm ${state.alarm_on ? "enabled" : "disabled"}.`;
  };

  const persist = async () => {
    writeLocalState(DEVICE_CONTROL_KEY, state);
    try {
      await persistDeviceControlsToApi(state);
    } catch (_err) {
      // keep local fallback silently
    }
  };

  lightsBtn.onclick = () => {
    state.lights_on = !state.lights_on;
    persist();
    syncUi();
  };
  audioBtn.onclick = () => {
    state.audio_on = !state.audio_on;
    persist();
    syncUi();
  };
  alarmBtn.onclick = () => {
    state.alarm_on = !state.alarm_on;
    persist();
    syncUi();
  };
  lightLevel.oninput = () => {
    state.light_level = Number(lightLevel.value || 65);
    persist();
    syncUi();
  };

  syncUi();
}

function readSpotifyCallbackFlag() {
  const params = new URLSearchParams(location.search || "");
  const state = String(params.get("spotify") || "").toLowerCase();
  const reason = String(params.get("reason") || "");
  const missing = String(params.get("missing") || "");
  const detail = String(params.get("detail") || "");
  if (!state) return { state: "", reason: "", missing: "", detail: "" };

  params.delete("spotify");
  params.delete("reason");
  params.delete("missing");
  params.delete("detail");
  const nextQuery = params.toString();
  const nextUrl = `${location.pathname}${nextQuery ? `?${nextQuery}` : ""}${location.hash || ""}`;
  window.history.replaceState({}, "", nextUrl);
  return { state, reason, missing, detail };
}

async function hydrateSpotifyConnectStatus(preferredMessage = "") {
  const status = document.getElementById("spotify-connect-status");
  const connectBtn = document.getElementById("spotify-connect-btn");
  const disconnectBtn = document.getElementById("spotify-disconnect-btn");
  if (!status || !connectBtn || !disconnectBtn) return;

  try {
    const res = await loadSpotifyStatusFromApi();
    if (res.status === 401) {
      redirectToLogin("user");
      return;
    }
    if (!res.ok) {
      status.textContent = preferredMessage || "Spotify status unavailable right now.";
      connectBtn.disabled = false;
      disconnectBtn.disabled = true;
      return;
    }
    const payload = await res.json().catch(() => ({}));
    const connected = Boolean(payload?.connected);
    if (connected) {
      const email = String(payload?.spotify_email || payload?.spotify_user_id || "Connected account");
      status.textContent = preferredMessage || `Connected to Spotify: ${email}`;
      connectBtn.disabled = false;
      connectBtn.textContent = "Reconnect Spotify";
      disconnectBtn.disabled = false;
      return;
    }
    status.textContent = preferredMessage || "Spotify not connected.";
    connectBtn.disabled = false;
    connectBtn.textContent = "Connect Spotify";
    disconnectBtn.disabled = true;
  } catch (_err) {
    status.textContent = preferredMessage || "Spotify status unavailable right now.";
    connectBtn.disabled = false;
    connectBtn.textContent = "Connect Spotify";
    disconnectBtn.disabled = true;
  }
}

async function initSpotifyConnect() {
  if (!location.pathname.includes("user-dashboard")) return;
  const connectBtn = document.getElementById("spotify-connect-btn");
  const disconnectBtn = document.getElementById("spotify-disconnect-btn");
  const status = document.getElementById("spotify-connect-status");
  const playBtn = document.getElementById("spotify-play-btn");
  const pauseBtn = document.getElementById("spotify-pause-btn");
  const nextBtn = document.getElementById("spotify-next-btn");
  const prevBtn = document.getElementById("spotify-prev-btn");
  const volumeInput = document.getElementById("spotify-volume-input");
  const volumeApplyBtn = document.getElementById("spotify-volume-apply-btn");
  if (!connectBtn || !disconnectBtn || !status) return;

  const callback = readSpotifyCallbackFlag();
  if (callback.state === "connected") {
    status.textContent = "Spotify connected successfully.";
  } else if (callback.state === "error") {
    const reasonMap = {
      oauth_not_configured: "Spotify OAuth is not configured on server yet.",
      missing_user_key: "Could not identify your account for Spotify connection.",
      missing_code_or_state: "Spotify login returned incomplete data.",
      invalid_state: "Spotify security state validation failed. Please retry.",
      token_exchange_failed: "Spotify did not return a valid access token.",
      exchange_failed: "Spotify token exchange request failed.",
    };
    const reasonKey = String(callback.reason || "").trim();
    if (reasonKey === "oauth_not_configured" && String(callback.missing || "").trim()) {
      status.textContent = `Spotify OAuth missing server vars: ${callback.missing}`;
    } else if (reasonKey === "exchange_failed" && String(callback.detail || "").trim()) {
      status.textContent = `Spotify connect failed: ${callback.detail}`;
    } else {
      status.textContent = reasonMap[reasonKey] || (reasonKey ? `Spotify connect failed: ${reasonKey}` : "Spotify connect failed.");
    }
  }

  await hydrateSpotifyConnectStatus(status.textContent);
  await hydrateSpotifyPlaybackStatus();

  if (connectBtn.dataset.bound !== "1") {
    connectBtn.dataset.bound = "1";
    connectBtn.addEventListener("click", () => {
      location.href = "/v1/mobile/spotify/connect";
    });
  }

  if (disconnectBtn.dataset.bound !== "1") {
    disconnectBtn.dataset.bound = "1";
    disconnectBtn.addEventListener("click", async () => {
      status.textContent = "Disconnecting Spotify...";
      try {
        const res = await disconnectSpotifyFromApi();
        if (res.status === 401) {
          redirectToLogin("user");
          return;
        }
      } catch (_err) {
        // Keep fallback status refresh
      }
      hydrateSpotifyConnectStatus("Spotify disconnected.");
      hydrateSpotifyPlaybackStatus("Connect Spotify to control playback.");
    });
  }

  const runPlaybackAction = async (action, extra = {}) => {
    const playbackStatus = document.getElementById("spotify-playback-status");
    if (playbackStatus) playbackStatus.textContent = "Sending command to Spotify...";
    try {
      const res = await spotifyPlaybackAction(action, extra);
      const responseTextPromise = res.clone().text().catch(() => "");
      if (res.status === 401) {
        redirectToLogin("user");
        return;
      }
      const payload = await res.json().catch(() => ({}));
      if (!res.ok) {
        const rawText = String(await responseTextPromise || "").replace(/<[^>]*>/g, " ").trim();
        hydrateSpotifyPlaybackStatus(payload?.detail || payload?.message || rawText || "Spotify command failed.");
        return;
      }
      hydrateSpotifyPlaybackStatus(payload?.message || "Spotify command sent.");
      setTimeout(() => {
        hydrateSpotifyPlaybackStatus();
      }, 700);
    } catch (_err) {
      hydrateSpotifyPlaybackStatus("Network error while sending Spotify command.");
    }
  };

  if (playBtn && playBtn.dataset.bound !== "1") {
    playBtn.dataset.bound = "1";
    playBtn.addEventListener("click", () => runPlaybackAction("play"));
  }
  if (pauseBtn && pauseBtn.dataset.bound !== "1") {
    pauseBtn.dataset.bound = "1";
    pauseBtn.addEventListener("click", () => runPlaybackAction("pause"));
  }
  if (nextBtn && nextBtn.dataset.bound !== "1") {
    nextBtn.dataset.bound = "1";
    nextBtn.addEventListener("click", () => runPlaybackAction("next"));
  }
  if (prevBtn && prevBtn.dataset.bound !== "1") {
    prevBtn.dataset.bound = "1";
    prevBtn.addEventListener("click", () => runPlaybackAction("previous"));
  }
  if (volumeApplyBtn && volumeInput && volumeApplyBtn.dataset.bound !== "1") {
    volumeApplyBtn.dataset.bound = "1";
    volumeApplyBtn.addEventListener("click", () => {
      const vol = Number(volumeInput.value || 45);
      runPlaybackAction("set_volume", { volume_percent: vol });
    });
  }
}

function bindLogoutAction() {
  const logout = document.getElementById("logout-btn");
  if (!logout) return;

  logout.addEventListener("click", async () => {
    try {
      await apiFetch("/v1/auth/logout", { method: "POST" });
    } catch (_err) {
      // Ignore network errors and continue logout redirect.
    }
    location.href = "/login";
  });
}

async function hydrateSessionIdentity() {
  const roleTag = document.getElementById("session-role");
  const userName = document.getElementById("session-user");

  if (location.pathname.includes("admin")) {
    try {
      const res = await apiFetch("/v1/admin/auth/me");
      if (res.status === 401) {
        redirectToLogin("admin");
        return;
      }
      if (!res.ok) return;
      const payload = await res.json();
      const admin = payload?.admin || {};
      if (roleTag) roleTag.textContent = `Role: ${String(admin?.role || "admin")}`;
      if (userName) userName.textContent = String(admin?.email || "admin");
    } catch (_err) {
      // Keep fallback content.
    }
    return;
  }

  if (location.pathname.includes("user-dashboard")) {
    try {
      const res = await apiFetch("/v1/auth/me");
      if (res.status === 401) {
        redirectToLogin("user");
        return;
      }
      if (!res.ok) return;
      const payload = await res.json();
      const user = payload?.user || {};
      if (roleTag) roleTag.textContent = "Role: User";
      if (userName) userName.textContent = String(user?.name || user?.email || "User");
    } catch (_err) {
      // Keep fallback content.
    }
  }
}

function readQueryParam(key) {
  const params = new URLSearchParams(location.search || "");
  return params.get(key) || "";
}

function initLoginPage() {
  const mode = readQueryParam("role").toLowerCase() === "admin" ? "admin" : "user";
  const nextUrl = readQueryParam("next") || (mode === "admin" ? "/admin-panel" : "/user-dashboard");

  const title = document.getElementById("login-mode-title");
  const form = document.getElementById("login-form");
  const registerForm = document.getElementById("register-form");
  const switchBtn = document.getElementById("switch-role-btn");
  const status = document.getElementById("auth-status");
  if (!form || !registerForm || !title || !switchBtn || !status) return;

  title.textContent = mode === "admin" ? "Admin Login" : "User Login";
  switchBtn.textContent = mode === "admin" ? "Switch to User Login" : "Switch to Admin Login";
  switchBtn.onclick = () => {
    const targetRole = mode === "admin" ? "user" : "admin";
    location.href = `/login?role=${targetRole}&next=${encodeURIComponent(nextUrl)}`;
  };

  form.addEventListener("submit", async (evt) => {
    evt.preventDefault();
    const email = document.getElementById("auth-email")?.value?.trim() || "";
    const password = document.getElementById("auth-password")?.value || "";
    status.textContent = "Signing in...";

    try {
      const endpoint = mode === "admin" ? "/v1/admin/auth/login" : "/v1/auth/login";
      const res = await apiFetch(endpoint, {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        status.textContent = err?.detail || "Login failed.";
        return;
      }
      location.href = nextUrl;
    } catch (_err) {
      status.textContent = "Login failed due to network error.";
    }
  });

  registerForm.addEventListener("submit", async (evt) => {
    evt.preventDefault();
    if (mode === "admin") {
      status.textContent = "Admin accounts must be registered as users first.";
      return;
    }
    const name = document.getElementById("reg-name")?.value?.trim() || "";
    const email = document.getElementById("reg-email")?.value?.trim() || "";
    const password = document.getElementById("reg-password")?.value || "";
    status.textContent = "Creating account...";

    try {
      const res = await apiFetch("/v1/auth/register", {
        method: "POST",
        body: JSON.stringify({ name, email, password }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        status.textContent = err?.detail || "Registration failed.";
        return;
      }
      location.href = "/user-dashboard";
    } catch (_err) {
      status.textContent = "Registration failed due to network error.";
    }
  });
}

function initChatWidget() {
  const toggle = document.getElementById("chat-toggle");
  const panel = document.getElementById("chat-panel");
  const input = document.getElementById("chat-input");
  const send = document.getElementById("chat-send");
  const log = document.getElementById("chat-log");

  if (!toggle || !panel || !input || !send || !log) return;

  toggle.addEventListener("click", () => {
    panel.classList.toggle("open");
  });

  const appendBubble = (text, type) => {
    const item = document.createElement("div");
    item.className = `bubble ${type}`;
    item.textContent = text;
    log.appendChild(item);
    log.scrollTop = log.scrollHeight;
  };

  const sendMessage = async () => {
    const message = input.value.trim();
    if (!message) return;
    input.value = "";
    appendBubble(message, "user");

    try {
      const response = await apiFetch("/v1/ai/chat", {
        method: "POST",
        body: JSON.stringify({ message }),
      });

      if (response.status === 401) {
        appendBubble("Session expired. Please login again.", "bot");
        setTimeout(() => redirectToLogin("user"), 600);
        return;
      }

      if (!response.ok) {
        appendBubble("Chat service is unavailable right now.", "bot");
        return;
      }

      const payload = await response.json();
      const reply = payload?.reply || payload?.text || "I am here. Try again.";
      appendBubble(reply, "bot");
    } catch (_err) {
      appendBubble("Could not reach AI service. Check backend URL/network.", "bot");
    }
  };

  const chips = panel.querySelectorAll(".chat-chip");
  chips.forEach((chip) => {
    chip.addEventListener("click", () => {
      const prompt = String(chip.dataset.prompt || "").trim();
      if (!prompt) return;
      input.value = prompt;
      sendMessage();
    });
  });

  send.addEventListener("click", sendMessage);
  input.addEventListener("keydown", (evt) => {
    if (evt.key === "Enter") sendMessage();
  });
}

function activateNavButtons() {
  const links = document.querySelectorAll(".nav-link");
  links.forEach((link) => {
    if (link.dataset.href === location.pathname.split("/").pop()) {
      link.classList.add("active");
    }
    link.addEventListener("click", () => {
      if (link.dataset.href) {
        location.href = link.dataset.href;
      }
    });
  });
}

function readUserSettings() {
  try {
    const raw = localStorage.getItem(USER_SETTINGS_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (_err) {
    return null;
  }
}

function writeUserSettings(payload) {
  try {
    localStorage.setItem(USER_SETTINGS_KEY, JSON.stringify(payload));
  } catch (_err) {
    // Ignore localStorage errors.
  }
}

async function loadRoutineFromApi() {
  const res = await apiFetch("/v1/mobile/routine");
  return res;
}

async function persistRoutineToApi(payload) {
  const res = await apiFetch("/v1/mobile/routine", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return res;
}

async function loadProfileFromApi() {
  const res = await apiFetch("/v1/mobile/profile");
  return res;
}

async function persistProfileToApi(payload) {
  const res = await apiFetch("/v1/mobile/profile", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return res;
}

async function loadDeviceControlsFromApi() {
  const res = await apiFetch("/v1/mobile/device-controls");
  return res;
}

async function loadBedStateFromApi() {
  const res = await apiFetch("/v2/bed/state");
  return res;
}

async function persistDeviceControlsToApi(payload) {
  const res = await apiFetch("/v1/mobile/device-controls", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return res;
}

async function loadUserTimelineFromApi() {
  const res = await apiFetch("/v1/mobile/timeline");
  return res;
}

async function triggerUserAction(action) {
  const res = await apiFetch("/v1/mobile/user-actions", {
    method: "POST",
    body: JSON.stringify({ action }),
  });
  return res;
}

async function submitDeviceCommand(action) {
  const res = await apiFetch("/v1/mobile/device-commands", {
    method: "POST",
    body: JSON.stringify({ action }),
  });
  return res;
}

async function readDeviceCommandStatus(commandId) {
  const res = await apiFetch(`/v1/mobile/device-commands/${encodeURIComponent(commandId)}`);
  return res;
}

async function loadSpotifyStatusFromApi() {
  const res = await apiFetch("/v1/mobile/spotify/status");
  return res;
}

async function disconnectSpotifyFromApi() {
  const res = await apiFetch("/v1/mobile/spotify/disconnect", { method: "POST" });
  return res;
}

async function spotifyPlaybackAction(action, payload = {}) {
  const res = await apiFetch("/v1/mobile/spotify/playback", {
    method: "POST",
    body: JSON.stringify({ action, ...payload }),
  });
  return res;
}

async function spotifyPlaybackStatus() {
  const res = await apiFetch("/v1/mobile/spotify/playback-status");
  return res;
}

async function persistUserSettings(payload) {
  const res = await apiFetch("/v1/mobile/settings", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return res;
}

function buildFocusPlan(settings) {
  const safe = settings || {};
  const windDown = Number(safe.wind_down_minutes || 45);
  const partnerOn = Boolean(safe.partner_mode_enabled);
  const style = String(safe.response_style || "balanced");
  const engagement = String(safe.engagement_level || "high");
  const lines = [
    `Start wind-down autopilot ${windDown} minutes before bedtime.`,
    partnerOn
      ? "Use partner-safe routine mode to avoid late-night trigger conflicts."
      : "Keep personal routine mode on and add partner-safe mode only when needed.",
    style === "coaching"
      ? "Enable coaching cues in chat for stronger bedtime accountability."
      : "Keep assistant tone calm and practical for night-time guidance.",
    engagement === "high"
      ? "Use proactive alerts to catch drift early."
      : "Use quieter reminders and manual check-ins from the AI chat.",
  ];
  return lines;
}

function renderFocusPlan(settings) {
  const plan = document.getElementById("focus-plan");
  if (!plan) return;
  plan.innerHTML = "";
  buildFocusPlan(settings).forEach((line) => {
    const li = document.createElement("li");
    li.textContent = line;
    plan.appendChild(li);
  });
}

function applyUserSettingsToForm(settings) {
  const styleSelect = document.getElementById("setting-response-style");
  const engagementSelect = document.getElementById("setting-engagement-level");
  const windDownInput = document.getElementById("setting-wind-down");
  const partnerMode = document.getElementById("setting-partner-mode");
  if (!styleSelect || !engagementSelect || !windDownInput || !partnerMode) return;

  styleSelect.value = String(settings.response_style || "balanced");
  engagementSelect.value = String(settings.engagement_level || "high");
  windDownInput.value = String(settings.wind_down_minutes || 45);
  partnerMode.checked = Boolean(settings.partner_mode_enabled);
}

function applyUserSettingsToMetrics(settings) {
  const styleMetric = document.getElementById("metric-style");
  const windDownMetric = document.getElementById("metric-winddown");
  const partnerMetric = document.getElementById("metric-partner");
  const consistency = document.getElementById("metric-consistency");
  const consistencyBar = document.getElementById("metric-consistency-bar");
  const recovery = document.getElementById("metric-recovery");

  const style = String(settings.response_style || "balanced");
  const engagement = String(settings.engagement_level || "high");
  const windDown = Number(settings.wind_down_minutes || 45);

  if (styleMetric) styleMetric.textContent = style;
  if (windDownMetric) windDownMetric.textContent = `${windDown} min`;
  if (partnerMetric) partnerMetric.textContent = settings.partner_mode_enabled ? "ON" : "OFF";
  if (recovery) recovery.textContent = engagement === "high" ? "84/100" : engagement === "medium" ? "80/100" : "76/100";

  const consistencyScore = style === "balanced" ? 76 : style === "coaching" ? 79 : 73;
  if (consistency) consistency.textContent = `${consistencyScore}%`;
  if (consistencyBar) consistencyBar.style.width = `${consistencyScore}%`;
}

function initUserSettingsPanel(baseSettings) {
  const form = document.getElementById("user-settings-form");
  if (!form || !location.pathname.includes("user-dashboard")) return;
  const status = document.getElementById("settings-status");
  const reset = document.getElementById("settings-reset");
  const styleSelect = document.getElementById("setting-response-style");
  const engagementSelect = document.getElementById("setting-engagement-level");
  const windDownInput = document.getElementById("setting-wind-down");
  const partnerMode = document.getElementById("setting-partner-mode");
  if (!status || !reset || !styleSelect || !engagementSelect || !windDownInput || !partnerMode) return;

  const defaults = {
    response_style: String(baseSettings?.response_style || "balanced"),
    engagement_level: String(baseSettings?.engagement_level || "high"),
    wind_down_minutes: Number(baseSettings?.wind_down_minutes || 45),
    partner_mode_enabled: Boolean(baseSettings?.partner_mode_enabled),
  };
  const active = { ...defaults };

  applyUserSettingsToForm(active);
  applyUserSettingsToMetrics(active);
  renderFocusPlan(active);

  form.onsubmit = async (evt) => {
    evt.preventDefault();
    status.textContent = "Saving preferences...";
    const next = {
      response_style: styleSelect.value,
      engagement_level: engagementSelect.value,
      wind_down_minutes: Math.max(15, Math.min(120, Number(windDownInput.value || 45))),
      partner_mode_enabled: partnerMode.checked,
    };

    try {
      const res = await persistUserSettings(next);
      if (res.status === 401) {
        redirectToLogin("user");
        return;
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        status.textContent = err?.detail || "Could not save to account right now.";
        return;
      }
      const payload = await res.json().catch(() => ({}));
      const saved = payload?.settings || next;
      writeUserSettings(saved);
      applyUserSettingsToMetrics(saved);
      renderFocusPlan(saved);
      status.textContent = "Preferences saved to your account.";
    } catch (_err) {
      writeUserSettings(next);
      applyUserSettingsToMetrics(next);
      renderFocusPlan(next);
      status.textContent = "Network issue: saved locally on this browser.";
    }
  };

  reset.onclick = async () => {
    localStorage.removeItem(USER_SETTINGS_KEY);
    status.textContent = "Resetting preferences...";
    try {
      const res = await persistUserSettings(defaults);
      if (res.status === 401) {
        redirectToLogin("user");
        return;
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        status.textContent = err?.detail || "Could not reset account settings right now.";
        return;
      }
      applyUserSettingsToForm(defaults);
      applyUserSettingsToMetrics(defaults);
      renderFocusPlan(defaults);
      status.textContent = "Preferences reset to profile defaults.";
    } catch (_err) {
      applyUserSettingsToForm(defaults);
      applyUserSettingsToMetrics(defaults);
      renderFocusPlan(defaults);
      status.textContent = "Network issue: reset locally to defaults.";
    }
  };
}

async function hydrateUserDashboard() {
  const recovery = document.getElementById("metric-recovery");
  const consistency = document.getElementById("metric-consistency");
  const health = document.getElementById("metric-health");
  const partner = document.getElementById("metric-partner");
  const consistencyBar = document.getElementById("metric-consistency-bar");
  const winddown = document.getElementById("metric-winddown");
  const style = document.getElementById("metric-style");
  const locationMetric = document.getElementById("metric-location");
  if (!recovery || !consistency || !health || !partner) return;
  setMetricLoading([recovery, consistency, health, partner, winddown, style, locationMetric], true);
  await hydrateDeviceStatusIndicator();

  try {
    const dashboardRes = await apiFetch("/v1/mobile/dashboard");
    if (dashboardRes.status === 401) {
      redirectToLogin("user");
      return;
    }
    if (!dashboardRes.ok) return;
    const dashboard = await dashboardRes.json();

    const defaults = {
      response_style: String(dashboard?.response_style || "balanced"),
      engagement_level: String(dashboard?.engagement_level || "high"),
      wind_down_minutes: Number(dashboard?.wind_down_minutes || 45),
      partner_mode_enabled: Boolean(dashboard?.partner_mode_enabled),
    };

    applyUserSettingsToMetrics(defaults);
    renderSleepInsights(defaults);
    health.textContent = "7 / 7";
    if (locationMetric) locationMetric.textContent = String(dashboard?.location || "Kuwait");
    initUserSettingsPanel(defaults);
    await initRoutinePlanner({ bedtime: "22:30", wake: "07:00", weekends: true });
    await initProfilePanel({
      display_name: String(document.getElementById("session-user")?.textContent || dashboard?.name || "User"),
      timezone: "Asia/Kuwait",
      push_enabled: true,
      email_enabled: false,
    });
    await initDeviceControls();
    await initSpotifyConnect();
    await hydrateUserTimeline();
    bindUserActions();
    if (consistencyBar && !consistencyBar.style.width) consistencyBar.style.width = "76%";
  } catch (_err) {
    // Keep default placeholder values on network failures.
    const fallback = {
      response_style: "balanced",
      engagement_level: "high",
      wind_down_minutes: 45,
      partner_mode_enabled: false,
    };
    initUserSettingsPanel(fallback);
    renderSleepInsights(fallback);
    await initRoutinePlanner({ bedtime: "22:30", wake: "07:00", weekends: true });
    await initProfilePanel({
      display_name: String(document.getElementById("session-user")?.textContent || "User"),
      timezone: "Asia/Kuwait",
      push_enabled: true,
      email_enabled: false,
    });
    await initDeviceControls();
    await initSpotifyConnect();
    await hydrateUserTimeline();
    bindUserActions();
  } finally {
    setMetricLoading([recovery, consistency, health, partner, winddown, style, locationMetric], false);
  }
}

function statusClassForUserTimeline(statusText) {
  const status = String(statusText || "").toLowerCase();
  if (status.includes("override")) return "good";
  if (status.includes("quiet") || status.includes("cooldown")) return "warn";
  if (status.includes("completed") || status.includes("active") || status.includes("ready") || status.includes("available")) return "good";
  if (status.includes("running")) return "warn";
  if (status.includes("queued")) return "warn";
  if (status.includes("review") || status.includes("pending") || status.includes("queued")) return "warn";
  if (status.includes("failed") || status.includes("error")) return "bad";
  return "warn";
}

async function awaitDeviceCommand(commandId, onProgress) {
  const maxAttempts = 8;
  for (let i = 0; i < maxAttempts; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 1000));
    try {
      const res = await readDeviceCommandStatus(commandId);
      if (res.status === 401) {
        redirectToLogin("user");
        return null;
      }
      if (!res.ok) continue;
      const payload = await res.json().catch(() => ({}));
      const command = payload?.command || null;
      if (!command) continue;
      if (typeof onProgress === "function") {
        onProgress(command);
      }
      const status = String(command?.status || "").toLowerCase();
      if (status === "completed" || status === "failed") {
        return command;
      }
    } catch (_err) {
      // Ignore intermediate polling failures.
    }
  }
  return null;
}

async function hydrateUserTimeline() {
  const tbody = document.getElementById("user-timeline-body");
  if (!tbody || !location.pathname.includes("user-dashboard")) return;
  tbody.innerHTML = '<tr><td colspan="3" class="table-note">Loading timeline...</td></tr>';

  try {
    const res = await loadUserTimelineFromApi();
    if (res.status === 401) {
      redirectToLogin("user");
      return;
    }
    if (!res.ok) {
      tbody.innerHTML = '<tr><td colspan="3" class="table-note">Timeline unavailable right now.</td></tr>';
      return;
    }
    const payload = await res.json().catch(() => ({}));
    const items = Array.isArray(payload?.items) ? payload.items : [];
    if (!items.length) {
      tbody.innerHTML = '<tr><td colspan="3" class="table-note">No timeline events yet.</td></tr>';
      return;
    }

    tbody.innerHTML = "";
    items.forEach((item) => {
      const status = String(item?.status || "active");
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${String(item?.time || "Anytime")}</td>
        <td>${String(item?.event || "Timeline event")}</td>
        <td><span class="status ${statusClassForUserTimeline(status)}">${status}</span></td>
      `;
      tbody.appendChild(tr);
    });
  } catch (_err) {
    tbody.innerHTML = '<tr><td colspan="3" class="table-note">Timeline unavailable right now.</td></tr>';
  }
}

function bindUserActions() {
  if (!location.pathname.includes("user-dashboard")) return;

  const status = document.getElementById("user-actions-status");
  const buttons = [
    { id: "user-action-winddown", action: "winddown" },
    { id: "user-action-optimize-room", action: "optimize_room" },
    { id: "user-action-wake-recovery", action: "wake_recovery" },
    { id: "user-action-reactive-lights", action: "reactive_lights" },
    { id: "user-action-quiet-override", action: "quiet_hours_override" },
  ];

  const runAction = async (action) => {
    if (status) status.textContent = "Executing action...";
    try {
      const res = await submitDeviceCommand(action);
      if (res.status === 401) {
        redirectToLogin("user");
        return;
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        if (status) status.textContent = err?.detail || "Action failed.";
        return;
      }
      const payload = await res.json().catch(() => ({}));
      const commandId = String(payload?.command_id || "");
      if (status) status.textContent = payload?.message || "Command queued.";
      await hydrateUserTimeline();

      if (commandId) {
        const finalCommand = await awaitDeviceCommand(commandId, (cmd) => {
          if (!status) return;
          const cur = String(cmd?.status || "running").toLowerCase();
          if (cur === "running") {
            status.textContent = "Command running on device...";
          } else if (cur === "queued") {
            status.textContent = "Command queued...";
          }
        });

        if (finalCommand && status) {
          const finalStatus = String(finalCommand?.status || "").toLowerCase();
          if (finalStatus === "completed") {
            status.textContent = finalCommand?.message || "Device command completed.";
          } else if (finalStatus === "failed") {
            status.textContent = "Device command failed. Please retry.";
          }
        }
      }
      await hydrateUserTimeline();
    } catch (_err) {
      if (status) status.textContent = "Network error while executing action.";
    }
  };

  buttons.forEach((cfg) => {
    const btn = document.getElementById(cfg.id);
    if (!btn) return;
    if (btn.dataset.bound === "1") return;
    btn.dataset.bound = "1";
    btn.addEventListener("click", () => runAction(cfg.action));
  });
}

async function hydrateAdminOverview() {
  const registeredUsers = document.getElementById("admin-registered-users");
  const activeBeds = document.getElementById("admin-active-beds");
  const openIncidents = document.getElementById("admin-open-incidents");
  const aiHealth = document.getElementById("admin-ai-health");
  const aiHealthBar = document.getElementById("admin-ai-health-bar");
  if (!registeredUsers || !activeBeds || !openIncidents || !aiHealth) return;
  setMetricLoading([registeredUsers, activeBeds, openIncidents, aiHealth], true);

  try {
    const overviewRes = await apiFetch("/v1/admin/overview");
    if (overviewRes.status === 401) {
      redirectToLogin("admin");
      return;
    }
    if (!overviewRes.ok) return;
    const overview = await overviewRes.json();

    registeredUsers.textContent = Number(overview?.registered_users || 0).toLocaleString();
    activeBeds.textContent = Number(overview?.active_beds || 0).toLocaleString();
    openIncidents.textContent = String(overview?.open_incidents || 0);
    const healthValue = Number(overview?.ai_quota_health_percent || 0);
    aiHealth.textContent = `${healthValue}%`;
    if (aiHealthBar) aiHealthBar.style.width = `${Math.max(0, Math.min(100, healthValue))}%`;
  } catch (_err) {
    // Keep default placeholder values on network failures.
  } finally {
    setMetricLoading([registeredUsers, activeBeds, openIncidents, aiHealth], false);
  }
}

async function hydrateAdminRuntime() {
  const guardDenied = document.getElementById("admin-guard-denied");
  const chatRequests = document.getElementById("admin-chat-requests");
  const sameOriginDenied = document.getElementById("admin-same-origin-denied");
  const tierMix = document.getElementById("admin-tier-mix");
  const graceUsers = document.getElementById("admin-grace-users");
  const webhookHealth = document.getElementById("admin-webhook-health");
  const webhookHealthBar = document.getElementById("admin-webhook-health-bar");
  if (!guardDenied || !chatRequests || !sameOriginDenied) return;

  setMetricLoading([guardDenied, chatRequests, sameOriginDenied], true);
  try {
    const runtimeRes = await apiFetch("/v1/admin/runtime");
    if (runtimeRes.status === 401) {
      redirectToLogin("admin");
      return;
    }
    if (!runtimeRes.ok) return;
    const runtime = await runtimeRes.json();

    guardDenied.textContent = String(runtime?.guard_denied || 0);
    chatRequests.textContent = String(runtime?.chat_requests || 0);
    sameOriginDenied.textContent = String(runtime?.same_origin_denied || 0);
    if (tierMix) tierMix.textContent = String(runtime?.tier_mix || "Free 39% | Standard 44% | Pro 17%");
    if (graceUsers) graceUsers.textContent = `7-day grace users: ${Number(runtime?.grace_users || 0)}`;
    const webhookRate = Number(runtime?.webhook_success_rate || 0);
    if (webhookHealth) webhookHealth.textContent = `Webhook success rate: ${webhookRate}%`;
    if (webhookHealthBar) webhookHealthBar.style.width = `${Math.max(0, Math.min(100, webhookRate))}%`;
  } catch (_err) {
    // Keep fallback values.
  } finally {
    setMetricLoading([guardDenied, chatRequests, sameOriginDenied], false);
  }
}

async function hydrateAdminFleet() {
  const tbody = document.getElementById("admin-fleet-snapshot-body");
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="3" class="table-note">Loading fleet snapshot...</td></tr>';

  try {
    const fleetRes = await apiFetch("/v1/admin/fleet");
    if (fleetRes.status === 401) {
      redirectToLogin("admin");
      return;
    }
    if (!fleetRes.ok) return;
    const payload = await fleetRes.json();
    const items = Array.isArray(payload?.items) ? payload.items : [];
    if (!items.length) {
      tbody.innerHTML = '<tr><td colspan="3" class="table-note">No fleet records yet.</td></tr>';
      return;
    }

    tbody.innerHTML = "";
    items.forEach((item) => {
      const tr = document.createElement("tr");
      const status = String(item?.status || "warn");
      tr.innerHTML = `
        <td>${String(item?.label || "-")}</td>
        <td>${String(item?.value || "-")}</td>
        <td><span class="status ${statusClassForIncident(status)}">${String(item?.note || status)}</span></td>
      `;
      tbody.appendChild(tr);
    });
  } catch (_err) {
    tbody.innerHTML = '<tr><td colspan="3" class="table-note">Fleet snapshot unavailable right now.</td></tr>';
  }
}

async function hydrateAdminAudit() {
  const tbody = document.getElementById("admin-audit-body");
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="4" class="table-note">Loading admin audit feed...</td></tr>';

  try {
    const auditRes = await apiFetch("/v1/admin/audit");
    if (auditRes.status === 401) {
      redirectToLogin("admin");
      return;
    }
    if (!auditRes.ok) return;
    const payload = await auditRes.json();
    const items = Array.isArray(payload?.items) ? payload.items : [];
    if (!items.length) {
      tbody.innerHTML = '<tr><td colspan="4" class="table-note">No audit events captured yet.</td></tr>';
      return;
    }

    tbody.innerHTML = "";
    items.forEach((item) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${String(item?.actor || "admin")}</td>
        <td>${String(item?.action || "-")}</td>
        <td>${String(item?.resource || "-")}</td>
        <td>${String(item?.time || "recent")}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (_err) {
    tbody.innerHTML = '<tr><td colspan="4" class="table-note">Audit feed unavailable right now.</td></tr>';
  }
}

function statusClassForCommandStatus(statusText) {
  const status = String(statusText || "").toLowerCase();
  if (status.includes("completed") || status.includes("active") || status.includes("ready")) return "good";
  if (status.includes("failed") || status.includes("error")) return "bad";
  return "warn";
}

async function hydrateAdminUserDashboard() {
  const settingsCount = document.getElementById("admin-user-settings-count");
  const routinesCount = document.getElementById("admin-user-routines-count");
  const liveCommands = document.getElementById("admin-user-command-live");
  const commandBreakdown = document.getElementById("admin-user-command-breakdown");
  const commandsBody = document.getElementById("admin-user-commands-body");
  const timelineBody = document.getElementById("admin-user-timeline-body");
  if (!settingsCount || !routinesCount || !liveCommands || !commandsBody || !timelineBody) return;

  setMetricLoading([settingsCount, routinesCount, liveCommands], true);
  commandsBody.innerHTML = '<tr><td colspan="4" class="table-note">Loading user command telemetry...</td></tr>';
  timelineBody.innerHTML = '<tr><td colspan="4" class="table-note">Loading user timeline activity...</td></tr>';

  try {
    const res = await apiFetch("/v1/admin/user-dashboard");
    if (res.status === 401) {
      redirectToLogin("admin");
      return;
    }
    if (!res.ok) return;

    const payload = await res.json().catch(() => ({}));
    const summary = payload?.summary || {};
    const commands = Array.isArray(payload?.commands) ? payload.commands : [];
    const timeline = Array.isArray(payload?.timeline) ? payload.timeline : [];

    const queued = Number(summary?.pending_commands || 0);
    const running = Number(summary?.running_commands || 0);
    const completed = Number(summary?.completed_commands || 0);

    settingsCount.textContent = String(Number(summary?.users_with_settings || 0));
    routinesCount.textContent = String(Number(summary?.users_with_routines || 0));
    liveCommands.textContent = String(queued + running);
    if (commandBreakdown) {
      commandBreakdown.textContent = `Queued ${queued} | Running ${running} | Completed ${completed}`;
    }

    if (!commands.length) {
      commandsBody.innerHTML = '<tr><td colspan="4" class="table-note">No user commands captured yet.</td></tr>';
    } else {
      commandsBody.innerHTML = "";
      commands.forEach((item) => {
        const status = String(item?.status || "queued");
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${String(item?.user || "-")}</td>
          <td>${String(item?.action || "-")}</td>
          <td><span class="status ${statusClassForCommandStatus(status)}">${status}</span></td>
          <td>${String(item?.updated_at || "recent")}</td>
        `;
        commandsBody.appendChild(tr);
      });
    }

    if (!timeline.length) {
      timelineBody.innerHTML = '<tr><td colspan="4" class="table-note">No user timeline activity yet.</td></tr>';
    } else {
      timelineBody.innerHTML = "";
      timeline.forEach((item) => {
        const status = String(item?.status || "active");
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${String(item?.user || "-")}</td>
          <td>${String(item?.time || "Anytime")}</td>
          <td>${String(item?.event || "Timeline event")}</td>
          <td><span class="status ${statusClassForCommandStatus(status)}">${status}</span></td>
        `;
        timelineBody.appendChild(tr);
      });
    }
  } catch (_err) {
    commandsBody.innerHTML = '<tr><td colspan="4" class="table-note">User command telemetry unavailable right now.</td></tr>';
    timelineBody.innerHTML = '<tr><td colspan="4" class="table-note">User timeline activity unavailable right now.</td></tr>';
  } finally {
    setMetricLoading([settingsCount, routinesCount, liveCommands], false);
  }
}

function bindAdminActions() {
  if (!location.pathname.includes("admin-panel")) return;

  const status = document.getElementById("admin-actions-status");
  const actionButtons = [
    { id: "admin-action-publish-firmware", action: "publish_firmware" },
    { id: "admin-action-device-timeline", action: "device_timeline" },
    { id: "admin-action-open-billing", action: "open_billing" },
    { id: "admin-action-export-report", action: "export_report" },
  ];

  const runAction = async (action) => {
    if (status) status.textContent = "Running admin action...";
    try {
      const res = await apiFetch("/v1/admin/actions", {
        method: "POST",
        body: JSON.stringify({ action }),
      });
      if (res.status === 401) {
        redirectToLogin("admin");
        return;
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        if (status) status.textContent = err?.detail || "Action failed.";
        return;
      }
      const payload = await res.json().catch(() => ({}));
      if (status) status.textContent = payload?.message || payload?.title || "Action completed.";
      hydrateAdminAudit();
    } catch (_err) {
      if (status) status.textContent = "Network error while executing action.";
    }
  };

  actionButtons.forEach((cfg) => {
    const btn = document.getElementById(cfg.id);
    if (!btn) return;
    btn.addEventListener("click", () => runAction(cfg.action));
  });
}

function statusClassForIncident(statusText) {
  const status = String(statusText || "").toLowerCase();
  if (status.includes("mitigated") || status.includes("resolved")) return "good";
  if (status.includes("escalated") || status.includes("failed")) return "bad";
  return "warn";
}

async function hydrateAdminIncidents() {
  const tbody = document.getElementById("admin-incidents-body");
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="4" class="table-note">Loading incident feed...</td></tr>';

  try {
    const incidentsRes = await apiFetch("/v1/admin/incidents");
    if (incidentsRes.status === 401) {
      redirectToLogin("admin");
      return;
    }
    if (!incidentsRes.ok) return;
    const payload = await incidentsRes.json();
    const items = Array.isArray(payload?.items) ? payload.items : [];
    if (!items.length) {
      tbody.innerHTML = '<tr><td colspan="4" class="table-note">No active incidents. Fleet is stable.</td></tr>';
      return;
    }

    tbody.innerHTML = "";
    items.forEach((item) => {
      const tr = document.createElement("tr");
      const status = String(item?.status || "monitoring");
      tr.innerHTML = `
        <td>${String(item?.id || "-")}</td>
        <td>${String(item?.type || "-")}</td>
        <td>${String(item?.device || "-")}</td>
        <td><span class="status ${statusClassForIncident(status)}">${status}</span></td>
      `;
      tbody.appendChild(tr);
    });
  } catch (_err) {
    tbody.innerHTML = '<tr><td colspan="4" class="table-note">Live incidents unavailable. Showing fallback data.</td></tr>';
  }
}

window.addEventListener("DOMContentLoaded", () => {
  initCinematicSheen();
  setContactStrip();
  initLoginPage();
  initChatWidget();
  activateNavButtons();
  bindLogoutAction();
  hydrateSessionIdentity();
  hydrateUserDashboard();
  hydrateAdminOverview();
  hydrateAdminRuntime();
  hydrateAdminIncidents();
  hydrateAdminFleet();
  hydrateAdminAudit();
  hydrateAdminUserDashboard();
  bindAdminActions();
});
