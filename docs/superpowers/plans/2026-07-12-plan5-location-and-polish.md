# Plan 5: Location-Aware Prayer Times + Professional Polish

Lean plan (inline execution, fast checks; full suite via CI on push).

## Part A — Location → prayer times, automatically

Chain (mostly existed): capture GPS (geolocator) → save to profile →
backend read-through (P0-3 fix) → AlAdhan prayer times for real coordinates.

- [x] **A1. "Use my location" on the Islamic screen** — user-initiated sync
  that triggers the OS permission dialog, saves coords (forcing mode back to
  `auto` — the ONLY recovery after a past denial permanently flipped the
  profile to `manual`), refreshes `islamicOverviewProvider`, honest snackbars
  for denied/disabled/failed. `SmartBedRepository.syncDeviceLocation()`.
- [ ] **A2. Ask at the right moment** — onboarding step (post-register):
  "Prayer times follow where you are" rationale screen before the OS dialog;
  skip cleanly if denied (defaults to Kuwait City until A1 is used).
- [ ] **A3. Silent refresh on app resume** — if permission already granted
  and mode=auto, re-capture on lifecycle resume (>25km move updates profile).
- [ ] **A4. Schedules follow location** — verify alarm next_trigger and
  automation windows use profile timezone; fix if UTC-pinned.

## Part B — Design: "professional grade" direction

**Subject**: a calm evening companion for Gulf Muslim households — sleep
science braided with the five-prayer rhythm. The design should feel like
dusk in Kuwait: deep, warm, unhurried.

**Signature (the one aesthetic risk): The Prayer Arc.** The day rendered as
a sky arc — five prayer marks positioned on it, the arc's gradient tracking
the *actual* window (Fajr indigo → Dhuhr bright → Asr gold → Maghrib ember →
Isha violet-navy), next prayer glowing with a countdown. Lives as the Home
hero + Islamic screen header. It mirrors the bed's circadian LED story: the
app and the hardware tell one story. Everything else stays quiet.

**Palette** (refine current navy/cyan, don't replace):
- ground `#0A1628` (keep) · surface `#12213B` (keep)
- utility accent cyan `#22D3EE` (keep — buttons, links, info)
- prayer-window hues (semantic, used ONLY by the arc + sacred moments):
  fajr `#6366F1` · dhuhr `#E8F1FF` · asr `#F4B860` · maghrib `#E86A33` ·
  isha `#312E81`
- gold `#F4B860` is reserved for sacred/celebration; never a button color.

**Type**: Arabic-first pairing — IBM Plex Sans Arabic (ar) with Manrope
(Latin display) + system fallback body; tabular numerals for prayer times,
countdowns, and stats so digits never jitter.

**Motion system** (one orchestrated moment, micro elsewhere, always honoring
`MediaQuery.disableAnimations`):
- Home load: arc draws (600ms ease-out), cards stagger in 80ms apart.
- Countdown ring "breathes" only in the last 10 minutes before a prayer.
- Hydration: water-fill animation on log; press-scale (0.98) on cards.

**Professional floor**: skeleton loaders replace spinners; every empty state
gets one clear action; every error state gets retry; spacing scale
4/8/12/16/24 enforced; RTL audit with Arabic strings; 48dp tap targets.

### Tasks
- [ ] **B1. Token consolidation** — one theme file: palette above + type +
  spacing as Flutter ThemeExtension; kill per-screen hex literals.
- [ ] **B2. Prayer Arc widget** — CustomPainter, drives Home hero + Islamic
  header; countdown + window hue; reduced-motion safe.
- [ ] **B3. Motion pass** — load stagger, press feedback, hydration fill.
- [ ] **B4. States pass** — skeletons, empty, error+retry across live screens.
- [ ] **B5. Arabic type + RTL sweep** — fonts wired, l10n strings for live
  screens, RTL layout audit.
- [ ] **B6. Haptics + final sweep** — selection clicks, success taps;
  remove one accessory per screen (Chanel rule).

Order: A2 → B1 → B2 (the hero) → B3/B4 → B5 → A3/A4 → B6.
