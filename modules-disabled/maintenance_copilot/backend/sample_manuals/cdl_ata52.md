---
doc_type: CDL
title: Configuration Deviation List — ATA 52 Doors
revision: Rev-07
effective_date: 2026-04-15
ata_chapter: "52"
---

# CDL 52-00 — General

The Configuration Deviation List (CDL) permits dispatch with certain secondary
airframe parts missing. Unlike the Minimum Equipment List (MEL), which governs
inoperative *systems* and equipment, the CDL addresses secondary structural and
aerodynamic *parts* — access panels, fairings, seals, static dischargers, drain
masts, lens covers, and similar non-primary items. Each item below states the
associated performance penalty and any placarding requirement.

Note: If a *system* is affected (for example, a door warning sensor, a latch
actuator, or a proximity switch), that condition is governed by the MEL, not by
this CDL. See the MEL — for example MEL 52-30-01 (cargo door warning) or
MEL 32-30-01 (landing gear door sequence) — for system-level dispatch relief.
Do not attempt to use a CDL item to dispatch an inoperative system.

## 52-00-1 — How to Use This Document

Each CDL item is identified by a three-part number in the form CDL 52-XX-Y,
where 52 is the ATA chapter (Doors), XX is the section, and Y is the sequential
item within that section. An item is applicable only when the missing part
matches the part identity given in the item heading, including the part number
(P/N) or panel/zone identifier where quoted.

Every item provides, in order:

- the part identity and its location or zone;
- a "may be dispatched with ... missing" statement establishing the relief;
- a "Performance penalty:" line, expressed either as additional fuel burn in
  kilograms per flight hour (kg/hr) or as "negligible" or "none";
- an optional "Limitation:" line stating quantity, symmetry, or interaction
  constraints; and
- a placarding instruction: either "Placard required:" with the exact placard
  text, or "No placard required."

## 52-00-2 — Cumulative Penalties

Performance penalties are **cumulative**. When more than one part is missing,
sum the individual penalties across all applicable CDL items and confirm the
total against the operator's dispatch performance limits for the route, runway,
and payload. If the aircraft is also dispatched under one or more MEL items that
carry a performance penalty, the CDL total and the MEL total **combine**: add
both before checking dispatch limits.

Caution: A combination of several individually "negligible" or small penalties
can become significant. Always compute the arithmetic total; never assume the
sum is negligible because each contributor is small.

## 52-00-3 — Repair Interval and Recording

A part released under the CDL must be repaired or replaced at the next scheduled
maintenance opportunity, unless a shorter interval is specified in the item.
Record every deviation in the aircraft technical log, quoting:

- the CDL item number (for example, CDL 52-10-1);
- the date the deviation was recorded;
- the specific part number or panel identifier that is missing; and
- the location on the airframe (zone, side, surface).

Note: Where an item affects a pressure boundary — a passenger, service, or cargo
door seal — the pre-departure pressurization / cabin-differential leak check
must confirm the leak rate remains within the Aircraft Maintenance Manual (AMM)
limits before dispatch. This interacts with, but does not replace, any related
MEL pressurization relief.

## 52-00-4 — Definitions

- "Access panel" — a removable secondary panel providing maintenance access,
  not part of the pressure boundary and not load-bearing for primary loads.
- "Fairing" — an aerodynamic shroud that smooths airflow over a structural
  feature (flap track, gear, wing-to-body junction) but carries no primary load.
- "Seal segment" — a discrete length of door or panel seal, replaceable
  independently of adjacent segments.
- "Static discharger" — a wick or rod that bleeds accumulated static charge
  from a surface trailing edge to reduce precipitation-static radio interference.
- "Dielectric panel" — a non-metallic panel (typically over an antenna) that is
  transparent to radio frequency energy.

# CDL 52-10 — Access Panels, 191/192/193 Series

This section covers removable maintenance access panels in the lower fuselage
and door-surround zones. Before dispatch with any panel of these series missing,
inspect the exposed structure and any exposed wiring or plumbing for security,
chafing, and damage.

## CDL 52-10-1 — Access Panel 191AB

Aircraft may be dispatched with access panel 191AB missing.
Performance penalty: 5 kg additional fuel per flight hour. No placard required.

Limitation: Not more than one access panel from the 191-series may be missing at
the same time. Inspect the exposed structure and any exposed wiring or plumbing
for security and damage before dispatch.

## CDL 52-10-2 — Access Panel 192CD

Aircraft may be dispatched with access panel 192CD missing.
Performance penalty: 8 kg additional fuel per flight hour.
Placard required: Placard the flight deck DISPATCH CONFIG panel with
"192CD MISSING."

Limitation: Do not dispatch with both 191AB and 192CD missing on the same side
of the aircraft.

## CDL 52-10-3 — Access Panel 191CD

Aircraft may be dispatched with access panel 191CD (lower fuselage, forward
cargo zone) missing.
Performance penalty: 5 kg additional fuel per flight hour.
Limitation: Counts against the 191-series single-panel limit stated in
CDL 52-10-1. Not more than one 191-series panel missing at a time.
No placard required.

## CDL 52-10-4 — Access Panel 192AB

Aircraft may be dispatched with access panel 192AB missing.
Performance penalty: 7 kg additional fuel per flight hour.
Limitation: Do not dispatch with both 192AB and 192CD missing.
Placard required: Placard the DISPATCH CONFIG panel with "192AB MISSING."

## CDL 52-10-5 — Access Panel 193AB

Aircraft may be dispatched with access panel 193AB (aft service door surround)
missing.
Performance penalty: 4 kg additional fuel per flight hour.
Limitation: Not more than two panels of the combined 191/192/193 series may be
missing on the aircraft at once; verify the cumulative penalty against dispatch
limits.
No placard required.

## CDL 52-10-6 — Access Panel 193CD

Aircraft may be dispatched with access panel 193CD missing.
Performance penalty: 4 kg additional fuel per flight hour.
Limitation: Counts against the two-panel combined-series limit in CDL 52-10-5.
No placard required.

## CDL 52-10-7 — Access Panel 194 (Aft Pressure Dome Access)

Aircraft may be dispatched with access panel 194 missing **only** if the panel
is external to the pressure boundary; verify against the AMM zone diagram.
Performance penalty: 6 kg additional fuel per flight hour.
Caution: If panel 194 forms part of the pressure boundary, the CDL does not
apply — the aircraft is not dispatchable in that configuration and the missing
panel must be replaced before flight.
Placard required: Placard "194 MISSING — VERIFY NON-PRESSURE."

# CDL 52-20 — Door-Surround Fairings and Fairing Panels

Fairings smooth airflow around doors and adjacent structure. Missing fairings
increase drag; the penalties below reflect typical cruise increments.

## CDL 52-20-1 — Wing-to-Body Fairing Panel (Lower, Left)

Aircraft may be dispatched with one lower wing-to-body fairing panel on the left
side missing.
Performance penalty: 12 kg additional fuel per flight hour.
Limitation: Not both left and right lower wing-to-body fairing panels missing on
the same flight. Inspect exposed fasteners and system runs for security.
Placard required: Placard "W2B FAIRING LH — CDL 52-20-1."

## CDL 52-20-2 — Wing-to-Body Fairing Panel (Lower, Right)

Aircraft may be dispatched with one lower wing-to-body fairing panel on the
right side missing.
Performance penalty: 12 kg additional fuel per flight hour.
Limitation: Not both sides missing (see CDL 52-20-1). Not to be combined with a
missing belly fairing (CDL 52-20-5) without recomputing total drag penalty.
Placard required: Placard "W2B FAIRING RH — CDL 52-20-2."

## CDL 52-20-3 — Flap Track Fairing (Inboard)

Aircraft may be dispatched with one inboard flap track fairing (canoe fairing)
missing.
Performance penalty: 9 kg additional fuel per flight hour.
Limitation: Not more than one flap track fairing missing per wing. Confirm no
fouling of the flap mechanism and that the exposed track is undamaged.
Placard required: Placard "FLAP TRK FAIRING — CDL 52-20-3."

## CDL 52-20-4 — Flap Track Fairing (Outboard)

Aircraft may be dispatched with one outboard flap track fairing missing.
Performance penalty: 7 kg additional fuel per flight hour.
Limitation: Combined with CDL 52-20-3, not more than one flap track fairing per
wing missing at a time.
No placard required.

## CDL 52-20-5 — Belly Fairing Access Panel

Aircraft may be dispatched with one belly (keel) fairing access panel missing.
Performance penalty: 6 kg additional fuel per flight hour.
Limitation: Not more than two belly fairing access panels missing at once.
No placard required.

## CDL 52-20-6 — Main Landing Gear Door Fairing

Aircraft may be dispatched with one main landing gear door aerodynamic fairing
(non-structural trailing edge shroud) missing.
Performance penalty: 8 kg additional fuel per flight hour.
Limitation: The gear door itself and its actuation are a *system* — if the door
or its mechanism is affected, refer to the MEL, not this CDL. This item covers
only the detachable aerodynamic shroud.
Placard required: Placard "MLG DOOR FAIRING — CDL 52-20-6."

## CDL 52-20-7 — Nose Landing Gear Door Fairing

Aircraft may be dispatched with the nose landing gear door aerodynamic fairing
missing.
Performance penalty: 5 kg additional fuel per flight hour.
Limitation: Not to be combined with CDL 52-20-6 on the same flight without
recomputing the cumulative penalty against takeoff performance limits.
No placard required.

## CDL 52-20-8 — Passenger Door Hinge Fairing

Aircraft may be dispatched with one passenger door external hinge fairing
missing.
Performance penalty: 3 kg additional fuel per flight hour.
Limitation: Not more than two hinge fairings missing across all passenger doors.
Verify the door still closes and latches normally.
No placard required.

# CDL 52-30 — Door and Panel Seal Segments

Seal segments maintain aerodynamic smoothness and, for pressure-boundary doors,
contribute to the cabin pressure seal. Items in this section that affect a
pressure boundary require a satisfactory pre-departure pressurization check.

## CDL 52-30-1 — Cargo Door Seal Segment

Aircraft may be dispatched with one cargo door seal segment (P/N 52-SEAL-30)
missing, provided the adjacent segments are secure and the door closes and
latches normally.
Performance penalty: negligible fuel penalty; cabin/cargo differential-pressure
leak rate must remain within limits on the pre-departure pressurization check.
Placard required: Placard "CARGO DOOR SEAL — CDL 52-30-1."

## CDL 52-30-2 — Passenger Door Aerodynamic Seal Segment

Aircraft may be dispatched with one passenger door external aerodynamic seal
segment (P/N 52-SEAL-31) missing.
Performance penalty: negligible.
Limitation: Not more than one aerodynamic seal segment missing per door, and not
more than two across the aircraft. This item covers the *external* aerodynamic
seal only; the pressure seal is addressed by CDL 52-30-3.
Placard required: Placard "PAX DOOR AERO SEAL — CDL 52-30-2."

## CDL 52-30-3 — Passenger Door Pressure Seal Segment

Aircraft may be dispatched with one passenger door pressure seal segment
(P/N 52-SEAL-32) missing **only if** the pre-departure pressurization check
confirms cabin leak rate within AMM limits.
Performance penalty: negligible aerodynamically; monitor cabin pressurization.
Caution: If the pressurization check exceeds limits, the aircraft is not
dispatchable under this item. A pressurization *system* fault is an MEL matter
(see MEL 21-31-01); a missing seal *part* within leak limits is this CDL item.
Placard required: Placard "PAX DOOR PRESS SEAL — CDL 52-30-3 — MONITOR CABIN."

## CDL 52-30-4 — Service Door Seal Segment

Aircraft may be dispatched with one galley service door seal segment
(P/N 52-SEAL-33) missing, provided the door closes and latches normally and the
pressurization check is satisfactory.
Performance penalty: negligible.
Limitation: Not more than one service door seal segment missing at a time.
Placard required: Placard "SVC DOOR SEAL — CDL 52-30-4."

## CDL 52-30-5 — Cargo Door Seal Segment (Aft Compartment)

Aircraft may be dispatched with one aft cargo door seal segment (P/N 52-SEAL-34)
missing under the same conditions as CDL 52-30-1.
Performance penalty: negligible; confirm cargo compartment differential leak
rate within limits.
Limitation: Not more than one cargo door seal segment missing per door.
Not to be combined with CDL 52-30-1 on the same door.
Placard required: Placard "AFT CARGO DOOR SEAL — CDL 52-30-5."

## CDL 52-30-6 — Avionics Bay Access Door Seal

Aircraft may be dispatched with the avionics bay external access door seal
segment missing.
Performance penalty: negligible.
Limitation: This bay is normally unpressurized; verify against AMM. If the seal
is part of a pressurized boundary on the applicable model, apply CDL 52-30-3
conditions instead.
No placard required.

## CDL 52-30-7 — Emergency Exit Door Aerodynamic Seal

Aircraft may be dispatched with one overwing emergency exit door external
aerodynamic seal segment missing.
Performance penalty: negligible.
Caution: The emergency exit *mechanism, arming, and warning* are governed by the
MEL, not this CDL. This item releases only a missing external aerodynamic seal
that does not affect exit operation or the pressure boundary.
Placard required: Placard "OWE AERO SEAL — CDL 52-30-7."

# CDL 52-40 — Static Dischargers and Electrical/Aerodynamic Trailing-Edge Items

Static dischargers bleed precipitation-static charge from trailing edges. A
limited number may be missing before radio interference or charge buildup
becomes a concern.

## CDL 52-40-1 — Static Discharger

Aircraft may be dispatched with up to two static dischargers missing from the
airframe, provided no more than one is missing from any single control surface.
Performance penalty: none. No fuel penalty.
No placard required, but record each missing discharger location in the
technical log.

## CDL 52-40-2 — Static Discharger (Wingtip)

Aircraft may be dispatched with one wingtip static discharger missing per
wingtip.
Performance penalty: none.
Limitation: Counts toward the total-of-two airframe limit in CDL 52-40-1.
No placard required; record location in the technical log.

## CDL 52-40-3 — Static Discharger (Horizontal Stabilizer)

Aircraft may be dispatched with one horizontal stabilizer trailing-edge static
discharger missing per side.
Performance penalty: none.
Limitation: Not more than one per elevator surface; counts toward the total in
CDL 52-40-1.
No placard required; record location in the technical log.

## CDL 52-40-4 — Static Discharger (Vertical Stabilizer / Rudder)

Aircraft may be dispatched with one rudder trailing-edge static discharger
missing.
Performance penalty: none.
Limitation: The vertical stabilizer / rudder is a single control surface for the
purpose of the "one per surface" rule in CDL 52-40-1.
No placard required; record location in the technical log.

Note: If VHF communication or navigation reception degrades in precipitation
after dispatch under a 52-40 item, the flight crew should suspect P-static and
the affected radio should be assessed against the MEL on the next check.

# CDL 52-50 — Drain Masts, Vents, and Drain Provisions

## CDL 52-50-1 — Forward Galley Drain Mast

Aircraft may be dispatched with the forward galley drain mast heater fairing
(aerodynamic cover only) missing.
Performance penalty: 2 kg additional fuel per flight hour.
Limitation: This item covers the aerodynamic cover only. The drain mast *heater*
is a system — if the heater is inoperative, refer to the MEL (icing protection).
No placard required.

## CDL 52-50-2 — Aft Lavatory Drain Mast Fairing

Aircraft may be dispatched with the aft lavatory drain mast aerodynamic fairing
missing.
Performance penalty: 2 kg additional fuel per flight hour.
Limitation: Not both galley and lavatory drain mast fairings missing on the same
flight in known or forecast icing conditions.
No placard required.

## CDL 52-50-3 — Fuselage Overpressure Vent Screen

Aircraft may be dispatched with one fuselage overpressure vent screen (mesh
insect/debris guard) missing.
Performance penalty: negligible.
Limitation: Inspect the vent aperture for obstruction and foreign object debris
before each dispatch until repaired.
No placard required.

# CDL 52-60 — Position Light Lenses and Dielectric/Antenna Panels

## CDL 52-60-1 — Wingtip Position Light Lens Cover

Aircraft may be dispatched with one wingtip position light outer lens *cover*
(clear protective fairing) missing, provided the light unit itself remains
serviceable and weatherproof.
Performance penalty: 1 kg additional fuel per flight hour.
Limitation: The position *light* is a system — if the light is inoperative,
refer to the MEL (exterior lighting). This item covers the detachable outer lens
cover only.
Placard required: Placard "POS LT LENS COVER — CDL 52-60-1."

## CDL 52-60-2 — Tail Navigation Light Lens Cover

Aircraft may be dispatched with the tail navigation light outer lens cover
missing under the same conditions as CDL 52-60-1.
Performance penalty: 1 kg additional fuel per flight hour.
Limitation: Not to be combined with CDL 52-60-1 on the same flight at night in
IMC without confirming lighting airworthiness against the MEL.
No placard required.

## CDL 52-60-3 — Dielectric Antenna Panel (VHF)

Aircraft may be dispatched with one VHF dielectric antenna panel *trim fairing*
missing, provided the antenna and its seal remain secure and weatherproof.
Performance penalty: 2 kg additional fuel per flight hour.
Caution: If the missing panel exposes the antenna feed or seal to weather, or if
antenna performance is affected, the aircraft is not dispatchable under the CDL
— assess the antenna against the MEL.
Placard required: Placard "VHF DIELECTRIC TRIM — CDL 52-60-3."

## CDL 52-60-4 — Radome Erosion Boot Segment

Aircraft may be dispatched with one radome leading-edge erosion boot segment
missing.
Performance penalty: negligible.
Limitation: Not more than one boot segment missing; inspect the radome laminate
for exposure or damage. Weather radar performance is an MEL matter if degraded.
No placard required.

# CDL 52-70 — Vortex Generators and Aerodynamic Seals

## CDL 52-70-1 — Wing Vortex Generator (Single)

Aircraft may be dispatched with up to two wing upper-surface vortex generators
missing, provided they are not adjacent.
Performance penalty: 3 kg additional fuel per flight hour for the first, plus
2 kg per flight hour for the second.
Limitation: Not more than two missing per wing, and never two adjacent vortex
generators. Verify remaining generators are secure.
Placard required: Placard "VG MISSING — CDL 52-70-1" if two are missing.

## CDL 52-70-2 — Nacelle Strake

Aircraft may be dispatched with one nacelle strake missing per engine.
Performance penalty: 4 kg additional fuel per flight hour.
Limitation: Not both nacelle strakes missing on the same engine. Not more than
one strake missing across the aircraft without a specific engineering
assessment.
Placard required: Placard "NACELLE STRAKE — CDL 52-70-2."

## CDL 52-70-3 — Control Surface Aerodynamic Seal (Spoiler)

Aircraft may be dispatched with one spoiler panel trailing-edge aerodynamic seal
segment missing.
Performance penalty: 2 kg additional fuel per flight hour.
Limitation: Not more than one spoiler aerodynamic seal missing per wing. Confirm
spoiler travel is unaffected (a mechanical restriction is an MEL matter).
No placard required.

## CDL 52-70-4 — Aileron Gap Seal Segment

Aircraft may be dispatched with one aileron gap seal segment missing.
Performance penalty: 3 kg additional fuel per flight hour.
Limitation: Not more than one gap seal segment missing per aileron; not both
ailerons affected on the same flight.
No placard required.

# CDL 52-80 — Miscellaneous Secondary Structure

## CDL 52-80-1 — Cabin Window Reveal Trim Panel (External)

Aircraft may be dispatched with one external cabin window reveal trim panel
missing, provided the window pane and its structural retention are unaffected.
Performance penalty: negligible.
Limitation: Not more than two external trim panels missing. This item does not
apply to the window pane itself, which is a structural/pressure item.
No placard required.

## CDL 52-80-2 — Wheel Well Splash Guard

Aircraft may be dispatched with one main wheel well splash guard (mud/debris
deflector) missing.
Performance penalty: negligible.
Limitation: Inspect exposed systems in the wheel well for foreign object debris
risk before each dispatch until repaired.
No placard required.

## CDL 52-80-3 — APU Exhaust Ferrule Trim Ring

Aircraft may be dispatched with the APU exhaust ferrule aerodynamic trim ring
missing.
Performance penalty: 1 kg additional fuel per flight hour.
Limitation: The APU itself and its exhaust *system* are MEL items if affected;
this item covers only the external aerodynamic trim ring.
No placard required.

## CDL 52-80-4 — Ground Service Panel Door (External Cover)

Aircraft may be dispatched with one ground service panel external hinged cover
missing, provided the service connectors beneath are capped and secure.
Performance penalty: 2 kg additional fuel per flight hour.
Limitation: Not more than one ground service panel cover missing at a time.
Verify no exposed connector is a moisture-ingress or FOD hazard.
Placard required: Placard "GND SVC PANEL COVER — CDL 52-80-4."

# 52-90 — Dispatch Worked Example

The following illustrates cumulative penalty computation. Assume an aircraft is
dispatched with the following missing parts:

- CDL 52-10-1 Access Panel 191AB — 5 kg/hr
- CDL 52-20-3 Inboard Flap Track Fairing — 9 kg/hr
- CDL 52-40-1 two static dischargers — 0 kg/hr
- CDL 52-60-1 Wingtip Position Light Lens Cover — 1 kg/hr

CDL subtotal: 5 + 9 + 0 + 1 = 15 kg additional fuel per flight hour.

If the same flight also carries an MEL item with a 4 kg/hr performance penalty,
the combined dispatch penalty is 15 + 4 = 19 kg/hr. The dispatcher must add this
total to the trip fuel and confirm the aircraft still meets takeoff, en-route,
and landing performance limits. Placards are required for CDL 52-60-1 in this
example; the other items in this set require none.

Note: Confirm no limitation is violated — for example, only one 191-series panel
is missing (satisfied), and no two adjacent vortex generators are missing (not
applicable here). Record each item, part identifier, and date in the technical
log.

# 52-95 — Item Index

- CDL 52-10-1 — Access Panel 191AB — 5 kg/hr — no placard
- CDL 52-10-2 — Access Panel 192CD — 8 kg/hr — placard "192CD MISSING"
- CDL 52-10-3 — Access Panel 191CD — 5 kg/hr — no placard
- CDL 52-10-4 — Access Panel 192AB — 7 kg/hr — placard "192AB MISSING"
- CDL 52-10-5 — Access Panel 193AB — 4 kg/hr — no placard
- CDL 52-10-6 — Access Panel 193CD — 4 kg/hr — no placard
- CDL 52-10-7 — Access Panel 194 — 6 kg/hr — placard (verify non-pressure)
- CDL 52-20-1 — Wing-to-Body Fairing (LH) — 12 kg/hr — placard
- CDL 52-20-2 — Wing-to-Body Fairing (RH) — 12 kg/hr — placard
- CDL 52-20-3 — Flap Track Fairing (Inboard) — 9 kg/hr — placard
- CDL 52-20-4 — Flap Track Fairing (Outboard) — 7 kg/hr — no placard
- CDL 52-20-5 — Belly Fairing Access Panel — 6 kg/hr — no placard
- CDL 52-20-6 — MLG Door Fairing — 8 kg/hr — placard
- CDL 52-20-7 — NLG Door Fairing — 5 kg/hr — no placard
- CDL 52-20-8 — Passenger Door Hinge Fairing — 3 kg/hr — no placard
- CDL 52-30-1 — Cargo Door Seal Segment — negligible — placard
- CDL 52-30-2 — Passenger Door Aero Seal Segment — negligible — placard
- CDL 52-30-3 — Passenger Door Pressure Seal Segment — negligible — placard
- CDL 52-30-4 — Service Door Seal Segment — negligible — placard
- CDL 52-30-5 — Aft Cargo Door Seal Segment — negligible — placard
- CDL 52-30-6 — Avionics Bay Access Door Seal — negligible — no placard
- CDL 52-30-7 — Emergency Exit Aero Seal — negligible — placard
- CDL 52-40-1 — Static Discharger (up to two) — none — no placard
- CDL 52-40-2 — Static Discharger (Wingtip) — none — no placard
- CDL 52-40-3 — Static Discharger (Horizontal Stab) — none — no placard
- CDL 52-40-4 — Static Discharger (Rudder) — none — no placard
- CDL 52-50-1 — Forward Galley Drain Mast Fairing — 2 kg/hr — no placard
- CDL 52-50-2 — Aft Lavatory Drain Mast Fairing — 2 kg/hr — no placard
- CDL 52-50-3 — Overpressure Vent Screen — negligible — no placard
- CDL 52-60-1 — Wingtip Position Light Lens Cover — 1 kg/hr — placard
- CDL 52-60-2 — Tail Navigation Light Lens Cover — 1 kg/hr — no placard
- CDL 52-60-3 — VHF Dielectric Antenna Trim — 2 kg/hr — placard
- CDL 52-60-4 — Radome Erosion Boot Segment — negligible — no placard
- CDL 52-70-1 — Wing Vortex Generator — 3–5 kg/hr — conditional placard
- CDL 52-70-2 — Nacelle Strake — 4 kg/hr — placard
- CDL 52-70-3 — Spoiler Aero Seal Segment — 2 kg/hr — no placard
- CDL 52-70-4 — Aileron Gap Seal Segment — 3 kg/hr — no placard
- CDL 52-80-1 — Cabin Window Reveal Trim Panel — negligible — no placard
- CDL 52-80-2 — Wheel Well Splash Guard — negligible — no placard
- CDL 52-80-3 — APU Exhaust Ferrule Trim Ring — 1 kg/hr — no placard
- CDL 52-80-4 — Ground Service Panel Cover — 2 kg/hr — placard

# 52-99 — Revision Record

- Rev-07 (2026-04-15): Added CDL 52-30-7 (emergency exit aerodynamic seal),
  CDL 52-70-4 (aileron gap seal), and CDL 52-80-4 (ground service panel cover).
  Clarified pressure-boundary conditions in CDL 52-30-3 and cross-references to
  the MEL for system-level faults. Added worked example in section 52-90.
- Rev-06 (2025-11-01): Added the 52-70 vortex generator and nacelle strake items
  and the 52-60 dielectric/antenna panel items. Restructured the item index.
- Rev-05 (2025-06-15): Introduced drain mast fairing items (52-50) and expanded
  the static discharger section (52-40) to cover individual surfaces.
- Rev-04 (2024-12-10): Added passenger and service door seal segment items
  (52-30-2 through 52-30-6) with pressurization-check conditions.
- Rev-03 (2024-05-20): Added wing-to-body, flap track, and gear door fairing
  items (52-20). Established the cumulative-penalty computation guidance.
- Rev-02 (2023-10-01): Added 191/192/193-series access panel items beyond the
  original two, and the general "How to Use" and repair-interval sections.
- Rev-01 (2023-03-15): Initial issue with the baseline access panel, cargo door
  seal, and static discharger items.

Note: This CDL is self-consistent for ATA 52 secondary structure. For any
inoperative *system* — door warnings, latch actuators, proximity sensors,
pressurization control, heaters, or lighting units — refer to the MEL, not this
CDL. Where a CDL item and an MEL item both apply on the same flight, combine
their performance penalties before confirming dispatch limits.
