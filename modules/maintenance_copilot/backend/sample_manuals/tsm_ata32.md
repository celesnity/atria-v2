---
doc_type: TSM
title: Troubleshooting Manual — ATA 32 Landing Gear
revision: Rev-31
effective_date: 2026-05-20
ata_chapter: "32"
---

# TSM 32-00 — Using This Manual

This Troubleshooting Manual (TSM) covers the landing gear system (ATA 32),
including the main and nose landing gear, retraction and extension, position
indicating, wheels and brakes, anti-skid, nose-wheel steering, and the weight-on-
wheels (WoW) sensing network. It is written for line and base maintenance
technicians and must be used together with the applicable Aircraft Maintenance
Manual (AMM) tasks referenced throughout.

Each fault begins with the observed symptom and the associated maintenance
message or fault code reported by the landing gear control and interface unit
(LGCIU). Work the steps in order; do not skip a step because the fault "looks
obvious." Where a step calls out an AMM task, complete that task fully before
continuing. If the fault is intermittent, note the ambient conditions (OAT,
recent flight loads, runway condition) in the technical log so that trends can be
correlated across flights.

## How Fault Codes Are Structured

Fault codes in this manual use the form `32-XXYY`, where `XX` identifies the
sub-system group and `YY` identifies the specific fault within that group. For
example, `32-3101` is the first fault in the retraction group (32-31), and
`32-4101` is the first fault in the braking group (32-41). The LGCIU records the
code with a snapshot of the proximity sensor states and hydraulic pressures at
the moment of detection; retrieve this snapshot from the maintenance page before
clearing any code.

## Nominal Reference Values

Use these nominal values as the baseline for every diagnostic step. They are kept
consistent with the AMM. If a measured value falls outside the stated band, treat
the affected component as suspect before proceeding.

- Green hydraulic system pressure: 3000 psi (normal operating).
- Yellow (alternate) hydraulic system pressure: 3000 psi.
- Normal gear transit time (up or down): approximately 10–12 seconds.
- Proximity sensor target gap: 1.5–2.5 mm.
- Main tire pressure (unladen, cold): 205 psi nominal.
- Nose tire pressure (unladen, cold): 185 psi nominal.
- Shock strut extension (static, nominal gross weight): per AMM 32-11-00 chart.
- Brake accumulator pre-charge: 1000 psi nominal.
- Anti-skid transducer output: 0.5–1.0 V AC at wheel spin-up.

Warning: Never work on or near the landing gear with hydraulic power available
unless the gear is mechanically pinned with the down-lock safety devices
installed. Inadvertent retraction can cause fatal injury.

Caution: Depressurize the green and yellow systems and verify zero residual
pressure at the actuator before disconnecting any hydraulic line (AMM 29-00-00).

Note: Before dispatching an aircraft with an unresolved landing gear fault, check
the applicability of MEL 32-30-01 (position indicating), MEL 32-40-01 (anti-skid),
and MEL 32-30-02 (aural warning), together with any related placarding
requirements.

# TSM 32-10 — Fault Code Index

Use this index to locate the correct fault tree quickly. Each entry lists the
fault code, the short title, and the sub-system group.

- 32-3101 — Gear Fails to Retract (retraction, 32-31).
- 32-3102 — Up-Lock Will Not Release (retraction, 32-31).
- 32-3103 — Gear Door Fails to Close (retraction, 32-31).
- 32-3201 — Gear Fails to Extend (extension, 32-32).
- 32-3202 — Down-Lock Will Not Engage (extension, 32-32).
- 32-3203 — Landing Gear Lever Jam (extension, 32-32).
- 32-3301 — False or Intermittent Gear Position Indication (indicating, 32-33).
- 32-3302 — LGCIU Channel Disagree (indicating, 32-33).
- 32-3303 — Proximity Sensor Gap Out of Range (indicating, 32-33).
- 32-3401 — Gear Unsafe Warning in Flight (warning, 32-34).
- 32-3402 — Gear Aural Warning / Horn Inoperative (warning, 32-34).
- 32-3501 — Weight-on-Wheels Sensor Fault (sensing, 32-35).
- 32-3601 — Shock Strut Low or Flat (struts, 32-36).
- 32-3602 — Shock Strut Over-Compressed (struts, 32-36).
- 32-4101 — Brake Drags or Fails to Release (braking, 32-41).
- 32-4201 — Brake Temperature High (braking, 32-42).
- 32-4301 — Anti-Skid Fault (anti-skid, 32-43).
- 32-4401 — Tire Wear or Pressure Fault (wheels/tires, 32-44).
- 32-5101 — Nose-Wheel Steering Fault (steering, 32-51).
- 32-6101 — Hydraulic Leak at Actuator (hydraulics, 32-61).

# TSM 32-31 — Gear Fails to Retract

Fault code 32-3101: Retraction actuator does not extend.

Symptom: On gear-up selection, one main gear remains down or stops partway. The
crew reports no up-lock indication and, in most cases, an unsafe-gear warning.

Step 1: Check hydraulic pressure at the actuator (AMM 29-00-00). Nominal green
system pressure is 3000 psi. If pressure is low, resolve the hydraulic fault
before continuing.

Step 2: Inspect the retraction actuator wiring for continuity. Check the LGCIU
harness connector for bent pins, corrosion, and moisture ingress.

Step 3: Confirm that the up-lock is releasing and that the gear door has fully
opened to clear the retraction path. A partially open door will stall retraction
and set this code (see TSM 32-31 for 32-3103).

Step 4: If pressure and wiring are good, replace the actuator per AMM 32-31-00.

Step 5: After replacement, perform the operational test (AMM Task
32-11-00-700-801) and clear the fault code from the LGCIU. Confirm transit time
returns to the nominal 10–12 seconds.

Note: If the fault occurs only at high gross weight or high OAT, suspect marginal
hydraulic pressure rather than the actuator, and re-check the green system supply
per AMM 29-00-00.

## 32-3102 — Up-Lock Will Not Release

Fault code 32-3102: Up-lock hook remains engaged on gear-down selection.

Symptom: On gear-down selection, one gear stays retracted and locked up. The
crew reports one green missing and an unsafe indication. The up-lock unlock
solenoid may be heard to click without the gear moving.

Step 1: Verify green hydraulic pressure at 3000 psi and confirm the gear selector
reached the DOWN detent (AMM 29-00-00).

Step 2: Check the up-lock release solenoid for electrical continuity and correct
resistance. Inspect the connector for corrosion.

Step 3: Inspect the up-lock hook and roller for mechanical binding, corrosion, or
a broken return spring. Lubricate per AMM 32-31-00.

Step 4: If the up-lock still will not release, perform free-fall (alternate)
extension per AMM 32-32-00 to get the gear down for landing, then rectify on the
ground.

Step 5: Replace the up-lock actuator or solenoid as required (AMM 32-31-00) and
repeat the operational test (AMM Task 32-11-00-700-801).

Warning: Do not attempt to manually release a loaded up-lock hook without
relieving hydraulic pressure first. Stored energy in the strut can cause the gear
to fall rapidly.

## 32-3103 — Gear Door Fails to Close

Fault code 32-3103: Gear door not closed after retraction sequence.

Symptom: After gear-up, an amber door-open advisory persists, or increased
airframe noise and drag are reported. The LGCIU shows the door proximity sensor
in the OPEN state.

Step 1: Inspect the door proximity sensor target gap. Nominal gap is 1.5–2.5 mm;
adjust the target bracket if out of range (see 32-3303).

Step 2: Check the door actuator hydraulic supply and return lines for leaks or a
mis-seated cap left from a prior gear removal (AMM Task 32-11-00-000-801).

Step 3: Inspect the door hinge, rigging, and sequencing linkage for binding or a
bent rod. Re-rig the door per AMM 32-31-00 if the close position is out of
tolerance.

Step 4: If the cargo door seal interferes with door travel, refer to CDL 52-30-1
for any allowable dispatch condition and coordinate with structures.

Step 5: Replace the door actuator per AMM 32-31-00 if it fails to drive the door
to the fully closed and latched position. Retest per AMM Task 32-11-00-700-801.

# TSM 32-32 — Gear Fails to Extend

Fault code 32-3201: Gear does not reach down-and-locked on normal extension.

Symptom: On gear-down selection, one or more gear do not show green
down-and-locked within the normal transit time (approximately 12 seconds).

Step 1: Confirm the gear selector is in the DOWN position and the green
hydraulic system is pressurized (AMM 29-00-00).

Step 2: If normal extension fails, perform the free-fall (alternate) extension
per AMM 32-32-00 and confirm the gear reaches down-and-locked mechanically.

Step 3: If free-fall extension succeeds but normal extension fails, suspect the
selector valve or actuator. Inspect and replace the retraction actuator per
AMM 32-31-00 if defective.

Step 4: If free-fall extension also fails, inspect the down-lock mechanism and
the pivot for binding or a seized main pivot pin (AMM Task 32-11-00-000-801 for
access). Check the pivot pin against the wear limits in the AMM.

Step 5: After any component replacement, perform the operational test (AMM Task
32-11-00-700-801) and confirm the down-and-locked indication on both LGCIU
channels.

Caution: Free-fall extension is irreversible in flight without maintenance
action. After a free-fall extension, inspect the release mechanism and reset it
per AMM 32-32-00 before the next dispatch.

## 32-3202 — Down-Lock Will Not Engage

Fault code 32-3202: Gear extends but down-lock does not confirm.

Symptom: The gear reaches the down position but the green light does not
illuminate, or it shows amber transit. The down-lock proximity sensor does not
transition to LOCKED.

Step 1: Verify the gear is physically down by visual check through the wheel-well
sight glass.

Step 2: Inspect the down-lock over-center linkage and lock-stay for full travel.
A worn or fouled lock-stay will not go over-center. Lubricate and re-rig per
AMM 32-31-00.

Step 3: Check the down-lock proximity sensor target gap against 1.5–2.5 mm and
adjust the bracket if out of range (see 32-3303).

Step 4: Confirm the lock spring is intact and provides positive over-center
force. Replace a weak or broken spring per AMM 32-31-00.

Step 5: If the gear is confirmed mechanically down-and-locked but a single
indicator is inoperative, review dispatch under MEL 32-30-01 (Category C) with
the indicator placarded INOP.

## 32-3203 — Landing Gear Lever Jam

Fault code 32-3203: Gear selector lever will not move to the commanded position.

Symptom: The crew reports the landing gear lever is stuck in UP or DOWN and will
not move, or requires abnormal force.

Step 1: Confirm the lever solenoid down-lock (the lever cannot be raised on the
ground with WoW active). Verify the WoW signal state (see 32-3501) — a false
ground signal can inhibit lever movement.

Step 2: Check the manual override release on the lever mechanism per AMM
32-32-00. Do not force the lever.

Step 3: Inspect the lever mechanism and micro-switches for a jammed detent,
foreign object, or broken return spring.

Step 4: Replace the lever assembly or solenoid per AMM 32-32-00 if the jam is
internal. Retest per AMM Task 32-11-00-700-801.

Note: A lever jam combined with a WoW disagreement frequently points to the WoW
sensor rather than the lever; troubleshoot 32-3501 in parallel.

# TSM 32-33 — False or Intermittent Gear Position Indication

Fault code 32-3301: Disagreement between LGCIU proximity sensors.

Symptom: Gear position indication flickers, shows amber transit continuously, or
disagrees between the two LGCIU channels while the gear is mechanically
down-and-locked.

Step 1: Verify the gear is physically down-and-locked (visual check through the
wheel-well sight glass).

Step 2: Inspect the proximity sensor target gap. Nominal gap is 1.5–2.5 mm;
adjust the target bracket if out of range.

Step 3: Check the proximity sensor harness and connector for corrosion and
chafing. Repair or replace as required.

Step 4: If a single indicator remains inoperative and the gear is confirmed
down-and-locked, the aircraft may be dispatched under MEL 32-30-01 (Category C)
with the affected indicator placarded INOP. Establish the alternate procedure
before dispatch.

Step 5: If the indication remains erratic after sensor and harness checks,
suspect the LGCIU itself and proceed to 32-3302.

## 32-3302 — LGCIU Channel Disagree

Fault code 32-3302: LGCIU channel 1 and channel 2 report different gear states.

Symptom: The two independent LGCIU channels disagree on the same gear position,
producing an intermittent unsafe or transit indication that clears on power
cycle.

Step 1: Retrieve the fault snapshot from both LGCIU channels and compare the
recorded proximity sensor states.

Step 2: Swap the suspect proximity sensor between channels (if the design allows)
or substitute a known-good sensor to isolate whether the fault follows the sensor
or the channel.

Step 3: Inspect the inter-channel wiring and the LGCIU power supply. A marginal
28 V DC bus can cause a single channel to drop out.

Step 4: If the disagreement follows one channel, replace that LGCIU per the AMM
and re-run the operational test (AMM Task 32-11-00-700-801).

Step 5: Clear the fault codes and verify both channels agree through a full
retraction/extension cycle on jacks.

Caution: Do not dispatch with an unresolved LGCIU channel disagree unless the
specific condition is covered by MEL 32-30-01; a dual-channel fault removes
redundancy on gear position sensing.

## 32-3303 — Proximity Sensor Gap Out of Range

Fault code 32-3303: Measured proximity target gap outside 1.5–2.5 mm.

Symptom: A proximity sensor reads inconsistently, or the built-in test flags a
gap fault. The gear indication may drop out under vibration or thermal cycling.

Step 1: Measure the target-to-sensor gap with a non-ferrous feeler gauge. Nominal
is 1.5–2.5 mm.

Step 2: If the gap is too large, shim or adjust the target bracket per AMM
32-31-00. If too small, back off the bracket to avoid contact during gear cycling.

Step 3: Inspect the target for corrosion, cracking, or a loose mounting screw.
Replace the target if damaged.

Step 4: Re-measure the gap through a full gear cycle to confirm it stays in band
under load. Torque the bracket hardware to the AMM value.

Step 5: Clear the fault and confirm stable indication on both channels.

# TSM 32-34 — Gear Unsafe Warning and Aural Warning

Fault code 32-3401: Gear unsafe warning annunciated in flight.

Symptom: A red gear-unsafe warning illuminates in flight with the gear selected
UP, or during approach with the gear selected DOWN and one gear not confirmed
locked.

Step 1: Correlate the warning with the individual gear position indications.
Determine whether the warning is a true un-locked condition or a false indication
(cross-check TSM 32-33).

Step 2: If in flight and the gear is selected DOWN with no down-lock, perform
free-fall extension per AMM 32-32-00 and confirm the gear down mechanically.

Step 3: On the ground, verify the actual lock state visually and via both LGCIU
channels. Rectify the underlying lock or sensor fault (32-3202 or 32-3303).

Step 4: Inspect the warning logic inputs — WoW state, lever position, and each
gear proximity sensor. A false input from any one can trigger the warning
(see 32-3501).

Step 5: After rectification, cycle the gear on jacks and confirm the warning
clears through the full envelope. Retest per AMM Task 32-11-00-700-801.

Warning: Treat every in-flight gear-unsafe warning as genuine until proven
otherwise. Do not suppress or pull the warning circuit breaker to silence it.

## 32-3402 — Gear Aural Warning / Horn Inoperative

Fault code 32-3402: Landing gear aural warning does not sound when required.

Symptom: The gear warning horn fails to sound with flaps in the landing
configuration and gear not down-and-locked, or fails the pre-flight test.

Step 1: Perform the aural warning self-test per AMM 32-32-00 and note whether any
tone is produced.

Step 2: Check the warning horn/speaker and its drive circuit for continuity.
Inspect the associated circuit breaker.

Step 3: Verify the input logic — throttle position, flap position, and gear
position signals must all be valid for the warning to arm.

Step 4: Replace the aural warning unit or speaker per the AMM if the drive
circuit is confirmed good.

Step 5: If the aural warning cannot be restored before dispatch, review MEL
32-30-02 for the allowable condition and any operational restriction, and placard
accordingly.

Note: The visual gear-unsafe warning and the aural warning are independent; an
inoperative horn does not by itself justify dispatch without reference to MEL
32-30-02.

# TSM 32-35 — Weight-on-Wheels Sensing

Fault code 32-3501: Weight-on-wheels (WoW) sensor fault.

Symptom: Systems that depend on air/ground logic misbehave — the gear lever
inhibit, cabin pressurization, auto-brake arming, or spoiler deployment behave as
if the aircraft is in the wrong state. The LGCIU logs a WoW disagreement.

Step 1: Retrieve the WoW signal state from each main gear proximity/compression
switch and compare left, right, and nose.

Step 2: Inspect the WoW sensor and its target on the shock strut torque link.
Confirm the strut is at the correct static extension (a low strut can hold a false
ground signal — see 32-3601).

Step 3: Check the WoW sensor target gap against 1.5–2.5 mm and adjust if out of
range (see 32-3303).

Step 4: Inspect the WoW wiring to the LGCIU and to the downstream systems for
chafing and corrosion.

Step 5: Replace the WoW sensor per the AMM if isolated as faulty, then verify
air/ground transitions on jacks per AMM Task 32-11-00-700-801.

Caution: An incorrect WoW signal can inhibit gear retraction on the ground or,
worse, permit it. Confirm correct air/ground indication before applying hydraulic
power to the gear.

# TSM 32-36 — Shock Strut Faults

Fault code 32-3601: Shock strut low or flat (under-inflated).

Symptom: The affected strut shows less than nominal static extension; the aircraft
sits low on one corner, or the strut bottoms during taxi. WoW logic may read
ground when the strut is under-extended.

Step 1: Measure the exposed strut dimension (chrome showing) and compare against
the AMM 32-11-00 servicing chart for the current gross weight and OAT.

Step 2: Inspect for external hydraulic fluid leakage at the strut seal (see also
32-6101). A flat strut with fluid loss indicates a seal failure.

Step 3: Service the strut with nitrogen and hydraulic fluid to the correct
extension per AMM 32-11-00. Do not overfill.

Step 4: If the strut will not hold pressure, remove and replace the strut or
overhaul the gland seal per AMM Task 32-11-00-000-801.

Step 5: After servicing, re-check WoW indication (32-3501) and static extension,
then release the aircraft.

Warning: A shock strut is charged with high-pressure nitrogen. Never loosen the
charging valve or the gland nut before fully discharging the strut per AMM
32-11-00. Explosive release of a component can be fatal.

## 32-3602 — Shock Strut Over-Compressed

Fault code 32-3602: Shock strut over-serviced or hydraulically locked high.

Symptom: The strut shows more than nominal extension, the ride is harsh, or the
strut does not compress normally under load. WoW may read air on the ground.

Step 1: Measure the exposed strut dimension against the AMM 32-11-00 chart. Excess
extension usually indicates over-inflation with nitrogen.

Step 2: Bleed nitrogen to bring the strut to the correct static extension per AMM
32-11-00.

Step 3: If the strut remains high after bleeding gas, suspect a hydraulic lock or
an incorrect fluid/gas ratio. Re-service the strut per AMM 32-11-00.

Step 4: Confirm the WoW signal transitions correctly under load after servicing
(32-3501).

Step 5: Re-check strut extension after a short taxi to confirm it settles to the
nominal value.

# TSM 32-41 — Brake Drags or Fails to Release

Fault code 32-4101: Residual brake pressure after release.

Symptom: A wheel is hot after taxi, or the crew reports asymmetric braking.

Step 1: Check for residual hydraulic pressure at the brake (AMM 29-00-00).
Bleed the brake circuit if air is suspected (AMM 32-42-00).

Step 2: Inspect the brake hydraulic lines — including any lines capped during a
prior gear removal (AMM Task 32-11-00-000-801) — for a blockage or a
mis-seated cap.

Step 3: If pressure releases correctly but drag persists, inspect the brake
assembly for a seized piston and overhaul per AMM 32-42-00.

Step 4: Check the brake accumulator pre-charge (nominal 1000 psi). A failed
accumulator can hold residual pressure after release.

Step 5: After rectification, verify free wheel rotation and confirm no residual
drag during a taxi check. Retest per AMM Task 32-11-00-700-801.

Note: Persistent single-wheel drag often correlates with a high brake temperature
event; if so, also work 32-4201.

# TSM 32-42 — Brake Temperature High

Fault code 32-4201: Brake temperature exceeds monitored limit.

Symptom: The brake temperature monitoring system (BTMS) shows one wheel
significantly hotter than the others, or an over-temperature advisory is
annunciated after landing or a rejected takeoff.

Step 1: Allow the brakes to cool and record the peak temperatures from each wheel
position for trend analysis.

Step 2: If a single wheel runs hot, inspect that brake for drag (work 32-4101) and
check the anti-skid function on that wheel (32-4301).

Step 3: Inspect the brake heat pack wear pins against the AMM 32-42-00 wear
limits. A worn or unevenly worn pack degrades heat rejection.

Step 4: Check the BTMS sensor and wiring for that wheel; a faulty sensor can
report a false high temperature. Compare against an infrared spot check.

Step 5: Replace the brake unit or temperature sensor per AMM 32-42-00 as isolated,
then confirm balanced temperatures on a subsequent taxi.

Caution: Do not dispatch with brakes above the AMM cooling schedule temperature.
Hot brakes reduce rejected-takeoff energy capacity and can cause tire fuse-plug
release.

# TSM 32-43 — Anti-Skid Fault

Fault code 32-4301: Anti-skid system fault or channel drop-out.

Symptom: An anti-skid fault advisory is annunciated, or the crew reports poor
braking, wheel skid, or asymmetric deceleration. One anti-skid channel may show
inoperative on the maintenance page.

Step 1: Perform the anti-skid self-test per AMM 32-42-00 and identify the failing
channel or wheel.

Step 2: Inspect the wheel-speed transducer for the affected wheel. Nominal output
is 0.5–1.0 V AC at spin-up. Replace a transducer with low or no output.

Step 3: Check the transducer wiring and the anti-skid control unit connector for
corrosion and continuity.

Step 4: Verify the anti-skid control valve for that wheel operates and returns
correctly. Replace per AMM 32-42-00 if seized.

Step 5: If the fault cannot be cleared before dispatch, review MEL 32-40-01 for
the allowable dispatch condition, associated performance penalty, and required
placard.

Warning: With anti-skid inoperative, braking must be applied with care to avoid
tire burst and loss of directional control. Observe the MEL 32-40-01 operational
limitations.

# TSM 32-44 — Tire Wear or Pressure Fault

Fault code 32-4401: Tire pressure low or tread wear beyond limit.

Symptom: A tire pressure indication reads low, a tire is visibly worn or damaged,
or the tire pressure monitoring system flags a slow leak.

Step 1: Measure cold tire pressure and compare against nominal — 205 psi for main
tires, 185 psi for the nose tire. Correct pressure per AMM 32-42-00.

Step 2: Inspect the tread for wear against the AMM 32-42-00 groove-depth limit,
and inspect for cuts, flat spots, or exposed cord. Replace if beyond limits.

Step 3: If a tire loses pressure repeatedly, inspect the valve core, wheel seal,
and fusible plugs for leakage. Replace the wheel/tire assembly per AMM 32-42-00 as
required.

Step 4: After a tire change, torque the axle nut and re-check pressure after the
tire has stabilized.

Step 5: Inspect the mating tire on the same axle for matched wear; replace in
pairs where the AMM requires it.

Note: A single low tire on a dual-wheel gear overloads its partner. Do not defer a
confirmed slow leak without reference to the MEL.

# TSM 32-51 — Nose-Wheel Steering Fault

Fault code 32-5101: Nose-wheel steering inoperative or erratic.

Symptom: The nose wheel does not respond to the tiller or rudder-pedal steering,
steers in the wrong direction, or oscillates (shimmy) during taxi.

Step 1: Confirm the steering system is armed (WoW active and correct — see
32-3501) and that hydraulic pressure is available at 3000 psi (AMM 29-00-00).

Step 2: Check the steering control valve and feedback (follow-up) linkage for
correct rigging and free movement per AMM 32-32-00.

Step 3: Inspect the torque links (scissors) and the shimmy damper for wear and
correct fluid level. A worn damper is a common cause of shimmy.

Step 4: Verify the steering angle transducer output and wiring to the steering
control unit. Replace a faulty transducer per the AMM.

Step 5: If steering remains erratic, replace the steering control valve or
actuator per AMM 32-32-00, then perform a low-speed taxi check.

Caution: Before towing, confirm the steering bypass (towing) pin is installed as
required. Steering a gear with the system pressurized during towing can damage the
steering actuator.

# TSM 32-61 — Hydraulic Leak at Actuator

Fault code 32-6101: External hydraulic leakage at a landing gear actuator.

Symptom: Hydraulic fluid is found in the wheel well or on the gear, green or
yellow system quantity is decreasing, or pressure will not hold during a gear
cycle.

Step 1: Identify the leaking component — retraction actuator, door actuator, brake
line, or strut gland — and confirm the affected system (green or yellow) per AMM
29-00-00.

Step 2: Depressurize the affected system and verify zero residual pressure before
touching any fitting (AMM 29-00-00).

Step 3: For a fitting or B-nut leak, inspect the seal and re-torque to the AMM
value. Do not over-torque.

Step 4: For a rod-seal or gland leak at the retraction actuator, replace the
actuator per AMM 32-31-00. For a strut gland leak, see 32-3601.

Step 5: After repair, refill and bleed the system (AMM 29-00-00), then cycle the
gear and confirm no leak and a normal 10–12 second transit time (AMM Task
32-11-00-700-801).

Warning: High-pressure hydraulic fluid can inject through skin. Never search for a
leak with bare hands; use cardboard or a mirror with the system pressurized only
as the AMM directs.

# TSM 32-90 — General Diagnostic Notes

The following notes apply across the sub-systems above and help avoid repeat
findings and no-fault-found removals.

- Always retrieve and record the LGCIU fault snapshot before clearing any code.
  The recorded proximity states and pressures at the moment of the fault are the
  single most useful diagnostic input.
- When two faults appear together (for example a WoW disagreement and a lever
  jam), suspect a common upstream cause — usually a shock strut extension or a
  sensor gap out of tolerance — before condemning multiple line-replaceable units.
- After any component change on the gear, complete the full operational test per
  AMM Task 32-11-00-700-801 on jacks. A partial test can leave a rigging or lock
  fault undetected until the next flight.
- Keep servicing consistent with the AMM values. A strut, tire, or accumulator
  serviced away from nominal will drift back into a fault and generate repeat
  write-ups.
- For access-intensive work, plan the gear removal per AMM Task 32-11-00-000-801
  and cap all open lines immediately to prevent contamination and the mis-seated-
  cap faults described in 32-3103 and 32-4101.

Note: Where a fault cannot be cleared before dispatch, the applicable MEL entry
(32-30-01 position indicating, 32-40-01 anti-skid, or 32-30-02 aural warning) and,
for structural door-seal conditions, CDL 52-30-1, govern whether dispatch is
permitted and what placards and procedures apply. Never invent a dispatch relief
that is not in the MEL or CDL.

# TSM 32-99 — Revision Record

This section records the change history of this manual. The current revision is
Rev-31, effective 2026-05-20.

- Rev-31 (2026-05-20): Major expansion. Added fault trees for up-lock release
  (32-3102), gear door close (32-3103), down-lock engage (32-3202), lever jam
  (32-3203), LGCIU channel disagree (32-3302), proximity gap (32-3303),
  in-flight unsafe warning (32-3401), aural warning (32-3402), WoW sensor
  (32-3501), shock strut low/over-compressed (32-3601/3602), brake temperature
  (32-4201), anti-skid (32-4301), tire wear/pressure (32-4401), nose-wheel
  steering (32-5101), and hydraulic leak at actuator (32-6101). Added fault-code
  index (32-10) and general diagnostic notes (32-90). Cross-references to MEL
  32-30-02 and CDL 52-30-1 introduced.
- Rev-30 (2026-01-15): Updated proximity sensor gap tolerance to 1.5–2.5 mm to
  align with AMM 32-31-00. Clarified free-fall reset requirement in 32-32.
- Rev-29 (2025-09-02): Added MEL 32-30-01 dispatch guidance to the position
  indicating fault tree (32-3301). Corrected nominal transit time to 10–12 s.
- Rev-28 (2025-04-20): Initial issue of the ATA 32 landing gear troubleshooting
  content covering retraction (32-3101), extension (32-3201), indication
  (32-3301), and brake drag (32-4101).

End of Troubleshooting Manual — ATA 32 Landing Gear (Rev-31).
