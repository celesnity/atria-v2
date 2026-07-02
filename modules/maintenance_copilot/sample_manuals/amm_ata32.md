---
doc_type: AMM
title: Landing Gear — Main Gear Removal/Installation
revision: Rev-42
effective_date: 2026-05-01
ata_chapter: "32"
---

# 32-00-00 Landing Gear — General

The landing gear system consists of two main landing gear (MLG) assemblies and
one nose landing gear (NLG) assembly. Each MLG is a cantilever, oleo-pneumatic
shock strut retracting inboard into the wheel well. Retraction and extension are
powered by the green hydraulic system (AMM 29-00-00); an alternate free-fall
extension is available (AMM 32-32-00).

Warning: The landing gear can move without warning when hydraulic pressure is
applied. Before any work in a wheel well, install the ground safety lock pins
(down-lock pins) in all three gear and attach the DO-NOT-OPERATE warning
placards to the flight-deck gear selector.

Caution: Do not depressurize the shock strut without first supporting the
aircraft on jacks. Sudden strut collapse can cause injury and structural damage.

## 32-00-00 Purpose and Scope

This chapter covers the removal, installation, servicing, and functional testing
of the landing gear and its principal sub-assemblies: the shock strut, the
retraction actuator, the down-lock and up-lock mechanisms, the wheels and tires,
the brakes, and the position-indicating sensors. Wiring interfaces to the
landing gear control and interface unit (LGCIU) are covered here only to the
extent required to remove and install gear components; full electrical
troubleshooting is in TSM 32-33.

The following related chapters are referenced throughout:
- AMM 12-21-00 — Lubrication (greases and application intervals).
- AMM 29-00-00 — Hydraulic power (pressurizing and depressurizing).
- AMM 32-31-00 — Retraction actuator removal/installation.
- AMM 32-32-00 — Free-fall (alternate) extension system.
- AMM 32-42-00 — Wheels and brakes.
- TSM 32-31, TSM 32-32, TSM 32-33, TSM 32-41 — troubleshooting.
- MEL 32-30-01, MEL 32-40-01 — dispatch relief.

## 32-00-00 System Description

Each main gear assembly comprises the following major components:
- Shock strut (oleo-pneumatic), providing energy absorption on touchdown and
  taxi. The strut is charged with dry nitrogen over hydraulic fluid.
- Main pivot pin and bushings at the wing rear spar, about which the gear
  rotates between the stowed (up) and deployed (down) positions.
- Retraction actuator, a double-acting hydraulic cylinder driving the gear.
- Down-lock and up-lock mechanisms with over-center linkages, each with a
  proximity sensor reporting lock status to the LGCIU.
- Torque links (scissors) maintaining wheel alignment while allowing strut
  compression.
- Axle, wheels, tires, and multi-disc brake units (AMM 32-42-00).

Nominal system data:
- Green hydraulic system pressure: 3000 psi (206 bar).
- Normal gear transit time, up or down: 10–12 seconds.
- Shock strut nitrogen charge (unladen, on jacks): see the strut servicing
  chart in Task 32-00-00-610-801.
- MLG assembly mass: approximately 310 kg (683 lb).

## 32-00-00 Safety Summary

Read this summary before any task in this chapter.

Warning: Gear retraction with personnel in the wheel well is fatal. Never apply
hydraulic power with the ground safety pins removed unless a functional test is
in progress and the wheel wells are confirmed clear.

Warning: The shock strut and tires are pressurized. A failed strut seal or an
over-inflated tire can release parts at lethal velocity. Stand clear of the tire
plane of rotation during inflation and never exceed the servicing pressures.

Caution: Hydraulic fluid is a skin and eye irritant. Wear gloves and eye
protection. Clean spills immediately; hydraulic fluid degrades some seals and
paints.

Caution: Many gear fasteners are single-use (self-locking nuts, cotter pins).
Do not re-use removed locking hardware. Discard and replace with new parts.

## Task 32-00-00-910-801 — Landing Gear Ground Safety Precautions

1. Confirm chocks are installed at the nose and both main wheels.
2. Install the down-lock (ground) safety pins in the MLG and NLG. Verify the
   red REMOVE-BEFORE-FLIGHT streamers are attached.
3. Install the DO-NOT-OPERATE placard on the gear selector handle.
4. If hydraulic work is required, depressurize the green system per
   AMM 29-00-00 and verify zero pressure on the ground service panel gauge.
5. Record the pin installation in the aircraft technical log.

## Task 32-00-00-580-801 — Aircraft Jacking for Gear Work

Warning: Jack only at the approved jacking points. Jacking off-point can buckle
the fuselage frames or wing structure.

Tooling:
- Wing jacks (2), rated 15 tonne, P/N 07-JAK-02.
- Nose/tail jack (1), rated 8 tonne, P/N 07-JAK-05.
- Jack pad adapters, P/N 07-JAK-11.

1. Perform the ground safety precautions (Task 32-00-00-910-801).
2. Verify the aircraft is defuelled or within the jacking weight and balance
   limits.
3. Position the two wing jacks under the approved wing jacking points and the
   nose jack under the forward fuselage jacking point.
4. Raise all jacks simultaneously in small increments, keeping the aircraft
   level, until the tires are clear of the ground.
5. Install the jack locking collars (down-locks on the jack rams).
6. Confirm the aircraft is stable before beginning gear work.

## Task 32-00-00-610-801 — Shock Strut Servicing (Nitrogen and Fluid)

Perform when the strut extension is out of limits, after a strut seal
replacement, or at the scheduled servicing interval.

Warning: Never loosen the strut charging valve while the strut is pressurized
except through the approved bleed procedure. The valve can eject at high energy.

Tooling and consumables:
- Nitrogen servicing cart with regulator, 0–3000 psi.
- Hydraulic fluid, MIL-PRF-83282 (or approved equivalent).
- Strut extension gauge / scale, P/N 32-TLG-19.

1. Place the aircraft on jacks (Task 32-00-00-580-801) so the strut is fully
   extended and unladen.
2. Slowly release the nitrogen charge through the charging valve until the
   strut is depressurized.
3. Depress the strut fully, top up hydraulic fluid to the fill port level, and
   allow trapped air to escape.
4. Re-install the charging valve core and charge with dry nitrogen to the
   pressure shown on the servicing chart for the measured ambient temperature.
5. Measure the exposed (shiny) portion of the strut piston against the
   extension limits. Re-service if outside limits.
6. Leak-check the charging valve with approved leak-detection fluid.

Strut extension limits (unladen, on jacks):
- Nominal exposed piston: 180 mm ± 10 mm at 15 °C.
- Adjust the target by +2 mm for every 10 °C above 15 °C.
- Reject and investigate for internal leakage if the strut will not hold the
  serviced pressure for 24 hours.

# 32-11-00 Main Landing Gear

The main landing gear pivots about the main pivot pin at the wing rear spar. The
retraction actuator (AMM 32-31-00) drives the gear between the up-lock and
down-lock positions. Position is sensed by three proximity sensors reported to
the landing gear control and interface unit (LGCIU) and displayed to the crew;
faults in that indicating path are addressed by MEL 32-30-01 and TSM 32-31.

## 32-11-00 Component Location

The MLG assembly is accessed through the main wheel well with the gear in the
down position. Principal component locations:
- Main pivot pin: at the top of the gear leg, at the wing rear spar fitting.
- Retraction actuator: forward of the gear leg, between the leg and the spar.
- Down-lock link and proximity sensor: on the aft side of the leg.
- Brake hydraulic lines: routed along the inboard face of the leg to the axle.
- LGCIU proximity-sensor harness: on the disconnect bracket at the wheel-well
  ceiling.

## Task 32-11-00-000-801 — Removal of the Main Landing Gear

Warning: Make sure the aircraft is on jacks and the gear is safetied before
removal. Depressurize the hydraulic system per AMM 29-00-00.

Caution: The MLG assembly weighs approximately 310 kg (683 lb). Use the
approved gear sling and an overhead hoist rated for at least 500 kg. Do not
attempt to support the assembly by hand.

Tooling and consumables:
- Main gear sling, P/N 32-SLG-11.
- Overhead hoist, 500 kg minimum.
- Pin extractor kit, P/N 32-TLG-07.
- Hydraulic line caps, P/N 29-CAP-04 (qty 4).
- Connector dust caps, P/N 32-CAP-11 (qty 2).
- New pivot-pin nut and cotter pin.

1. Perform the ground safety precautions (Task 32-00-00-910-801).
2. Place the aircraft on jacks (Task 32-00-00-580-801).
3. Remove the retraction actuator (AMM 32-31-00).
4. Disconnect the brake hydraulic lines and cap them. Cap the mating fittings on
   the gear leg to prevent contamination.
5. Disconnect the LGCIU proximity-sensor harness at the disconnect bracket and
   protect the connector with a dust cap.
6. Attach the gear sling to the two lifting lugs and take up the slack with the
   hoist until the sling is just load-bearing.
7. Support the gear leg and remove the main pivot pin using the pin extractor
   kit. Retain the pin, bushings, and shims for inspection.
8. Lower the gear clear of the wheel well and transfer it to the gear transport
   dolly.
9. Fit protective covers to the exposed spar fitting bores.

## Task 32-11-00-400-801 — Installation of the Main Landing Gear

Install in reverse order of removal (Task 32-11-00-000-801). Note the following:

1. Inspect the main pivot pin and bushings for scoring, corrosion, and wear
   before installation. Replace any part outside limits (see the wear limits
   below).
2. Lubricate the pivot pin and bushings with grease per AMM 12-21-00.
3. Align the gear leg with the pivot lugs and install the main pivot pin.
4. Install the shims to remove free play, then torque the pivot pin nut to
   1200 in-lb and install a new cotter pin.
5. Reconnect the brake hydraulic lines (AMM 32-42-00) and the LGCIU harness.
6. Install the retraction actuator (AMM 32-31-00).
7. Bleed the brake and retraction hydraulic circuits (AMM 29-00-00).
8. Remove the protective covers and confirm all connectors are fully seated.

## Task 32-11-00-700-801 — Main Landing Gear Operational Test

Perform after any installation or when troubleshooting a retraction fault
(TSM 32-31).

1. Remove the ground safety pins and stow them.
2. Pressurize the green hydraulic system (AMM 29-00-00).
3. On jacks, cycle the gear UP and DOWN three times. Confirm smooth travel,
   positive up-lock and down-lock engagement, and three green down-and-locked
   indications on the flight deck.
4. Confirm no hydraulic leakage at the actuator, pivot, or brake lines.
5. Confirm the LGCIU reports no active landing-gear maintenance messages.
6. Reinstall the ground safety pins on completion.

## Task 32-11-00-220-801 — Main Landing Gear Detailed Inspection

Perform at the scheduled structural inspection interval or after a hard landing.

1. Clean the gear leg and inspect for corrosion, cracks, and impact damage.
2. Inspect the pivot lugs and pin bores for elongation and fretting.
3. Check the torque links (scissors) for free play at the apex joint; the
   maximum lateral play at the axle is 0.50 mm.
4. Inspect the down-lock and up-lock over-center links for wear and correct
   over-center travel.
5. Inspect all hydraulic lines and unions for chafing, leakage, and security.
6. Verify the proximity-sensor targets and brackets are secure and undamaged.
7. Record all findings; rectify defects before returning the gear to service.

## Main Pivot Pin — Wear Limits

- Pin outside diameter: 49.95–50.00 mm nominal; reject below 49.90 mm.
- Bushing inside diameter: 50.02–50.08 mm nominal; reject above 50.15 mm.
- Maximum radial free play at the axle, gear installed: 0.25 mm.
- Any corrosion pitting deeper than 0.05 mm on the pin bearing surface is cause
  for rejection.
- Any crack, regardless of length, is cause for rejection.

## Torque Values — Main Landing Gear

- Main pivot pin nut: 1200 in-lb.
- Retraction actuator rod-end pin nut: 900 in-lb (see AMM 32-31-00).
- Torque-link apex bolt: 300 in-lb.
- Axle nut: 650 in-lb, then align to the next cotter-pin slot.
- Brake union B-nuts: 250 in-lb.

# 32-21-00 Nose Landing Gear

The nose landing gear retracts forward into the nose wheel well. It carries the
steering actuator and the taxi/takeoff light. Nose gear removal follows the same
general precautions as the main gear.

## Task 32-21-00-000-801 — Removal of the Nose Landing Gear

Warning: The nose gear can retract forward under hydraulic power. Confirm the
ground safety pin is installed and the DO-NOT-OPERATE placard is fitted.

1. Perform the ground safety precautions (Task 32-00-00-910-801).
2. Place the aircraft on jacks (Task 32-00-00-580-801) with the nose jack
   supporting the forward fuselage.
3. Disconnect and cap the steering hydraulic lines.
4. Disconnect the taxi-light and steering electrical harnesses.
5. Support the gear with the nose-gear sling and remove the trunnion pins.
6. Lower the gear clear of the wheel well.

## Task 32-21-00-400-801 — Installation of the Nose Landing Gear

Install in reverse order of removal. Torque the trunnion pin nuts to 800 in-lb
and install new cotter pins. Bleed the steering circuit (AMM 29-00-00) and
perform a steering operational test before returning to service.

# 32-31-00 Retraction Actuator

The retraction actuator is a double-acting hydraulic cylinder. Loss of actuator
function is a common cause of a gear that fails to retract or extend
(TSM 32-31, TSM 32-32).

## Task 32-31-00-000-801 — Removal of the Retraction Actuator

Warning: Depressurize the green hydraulic system (AMM 29-00-00) before
disconnecting the actuator. Trapped pressure can drive the rod suddenly.

1. Perform the ground safety precautions (Task 32-00-00-910-801).
2. Depressurize the green hydraulic system (AMM 29-00-00).
3. Disconnect and cap the two actuator hydraulic lines.
4. Remove the cotter pins and nuts from the actuator body-end and rod-end pins.
5. Support the actuator, withdraw the pins, and remove the actuator.

## Task 32-31-00-400-801 — Installation of the Retraction Actuator

1. Inspect the mounting pins and bushings; replace if outside wear limits.
2. Position the actuator and install the body-end and rod-end pins.
3. Torque the rod-end pin nut to 900 in-lb and install a new cotter pin.
4. Reconnect the hydraulic lines and torque the B-nuts to 250 in-lb.
5. Bleed the actuator circuit (AMM 29-00-00).
6. Perform the operational test (Task 32-11-00-700-801).

# 32-42-00 Wheels and Brakes

## Task 32-42-00-000-801 — Wheel and Tire Removal

Warning: Deflate the tire fully before removing the axle nut. A pressurized
wheel can explode if the tie bolts are loosened.

1. Perform the ground safety precautions (Task 32-00-00-910-801) and jack the
   affected gear (Task 32-00-00-580-801).
2. Deflate the tire completely through the valve core.
3. Remove the axle nut and washer, retaining the cotter pin for scrap.
4. Withdraw the wheel and tire assembly from the axle.

## Task 32-42-00-400-801 — Wheel and Tire Installation

1. Inspect the axle, bearings, and brake discs for wear and heat damage.
2. Pack the wheel bearings with grease per AMM 12-21-00.
3. Install the wheel, washer, and a new axle nut; torque to 650 in-lb and align
   to the next cotter-pin slot; install a new cotter pin.
4. Inflate the tire to the servicing pressure and leak-check the valve.

## Task 32-42-00-710-801 — Brake Bleeding

Perform after any brake line disconnection (including caps fitted during
Task 32-11-00-000-801) or when a spongy pedal is reported (TSM 32-41).

1. Connect the pressure bleed rig to the brake bleed port.
2. Apply bleed pressure and open the bleed valve until clear, air-free fluid
   flows.
3. Close the bleed valve, remove the rig, and check pedal firmness.
4. Confirm no residual drag by rotating the wheel by hand (TSM 32-41 if drag
   persists).

## Brake and Tire Servicing Data

- Main tire servicing pressure: 190 psi cold.
- Nose tire servicing pressure: 140 psi cold.
- Brake disc minimum thickness: reject at 22 mm total stack (nominal 28 mm).
- Maximum permitted brake temperature before dispatch: 150 °C.

# 32-32-00 Free-Fall (Alternate) Extension System

The free-fall extension system deploys the gear by gravity when normal hydraulic
extension is unavailable. Selecting free-fall isolates the retraction actuators
from hydraulic pressure and releases the up-locks; the gear then falls and locks
down under its own weight, assisted by airloads. This is the alternate procedure
referenced by MEL 32-30-01 and by the extension troubleshooting in TSM 32-32.

## Task 32-32-00-000-801 — Free-Fall System Functional Test

Warning: Perform on jacks only. The gear will fall rapidly when the up-locks
release. Keep personnel clear of the gear travel path.

1. Perform the ground safety precautions (Task 32-00-00-910-801) and jack the
   aircraft (Task 32-00-00-580-801).
2. Retract the gear normally and confirm up-lock engagement.
3. Operate the free-fall selector. Confirm the up-locks release and each gear
   falls to the down-and-locked position within 15 seconds.
4. Confirm three green down-and-locked indications.
5. Restore the normal selector and pressurize the green system (AMM 29-00-00).
6. Perform the normal operational test (Task 32-11-00-700-801).

## Task 32-32-00-220-801 — Up-Lock and Down-Lock Rigging Check

1. With the gear down and safetied, inspect each down-lock over-center link.
2. Measure the over-center travel; nominal is 4–6 mm past center.
3. Adjust the lock-link turnbuckle to achieve the correct over-center travel.
4. Verify the down-lock proximity sensor switches within the target gap
   (1.5–2.5 mm) at the locked position (see TSM 32-33).
5. Repeat for each up-lock, confirming positive engagement in the stowed
   position.

# 32-61-00 Landing Gear Position Indicating

Gear position is sensed by proximity sensors at each up-lock and down-lock and
reported to the LGCIU, which drives the flight-deck indications. Indicating
faults are troubleshot in TSM 32-33 and may be dispatched under MEL 32-30-01.

## Task 32-61-00-000-801 — Proximity Sensor Replacement

1. Perform the ground safety precautions (Task 32-00-00-910-801).
2. Disconnect the sensor connector at the disconnect bracket.
3. Remove the sensor mounting bolts and withdraw the sensor.
4. Install the new sensor and set the target gap to 1.5–2.5 mm.
5. Reconnect the harness and verify correct switching (TSM 32-33).
6. Confirm the LGCIU reports no active maintenance messages.

## Task 32-61-00-710-801 — LGCIU Indicating System Test

1. Apply electrical power to the LGCIU.
2. Cycle the gear on jacks (Task 32-11-00-700-801).
3. Confirm each proximity sensor transitions state at the correct gear position.
4. Confirm the transit, up-lock, and down-lock indications agree between the two
   LGCIU channels.
5. Clear any latched faults and record the test.

# 32-00-00 Consumables and Expendables Summary

- Grease, aircraft general-purpose, per AMM 12-21-00.
- Hydraulic fluid, MIL-PRF-83282 (or approved equivalent).
- Cotter pins — new on every reassembly; never re-use.
- Self-locking nuts — replace when the prevailing torque is below the minimum.
- Leak-detection fluid for pressurized connections.
- Dry nitrogen for strut servicing.

# 32-41-00 Nose-Wheel Steering

The nose-wheel steering actuator is powered from the green hydraulic system
(AMM 29-00-00) and commanded by the steering hand-wheel and rudder pedals.
Steering faults are troubleshot in TSM 32-51.

## Task 32-41-00-000-801 — Steering Actuator Removal

Warning: Depressurize the green hydraulic system (AMM 29-00-00) before
disconnecting the steering actuator. Center the nose wheel first.

1. Perform the ground safety precautions (Task 32-00-00-910-801).
2. Jack the nose gear (Task 32-00-00-580-801) so the nose wheel is clear.
3. Center the nose wheel and disconnect the steering feedback linkage.
4. Disconnect and cap the two steering hydraulic lines.
5. Remove the actuator mounting bolts and withdraw the actuator.

## Task 32-41-00-400-801 — Steering Actuator Installation

1. Position the actuator and install the mounting bolts; torque to 700 in-lb.
2. Reconnect the hydraulic lines and the feedback linkage.
3. Bleed the steering circuit (AMM 29-00-00).
4. Perform a steering operational test through the full left/right travel and
   confirm centering. Investigate any hard-over or free-play per TSM 32-51.

## Task 32-41-00-220-801 — Steering Free-Play Check

1. With the nose gear on jacks and hydraulic pressure off, grip the nose wheel
   and check lateral free play at the tire.
2. Maximum permitted free play at the tire tread: 3.0 mm.
3. If out of limits, inspect the feedback linkage rod-ends and the actuator
   internal seals; overhaul or replace as required.

# 32-51-00 Landing Gear Doors

Each gear well is closed by hydraulically sequenced doors. Door sequencing is
tied to gear travel; a door that fails to close is troubleshot in TSM 32-61 and
may involve the door seal items in CDL 52-30-1.

## Task 32-51-00-000-801 — Main Gear Door Removal

1. Perform the ground safety precautions (Task 32-00-00-910-801).
2. Support the door and remove the hinge and actuator-rod pins.
3. Retain the shims and note their locations for reinstallation.
4. Remove the door clear of the well.

## Task 32-51-00-400-801 — Main Gear Door Installation and Rigging

1. Install the door on its hinges with the original shims.
2. Connect the door actuator rod and adjust the rod length to achieve flush
   closure with the fuselage contour.
3. Cycle the gear on jacks (Task 32-11-00-700-801) and confirm the door
   sequences correctly and closes flush.
4. Confirm the door seal is continuous and undamaged; a missing seal segment may
   be subject to dispatch relief in CDL 52-30-1.

# 32-00-00 Standard Practices and Fastener Data

## Locking Hardware

- Install new cotter pins on every reassembly. Spread the legs fully.
- Replace self-locking nuts when the run-on (prevailing) torque falls below the
  minimum, or after the number of re-uses allowed by the operator's practices.
- Apply torque to the nut, not the bolt head, unless the task states otherwise.
- Where a torque range is given, torque to the mid-point unless the mating parts
  require otherwise for alignment (e.g. cotter-pin slot alignment).

## Hydraulic Line Handling

- Cap every disconnected line and its mating fitting immediately. Contamination
  is the leading cause of actuator and valve faults (TSM 32-31, TSM 32-32).
- Use only the specified fluid (MIL-PRF-83282 or approved equivalent).
- Bleed every circuit that was opened before an operational test (AMM 29-00-00).
- Torque B-nuts to the value for their size; do not over-torque, which distorts
  the flare and causes leaks.

## Corrosion Control

- Inspect exposed steel gear components for corrosion at every gear access.
- Remove light corrosion within blend limits and re-apply the protective
  finish per the structural repair manual.
- Reject any pin or bushing with corrosion pitting deeper than the wear-limit
  value (see Main Pivot Pin — Wear Limits).

# 32-00-00 Torque Reference Summary

- Main pivot pin nut: 1200 in-lb.
- Retraction actuator rod-end pin nut: 900 in-lb.
- Steering actuator mounting bolt: 700 in-lb.
- Nose trunnion pin nut: 800 in-lb.
- Torque-link apex bolt: 300 in-lb.
- Main axle nut: 650 in-lb, then align to the next cotter-pin slot.
- Nose axle nut: 500 in-lb, then align to the next cotter-pin slot.
- Brake and hydraulic union B-nuts: 250 in-lb.

# 32-00-00 Revision Record

- Rev-42 (2026-05-01): Added free-fall functional test, indicating system tasks,
  strut servicing chart, nose-wheel steering, gear doors, standard practices,
  and expanded safety summary. Cross-referenced TSM, MEL, and CDL items
  throughout.
- Rev-41 (2026-01-15): Updated main pivot pin wear limits and torque values.
- Rev-40 (2025-09-01): Initial issue of the consolidated ATA 32 chapter.
