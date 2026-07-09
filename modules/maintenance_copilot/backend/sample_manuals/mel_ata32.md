---
doc_type: MEL
title: Minimum Equipment List — ATA 32 Landing Gear
revision: Rev-18
effective_date: 2026-06-01
ata_chapter: "32"
---

# MEL 32-00 — General

The Minimum Equipment List (MEL) permits dispatch with specified items
inoperative, subject to the stated conditions, limitations, placarding, and
repair intervals. This chapter (ATA 32) addresses the Landing Gear system,
including gear extension and retraction, position indicating, wheels and
brakes, anti-skid and autobrake, nose-wheel steering, and the associated
warning, monitoring, and control functions.

An item may be dispatched inoperative only when all listed provisos are
satisfied, the required operations (O) and maintenance (M) procedures are
established and available, and the affected item is placarded in accordance
with this document. If any proviso cannot be met, the item is not dispatchable
under the relevant MEL entry and normal airworthiness requirements apply.

## Purpose and Scope

This MEL is a relief document. It never grants dispatch authority beyond the
conditions stated herein, and it does not supersede an Airworthiness Directive,
an emergency Airworthiness Directive, or a manufacturer alert bulletin that
imposes a more restrictive condition. Where the MEL and the Configuration
Deviation List (CDL) both apply — for example CDL 52-30-1 for a missing gear
door secondary seal — the more restrictive limitation governs.

The provisions of this chapter presume a serviceable green hydraulic system
delivering a nominal 3000 psi, a normal gear transit time of 10 to 12 seconds
in both extension and retraction, and proximity sensor target gaps set to the
1.5 to 2.5 mm range specified in AMM 32-31-00. Any deviation from these
baseline values must be investigated per the applicable Trouble Shooting Manual
(TSM) chapter before an MEL relief is considered valid.

## Definitions of Procedure Symbols

Two symbols qualify the relief granted by an item. When either symbol appears,
the corresponding procedure must be completed and the results verified before
the aircraft is released for dispatch.

(O) Operations procedure. A procedure normally accomplished by the flight crew.
Operations procedures include recalculating takeoff and landing performance for
a degraded configuration, establishing an alternate gear-position confirmation
method, applying a speed or crosswind limitation, or briefing an abnormal
checklist. An (O) procedure is considered established when the crew has the
procedure available and has acknowledged its use for the dispatch concerned.

(M) Maintenance procedure. A procedure normally accomplished by maintenance
personnel. Maintenance procedures include deactivating a system, isolating a
component, verifying a mechanical down-and-locked condition, safetying a valve,
collaring a control, or installing a placard. An (M) procedure is considered
established when it has been performed, signed off in the technical log, and —
where relevant — the affected control or panel has been physically secured.

Note: Where both (O) and (M) are listed, both must be satisfied. Where a
procedure references an AMM task, the current revision of that task governs the
detailed steps. This MEL cites tasks by number only; it does not reproduce them.

## Repair Interval Categories

Each item carries a repair interval category. The repair interval is the
maximum time an item may remain inoperative before it must be repaired or the
aircraft removed from service. Repair intervals begin at 00:01 on the calendar
day following the day the defect was recorded in the technical log, and they are
counted in consecutive calendar days regardless of aircraft utilization.

- Category A: as specified in the remarks or proviso text of the individual
  item. No standard interval applies; the interval may be expressed in calendar
  days, flight cycles, or flight hours as stated.
- Category B: three (3) consecutive calendar days.
- Category C: ten (10) consecutive calendar days.
- Category D: one hundred twenty (120) consecutive calendar days.

Caution: An expired repair interval renders the aircraft not airworthy for
dispatch. Do not attempt to reset or extend an interval administratively. A
short-term extension, where the operator's approved program allows one, is a
one-time provision and must be documented before the original interval expires.

## Placarding Convention

Every inoperative item released under this MEL must be placarded in view of the
flight crew unless the individual item states otherwise. Placards use the
component name followed by the word INOP — for example, ANTI-SKID INOP or NOSE
WHEEL STEERING INOP. Placards must be legible, durable, and removed only when
the item is restored and the technical log entry is cleared.

## Cross-Reference Documents

The following documents are referenced throughout this chapter and form part of
the technical basis for the reliefs granted:

- AMM 29-00-00 — Hydraulic Power, general and system description.
- AMM 32-31-00 — Landing Gear extension and retraction, normal operation and
  proximity sensor rigging.
- AMM 32-32-00 — Free-fall / alternate (gravity) extension procedure.
- AMM Task 32-11-00-700-801 — Landing gear operational test.
- TSM 32-31 — Extension / retraction fault isolation.
- TSM 32-32 — Gear-not-locked and downlock fault isolation.
- TSM 32-33 — Position indicating fault isolation.
- TSM 32-41 — Wheels, brakes, and anti-skid fault isolation.
- CDL 52-30-1 — Landing gear door missing/secondary-seal configuration deviation.

Note: Where an item directs the reader to "troubleshoot per TSM 32-xx", the
fault must be isolated to confirm the failure is limited to the function for
which relief is sought. Reliefs do not apply to undiagnosed faults.

# MEL 32-30-01 — Landing Gear Position Indicating

Category: C. Number installed: 3. Number required for dispatch: 2.

Placarding required: Placard the affected gear position indicator INOP.
One indicator may be inoperative provided alternate procedures are established
and used. Repair interval: 10 calendar days (Category C).

(O) The flight crew must use the alternate gear-position confirmation procedure
(free-fall/visual check reference, AMM 32-32-00) prior to landing.
(M) Confirm the affected gear is mechanically down-and-locked before each
dispatch until repair. Troubleshoot the indicating fault per TSM 32-33.

Note: This relief applies only to the indicating channel. If the gear itself
does not reach down-and-locked, the aircraft is not dispatchable under this
item; see TSM 32-32.

Caution: Do not confuse a failed indicator with a failed downlock. A confirmed
down-and-locked gear with a dead indication is dispatchable under this item; a
gear that will not lock is not.

# MEL 32-40-01 — Anti-Skid System

Category: C. Number installed: 1. Number required for dispatch: 0.

The anti-skid system may be inoperative provided:
(O) Takeoff and landing performance is recalculated for the anti-skid-inoperative
configuration and the runway is dry or damp (not contaminated).
(M) Deactivate the anti-skid system and placard ANTI-SKID INOP.
Repair interval: 10 calendar days (Category C).

Note: With anti-skid inoperative, expect increased brake temperatures. Refer to
TSM 32-41 if brake drag or asymmetric braking is subsequently reported.

Caution: Do not dispatch with anti-skid inoperative onto a contaminated runway.
The performance credit for anti-skid braking is not available in this
configuration and stopping distances increase materially.

# MEL 32-30-02 — Landing Gear Aural Warning

Category: B. Number installed: 1. Number required for dispatch: 0.

The landing gear aural warning may be inoperative provided:
(O) The flight crew verifies gear position visually and by indicator on every
approach.
(M) Placard GEAR AURAL WARNING INOP.
Repair interval: 3 calendar days (Category B).

Note: This item addresses only the aural (audio) warning. The visual gear
position indicating channels remain required per MEL 32-30-01.

# MEL 32-30-03 — Landing Gear Position Indicator Lights (Individual Green)

Category: C. Number installed: 3. Number required for dispatch: 2.

Each main and nose gear position is annunciated by an individual green
down-and-locked light. One individual green light may be inoperative provided:
(O) The flight crew confirms the affected gear down-and-locked using the
remaining indication and the alternate confirmation procedure of AMM 32-32-00
before landing.
(M) Verify the corresponding proximity sensor and downlock switch are
functional (target gap 1.5 to 2.5 mm) per AMM 32-31-00 and confirm the fault is
limited to the lamp/indicating channel per TSM 32-33.
Repair interval: 10 calendar days (Category C).
Placarding required: Placard the affected GEAR GREEN LIGHT INOP.

Note: A lamp test that fails to illuminate the affected light, with a confirmed
serviceable downlock signal, satisfies the (M) requirement for this item.

# MEL 32-30-04 — Landing Gear Position Indicator Lights (Red In-Transit / Unsafe)

Category: C. Number installed: 3. Number required for dispatch: 2.

The red in-transit (unsafe) indication may be inoperative for one gear provided:
(O) The flight crew observes gear transit timing (normal 10 to 12 seconds) and
confirms the associated green light logic on the unaffected channels.
(M) Confirm the red indication fault is isolated to the lamp or driver and does
not indicate a genuine unsafe condition per TSM 32-33.
Repair interval: 10 calendar days (Category C).
Placarding required: Placard the affected GEAR RED LIGHT INOP.

Caution: If a red unsafe indication is present and cannot be shown to be a lamp
or driver fault, the aircraft is not dispatchable under this item. Investigate
per TSM 32-32.

# MEL 32-31-01 — Nose Wheel Steering System

Category: C. Number installed: 1. Number required for dispatch: 0.

The nose wheel steering (NWS) system may be inoperative provided:
(O) The flight crew applies a maximum taxi crosswind limitation and uses
differential braking and asymmetric thrust for directional control during taxi.
Towing is required for congested ramp areas as directed by the ground handling
procedure.
(M) Deactivate and center the NWS actuator, install the steering bypass /
disconnect per AMM 32-31-00, and safety the disconnect. Placard NOSE WHEEL
STEERING INOP.
Repair interval: 10 calendar days (Category C).

Note: Rudder-pedal steering, where fitted as a separate low-authority function,
is addressed by MEL 32-31-02 and is not relieved by this item.

Caution: With NWS deactivated, verify the nose gear castoring is free and the
torque links are reconnected before releasing the aircraft. Refer to TSM 32-31
for actuator or valve faults.

# MEL 32-31-02 — Rudder-Pedal Nose Wheel Steering (Low-Authority)

Category: C. Number installed: 1. Number required for dispatch: 0.

The low-authority rudder-pedal steering function may be inoperative provided the
primary tiller steering remains available, or provided both are deactivated
under MEL 32-31-01.
(O) The flight crew is briefed that fine directional corrections via the rudder
pedals are unavailable and uses tiller steering for all turns.
(M) Confirm the rudder-pedal steering channel is isolated without affecting
rudder flight-control authority. Placard PEDAL STEERING INOP.
Repair interval: 10 calendar days (Category C).

Note: Confirm no cross-coupling fault exists between the pedal steering channel
and the tiller channel per TSM 32-31 before dispatch.

# MEL 32-31-03 — Nose Wheel Steering Angle Indication

Category: D. Number installed: 1. Number required for dispatch: 0.

The nose wheel steering angle indication (cockpit or maintenance display) may be
inoperative provided:
(O) The flight crew relies on visual reference and standard tiller technique;
no angle readout is required for normal operations.
(M) Confirm the steering angle transducer fault does not affect the steering
control loop per TSM 32-31.
Repair interval: 120 calendar days (Category D).
Placarding required: Placard NWS ANGLE IND INOP.

# MEL 32-32-01 — Landing Gear Gravity (Free-Fall) Extension Indication

Category: C. Number installed: 1. Number required for dispatch: 0.

The indication that confirms selection of the gravity (free-fall) extension
system may be inoperative provided:
(O) The flight crew is briefed that the free-fall extension, if required, must
be commanded by handle position and confirmed by the down-and-locked greens per
AMM 32-32-00, without reliance on the free-fall selection annunciator.
(M) Confirm the free-fall extension mechanism itself is serviceable and only the
selection indication has failed, per TSM 32-32.
Repair interval: 10 calendar days (Category C).
Placarding required: Placard FREE FALL SEL IND INOP.

Caution: The free-fall extension capability must remain fully functional. Relief
is granted only for the indication, never for the extension mechanism. Establish
the alternate procedure per AMM 32-32-00.

# MEL 32-32-02 — Landing Gear Manual Extension Handle Lock

Category: C. Number installed: 1. Number required for dispatch: 0.

The mechanical lock/stow on the manual (gravity) extension handle may be
inoperative provided:
(O) The flight crew verifies the handle is stowed and secured before each
flight.
(M) Secure the handle in the stowed position by approved alternate means and
confirm free travel to the extend position remains available per AMM 32-32-00.
Repair interval: 10 calendar days (Category C).
Placarding required: Placard MANUAL EXTENSION HANDLE LOCK INOP.

Note: Do not disable or obstruct the handle's travel to the extended position.
Any restriction of the free-fall path makes the aircraft not dispatchable.

# MEL 32-33-01 — Landing Gear Control and Interface Unit (LGCIU) Channel

Category: C. Number installed: 2. Number required for dispatch: 1.

The aircraft is equipped with two LGCIU channels, one of which supplies gear
sequencing and position data while the other provides redundancy. One LGCIU
channel may be inoperative provided:
(O) The flight crew notes that gear-position and door-sequencing data are
supplied by a single channel and monitors transit timing (10 to 12 seconds) on
each cycle.
(M) Confirm the remaining LGCIU channel passes the operational test per AMM Task
32-11-00-700-801 and isolate the failed channel per TSM 32-33.
Repair interval: 10 calendar days (Category C).
Placarding required: Placard LGCIU 1 (or 2) INOP.

Caution: Both LGCIU channels inoperative is not a dispatchable condition. Gear
sequencing and safe extension logic require at least one healthy channel.

# MEL 32-33-02 — Weight-on-Wheels (Air/Ground) Sensor

Category: C. Number installed: 2. Number required for dispatch: 1.

The weight-on-wheels (WOW / air-ground) sensing is provided by dual proximity
sensors per main gear leg. One WOW sensor per affected leg may be inoperative
provided:
(O) The flight crew is briefed that air/ground-dependent functions (e.g.,
ground spoiler arming logic, autobrake arming) are supplied by the remaining
sensor.
(M) Confirm the remaining WOW sensor target gap is within 1.5 to 2.5 mm and the
air/ground logic transitions correctly per AMM 32-31-00; isolate the failed
sensor per TSM 32-33.
Repair interval: 10 calendar days (Category C).
Placarding required: Placard WOW SENSOR (affected leg) INOP.

Note: A disagreement between WOW channels that cannot be isolated to a single
failed sensor is not dispatchable. Air/ground logic must be unambiguous.

# MEL 32-34-01 — Brake Temperature Monitoring System

Category: C. Number installed: 1 (system). Number required for dispatch: 0.

The brake temperature monitoring system (BTMS) with cockpit indication may be
inoperative provided:
(O) The flight crew applies conservative brake-cooling and turnaround
procedures, allowing standard minimum cooling times between landings, and does
not rely on measured brake temperature to reduce cooling periods.
(M) Confirm the fault is limited to the monitoring/indication function and does
not indicate an actual overheat condition per TSM 32-41.
Repair interval: 10 calendar days (Category C).
Placarding required: Placard BRAKE TEMP MON INOP.

Caution: Without brake temperature indication, a hot-brake condition may go
undetected. Apply the standard cooling schedule and inspect for fuse-plug
release before dispatch if a heavy braking event occurred.

# MEL 32-34-02 — Individual Brake Temperature Sensor

Category: C. Number installed: 4 (one per main wheel). Number required for dispatch: 3.

One individual brake temperature sensor may be inoperative provided:
(O) The flight crew notes the affected wheel position reads invalid and applies
the conservative cooling schedule for that position.
(M) Isolate the failed sensor and confirm the remaining sensors read valid per
TSM 32-41.
Repair interval: 10 calendar days (Category C).
Placarding required: Placard BRAKE TEMP SENSOR (wheel position) INOP.

# MEL 32-34-03 — Brake Fan / Cooling System

Category: C. Number installed: 4. Number required for dispatch: 2.

Brake cooling fans may be inoperative provided at least two remain serviceable
and symmetrically distributed:
(O) The flight crew extends the minimum brake-cooling turnaround time to the
value published for the reduced-fan configuration.
(M) Isolate the inoperative fan(s), confirm no electrical fault affects the
remaining fans, and verify symmetric cooling capability per TSM 32-41.
Repair interval: 10 calendar days (Category C).
Placarding required: Placard BRAKE FAN(S) (positions) INOP.

Note: Two inoperative fans on the same gear leg produce asymmetric cooling and
are not permitted. Distribute serviceable fans across both main legs.

# MEL 32-35-01 — Tire Pressure Indication System

Category: C. Number installed: 1 (system). Number required for dispatch: 0.

The tire pressure indication system (TPIS) with cockpit readout may be
inoperative provided:
(O) The flight crew is briefed that tire pressures are verified by manual gauge
check during the transit or daily inspection rather than by cockpit indication.
(M) Perform a manual tire pressure check on all wheels and record the values;
confirm the indication fault does not mask a low-pressure condition per TSM
32-41.
Repair interval: 10 calendar days (Category C).
Placarding required: Placard TIRE PRESS IND INOP.

Note: A tire found below the minimum servicing pressure is a separate defect and
is not relieved by this item.

# MEL 32-35-02 — Individual Tire Pressure Sensor

Category: D. Number installed: 6. Number required for dispatch: 5.

One individual tire pressure sensor may be inoperative provided:
(O) The affected wheel pressure is verified by manual gauge check before each
flight and recorded.
(M) Isolate the failed sensor and confirm the remaining channels read valid per
TSM 32-41.
Repair interval: 120 calendar days (Category D).
Placarding required: Placard TIRE PRESS SENSOR (wheel position) INOP.

# MEL 32-36-01 — Landing Gear Door (Main Gear)

Category: A. Number installed: (as configured). Number required for dispatch: (see proviso).

A main gear door may be dispatched in a degraded or removed condition only in
accordance with the Configuration Deviation List CDL 52-30-1, which specifies
the applicable performance penalties and speed limitations:
(O) The flight crew applies the airspeed and performance penalties published in
CDL 52-30-1 for the affected door configuration.
(M) Secure or remove the affected door per AMM 32-31-00 and CDL 52-30-1;
confirm door-sequencing logic does not inhibit gear operation and that transit
timing remains within 10 to 12 seconds.
Repair interval: Category A — as specified in CDL 52-30-1.
Placarding required: Placard GEAR DOOR (position) — DISPATCH PER CDL 52-30-1.

Caution: A door that fails to sequence and mechanically fouls gear travel is not
dispatchable. Isolate door-sequence faults per TSM 32-31 before applying CDL
relief.

# MEL 32-36-02 — Landing Gear Door Uplock Indication

Category: C. Number installed: 3. Number required for dispatch: 2.

A gear-door uplock position indication may be inoperative provided:
(O) The flight crew monitors normal gear/door transit timing (10 to 12 seconds)
and notes any abnormal drag or configuration warning.
(M) Confirm the door uplock is mechanically engaged and the fault is limited to
the indication channel per TSM 32-33.
Repair interval: 10 calendar days (Category C).
Placarding required: Placard GEAR DOOR UPLOCK IND (position) INOP.

# MEL 32-37-01 — Landing Gear Lever (Selector) Mechanical Lock / Downlock Override

Category: C. Number installed: 1. Number required for dispatch: 0.

The gear lever solenoid mechanical lock (which normally inhibits gear
retraction on the ground) may be inoperative provided:
(O) The flight crew exercises procedural care not to select gear up on the
ground and confirms the air/ground logic before retraction.
(M) Confirm the WOW / air-ground interlock (MEL 32-33-02) is fully serviceable —
this relief is not permitted with a WOW sensor also inoperative — and verify the
lever override function per AMM 32-31-00.
Repair interval: 10 calendar days (Category C).
Placarding required: Placard GEAR LEVER LOCK INOP.

Caution: This item may not be combined with MEL 32-33-02 (WOW sensor). The
air/ground interlock provides the remaining protection against inadvertent
ground retraction and must be intact.

# MEL 32-38-01 — Autobrake System

Category: C. Number installed: 1. Number required for dispatch: 0.

The autobrake system may be inoperative provided:
(O) The flight crew plans for manual braking on every landing and recomputes
landing distance without autobrake credit where the performance data require it.
(M) Deactivate the autobrake control and confirm normal (manual) braking and
anti-skid remain fully functional per AMM Task 32-11-00-700-801.
Repair interval: 10 calendar days (Category C).
Placarding required: Placard AUTOBRAKE INOP.

Note: With autobrake inoperative but anti-skid serviceable, no runway-surface
limitation applies beyond normal manual-braking performance planning. If
anti-skid is also inoperative, MEL 32-40-01 limitations govern.

# MEL 32-38-02 — Autobrake Mode Annunciation

Category: D. Number installed: 1. Number required for dispatch: 0.

The autobrake mode annunciation (LO / MED / MAX / RTO) may be inoperative
provided:
(O) The flight crew confirms the selected autobrake mode by knob position and
deceleration response.
(M) Confirm the annunciation fault does not affect autobrake command logic per
TSM 32-41.
Repair interval: 120 calendar days (Category D).
Placarding required: Placard AUTOBRAKE MODE ANNUN INOP.

# MEL 32-38-03 — Rejected-Takeoff (RTO) Autobrake Mode

Category: C. Number installed: 1. Number required for dispatch: 0.

The RTO autobrake mode may be inoperative provided:
(O) The flight crew briefs manual maximum braking for a rejected takeoff and
does not arm RTO.
(M) Confirm the RTO arming fault does not affect landing autobrake modes or
normal braking per TSM 32-41.
Repair interval: 10 calendar days (Category C).
Placarding required: Placard RTO AUTOBRAKE INOP.

Caution: A rejected takeoff with RTO autobrake unavailable requires prompt,
firm manual braking. Ensure the crew briefing reflects the increased pilot
workload.

# MEL 32-39-01 — Parking Brake

Category: A. Number installed: 1. Number required for dispatch: 1.

The parking brake is normally required. Dispatch with the parking brake
inoperative is permitted only where an approved ground procedure guarantees
positive aircraft restraint by alternate means:
(O) The flight crew ensures wheel chocks are installed at every stop where the
parking brake would otherwise be set, and coordinates with ground personnel for
pushback and engine start restraint.
(M) Confirm the parking brake accumulator and mechanical latch fault is isolated
and does not affect normal or alternate braking per TSM 32-41.
Repair interval: Category A — the aircraft may operate for the remainder of the
day of discovery; the item must be repaired before the next scheduled overnight.
Placarding required: Placard PARKING BRAKE INOP.

Caution: Never leave the aircraft unattended relying solely on hydraulic
pressure. Chocks are mandatory whenever the parking brake is inoperative.

# MEL 32-39-02 — Parking Brake Pressure Indication

Category: C. Number installed: 1. Number required for dispatch: 0.

The parking brake accumulator pressure indication may be inoperative provided:
(O) The flight crew uses chocks as the primary restraint and does not rely on
the pressure readout to confirm parking brake state.
(M) Confirm accumulator precharge and holding capability by test per AMM
29-00-00 and TSM 32-41; verify the fault is limited to the indication.
Repair interval: 10 calendar days (Category C).
Placarding required: Placard PARK BRK PRESS IND INOP.

# MEL 32-41-01 — Anti-Skid Per-Wheel Channel

Category: C. Number installed: 4. Number required for dispatch: 3.

The anti-skid protection is provided on a per-wheel basis. One anti-skid wheel
channel may be inoperative — with the remaining three channels serviceable —
provided:
(O) The flight crew recalculates landing performance for the degraded anti-skid
configuration and restricts operation to a dry or damp (not contaminated)
runway.
(M) Isolate the affected wheel's anti-skid channel, confirm the remaining
channels function per AMM Task 32-11-00-700-801, and verify no residual brake
drag on the isolated wheel per TSM 32-41.
Repair interval: 10 calendar days (Category C).
Placarding required: Placard ANTI-SKID CH (wheel position) INOP.

Note: Loss of more than one per-wheel channel reverts to MEL 32-40-01 (full
anti-skid inoperative) and its limitations.

# MEL 32-41-02 — Brake Wear Indicator

Category: D. Number installed: 4. Number required for dispatch: 3.

One brake wear indicator pin may be unreadable or inoperative provided:
(O) No specific flight-crew action is required beyond awareness.
(M) Verify remaining brake wear on the affected wheel by direct measurement per
AMM 32-31-00 and confirm the brake is within serviceable wear limits; record the
measurement.
Repair interval: 120 calendar days (Category D).
Placarding required: Placard BRAKE WEAR IND (wheel position) INOP.

Caution: A brake at or beyond the wear limit is a separate defect and is not
dispatchable regardless of the state of the wear indicator.

# MEL 32-42-01 — Alternate (Yellow) Brake System

Category: C. Number installed: 1. Number required for dispatch: 0.

The alternate/standby brake system may be inoperative provided the normal
(green, 3000 psi) brake system and anti-skid are fully serviceable:
(O) The flight crew is briefed that alternate braking and its accumulator
reserve are unavailable and that a loss of normal brake pressure would require
immediate action.
(M) Confirm the normal brake system, anti-skid, and parking brake are fully
serviceable per AMM Task 32-11-00-700-801; isolate the alternate system fault
per TSM 32-41.
Repair interval: 10 calendar days (Category C).
Placarding required: Placard ALTERNATE BRAKE INOP.

Caution: This relief is void if the normal brake system shows any degradation.
Both brake systems degraded is not a dispatchable condition.

# MEL 32-43-01 — Landing Gear Not-Locked Configuration Warning (Retraction Inhibit Cross-Check)

Category: B. Number installed: 1. Number required for dispatch: 0.

The configuration warning that cross-checks gear position against thrust-lever
and flap position may be inoperative provided:
(O) The flight crew explicitly verifies gear and flap configuration on each
approach and retraction, compensating for the absent automatic cross-check.
(M) Confirm the warning fault does not indicate a genuine unsafe gear condition
and is isolated per TSM 32-32.
Repair interval: 3 calendar days (Category B).
Placarding required: Placard GEAR CONFIG WARN INOP.

Caution: This is a Category B (3-day) item because the automatic protection
against an unsafe gear/flap configuration is lost. Crew vigilance is the only
remaining safeguard.

# MEL 32-44-01 — Landing Gear Retraction Time Monitoring

Category: D. Number installed: 1. Number required for dispatch: 0.

The maintenance function that monitors and records gear transit time may be
inoperative provided:
(O) No flight-crew action required; the crew observes transit qualitatively
(normal 10 to 12 seconds).
(M) Confirm actual transit timing is within limits by AMM Task 32-11-00-700-801
at the next convenient check; isolate the monitoring fault per TSM 32-31.
Repair interval: 120 calendar days (Category D).
Placarding required: Placard GEAR TRANSIT MON INOP.

# MEL 32-45-01 — Nose Gear Steering Interlock (Towing Protection)

Category: C. Number installed: 1. Number required for dispatch: 0.

The towing interlock that inhibits steering pressure during towing may be
inoperative provided:
(O) Ground personnel are briefed and towing is performed with the steering
bypass pin installed at all times.
(M) Confirm the steering bypass pin function per AMM 32-31-00 and verify the
interlock fault does not affect normal steering per TSM 32-31.
Repair interval: 10 calendar days (Category C).
Placarding required: Placard NWS TOW INTERLOCK INOP.

# MEL 32-46-01 — Gear Downlock Proximity Sensor (Redundant)

Category: C. Number installed: 6 (dual per leg). Number required for dispatch: 3 (one per leg minimum).

One redundant downlock proximity sensor per gear leg may be inoperative provided
at least one serviceable downlock sensor remains on each leg:
(O) The flight crew confirms three green down-and-locked indications before
landing and uses the alternate confirmation of AMM 32-32-00 if any doubt exists.
(M) Confirm the remaining downlock sensor per affected leg reads valid with a
target gap of 1.5 to 2.5 mm per AMM 32-31-00; isolate the failed sensor per TSM
32-32.
Repair interval: 10 calendar days (Category C).
Placarding required: Placard DOWNLOCK SENSOR (leg/channel) INOP.

Caution: Loss of both downlock sensors on any single leg removes down-and-locked
confirmation for that leg and is not dispatchable.

# MEL 32-47-01 — Landing Gear Uplock Proximity Sensor (Redundant)

Category: C. Number installed: 6 (dual per leg). Number required for dispatch: 3 (one per leg minimum).

One redundant uplock proximity sensor per gear leg may be inoperative provided
at least one serviceable uplock sensor remains on each leg:
(O) The flight crew monitors normal retraction timing (10 to 12 seconds) and
notes any residual in-transit indication after retraction.
(M) Confirm the remaining uplock sensor per affected leg reads valid with a
target gap of 1.5 to 2.5 mm per AMM 32-31-00; isolate the failed sensor per TSM
32-31.
Repair interval: 10 calendar days (Category C).
Placarding required: Placard UPLOCK SENSOR (leg/channel) INOP.

# MEL 32-48-01 — Brake Pressure Indication (Per System)

Category: C. Number installed: 2. Number required for dispatch: 1.

One brake pressure indication (normal or alternate system readout) may be
inoperative provided the corresponding brake system itself is serviceable:
(O) The flight crew relies on the remaining pressure indication and normal brake
pedal feel.
(M) Confirm the affected brake system delivers normal pressure (green system
nominal 3000 psi) by test per AMM 29-00-00; isolate the indication fault per TSM
32-41.
Repair interval: 10 calendar days (Category C).
Placarding required: Placard BRAKE PRESS IND (system) INOP.

# MEL 32-49-01 — Landing Gear Ground-Retraction Inhibit (Squat Switch Relay)

Category: B. Number installed: 1. Number required for dispatch: 0.

The squat-switch relay that inhibits gear retraction on the ground may be
inoperative provided the redundant air/ground interlock path and gear lever lock
remain serviceable:
(O) The flight crew confirms air/ground state before any retraction selection.
(M) Confirm the redundant inhibit path (WOW logic and gear lever lock, MEL
32-37-01) is fully serviceable — this item is not permitted concurrently with
MEL 32-33-02 or MEL 32-37-01 — and isolate the relay fault per TSM 32-31.
Repair interval: 3 calendar days (Category B).
Placarding required: Placard GEAR GND INHIBIT RELAY INOP.

Caution: At least one independent ground-retraction inhibit must remain intact.
Do not combine multiple inhibit-path reliefs.

# MEL 32-50-01 — Landing Gear Position Indicating (Standby / Backup Display)

Category: D. Number installed: 1. Number required for dispatch: 0.

The standby gear-position display (backup to the primary indicating panel) may
be inoperative provided the primary indication of MEL 32-30-01 is fully
serviceable:
(O) The flight crew uses the primary gear indication; no standby display is
required for normal operations.
(M) Confirm the standby display fault does not affect the primary indicating
channels per TSM 32-33.
Repair interval: 120 calendar days (Category D).
Placarding required: Placard GEAR STBY DISP INOP.

# MEL 32-51-01 — Body Gear Steering (Where Fitted)

Category: C. Number installed: 1. Number required for dispatch: 0.

Where a body/center gear steering function is fitted, it may be inoperative
provided:
(O) The flight crew observes the taxi-speed and turn-radius limitation published
for the body-steering-inoperative configuration.
(M) Center and deactivate the body gear steering actuator per AMM 32-31-00 and
confirm free castoring; isolate the fault per TSM 32-31.
Repair interval: 10 calendar days (Category C).
Placarding required: Placard BODY GEAR STEERING INOP.

# General Dispatch Notes

Note: Multiple simultaneous inoperative items must be assessed for interaction.
Where two items each remove a layer of a redundant protection (for example, a
WOW sensor and a ground-retraction inhibit), the combination may not be
dispatchable even though each item is individually relievable. The individual
item cautions identify the principal prohibited combinations; the operator's
maintenance control must review any combination not explicitly addressed.

Note: All operational tests referenced in this chapter default to AMM Task
32-11-00-700-801 unless a more specific task is cited. Hydraulic supply
verification defaults to AMM 29-00-00.

Caution: Reliefs granted by this MEL assume the underlying mechanical system is
airworthy. An MEL item never relieves a structural, hydraulic-leak, or
gear-will-not-lock condition. When in doubt, isolate the fault per the
applicable TSM chapter (32-31, 32-32, 32-33, or 32-41) before dispatch.

# Fault / Item Index

The following index maps common reported symptoms to the governing MEL item and
the primary troubleshooting reference.

- Gear position indicator dead (one channel) — MEL 32-30-01; TSM 32-33.
- Gear aural warning silent — MEL 32-30-02; TSM 32-33.
- Individual green down-lock light out — MEL 32-30-03; TSM 32-33.
- Red in-transit / unsafe light out — MEL 32-30-04; TSM 32-33 (rule out TSM 32-32).
- Nose wheel steering inoperative — MEL 32-31-01; TSM 32-31.
- Rudder-pedal steering fault — MEL 32-31-02; TSM 32-31.
- NWS angle indication fault — MEL 32-31-03; TSM 32-31.
- Free-fall selection indication fault — MEL 32-32-01; TSM 32-32; AMM 32-32-00.
- Manual extension handle lock fault — MEL 32-32-02; AMM 32-32-00.
- LGCIU channel fault — MEL 32-33-01; TSM 32-33; AMM Task 32-11-00-700-801.
- Weight-on-wheels sensor fault — MEL 32-33-02; TSM 32-33.
- Brake temperature monitoring fault — MEL 32-34-01; TSM 32-41.
- Individual brake temp sensor fault — MEL 32-34-02; TSM 32-41.
- Brake cooling fan fault — MEL 32-34-03; TSM 32-41.
- Tire pressure indication fault — MEL 32-35-01; TSM 32-41.
- Individual tire pressure sensor fault — MEL 32-35-02; TSM 32-41.
- Main gear door degraded/removed — MEL 32-36-01; CDL 52-30-1; TSM 32-31.
- Gear door uplock indication fault — MEL 32-36-02; TSM 32-33.
- Gear lever mechanical lock fault — MEL 32-37-01; AMM 32-31-00.
- Autobrake inoperative — MEL 32-38-01; TSM 32-41; AMM Task 32-11-00-700-801.
- Autobrake mode annunciation fault — MEL 32-38-02; TSM 32-41.
- RTO autobrake fault — MEL 32-38-03; TSM 32-41.
- Parking brake inoperative — MEL 32-39-01; TSM 32-41.
- Parking brake pressure indication fault — MEL 32-39-02; AMM 29-00-00; TSM 32-41.
- Anti-skid system inoperative (full) — MEL 32-40-01; TSM 32-41.
- Anti-skid per-wheel channel fault — MEL 32-41-01; TSM 32-41.
- Brake wear indicator unreadable — MEL 32-41-02; AMM 32-31-00.
- Alternate brake system inoperative — MEL 32-42-01; TSM 32-41.
- Gear configuration warning fault — MEL 32-43-01; TSM 32-32.
- Gear transit time monitoring fault — MEL 32-44-01; TSM 32-31.
- NWS towing interlock fault — MEL 32-45-01; TSM 32-31.
- Downlock proximity sensor (redundant) fault — MEL 32-46-01; TSM 32-32.
- Uplock proximity sensor (redundant) fault — MEL 32-47-01; TSM 32-31.
- Brake pressure indication fault — MEL 32-48-01; TSM 32-41; AMM 29-00-00.
- Ground-retraction inhibit relay fault — MEL 32-49-01; TSM 32-31.
- Standby gear-position display fault — MEL 32-50-01; TSM 32-33.
- Body gear steering fault — MEL 32-51-01; TSM 32-31.

# Revision Record

- Rev-18 (effective 2026-06-01): Added per-wheel anti-skid channel relief (MEL
  32-41-01), redundant uplock/downlock proximity sensor items (MEL 32-46-01,
  32-47-01), brake fan/cooling relief (MEL 32-34-03), and the ground-retraction
  inhibit relay item (MEL 32-49-01). Clarified prohibited combinations for the
  air/ground interlock family (MEL 32-33-02, 32-37-01, 32-49-01). Aligned all
  proximity sensor target-gap references to 1.5–2.5 mm per AMM 32-31-00.
- Rev-17 (effective 2026-02-01): Added tire pressure indication and individual
  tire pressure sensor items (MEL 32-35-01, 32-35-02). Updated cross-reference to
  CDL 52-30-1 for main gear door dispatch.
- Rev-16 (effective 2025-10-01): Introduced autobrake family items (MEL
  32-38-01, 32-38-02, 32-38-03) and alternate brake system relief (MEL 32-42-01).
  Standardized transit-time reference to 10–12 seconds.
- Rev-15 (effective 2025-06-01): Added LGCIU channel and weight-on-wheels sensor
  reliefs (MEL 32-33-01, 32-33-02). Added brake temperature monitoring items.
- Rev-14 (effective 2025-02-01): Baseline reissue. Established the general
  section, procedure-symbol definitions, and Category A/B/C/D repair intervals.
  Carried forward the position-indicating, anti-skid, and aural-warning items.

# End of ATA 32 Landing Gear MEL

Note: This document is controlled. Verify the revision (Rev-18) and effective
date (2026-06-01) against the master MEL register before use. Superseded
revisions must be removed from service.
