---
doc_id: WSM-LAM-3020
title: Urus — Battery Discharge / Parasitic Drain Diagnosis
department: GARAGE
classification: internal
owner: Service Engineering
last_updated: 2026-02-28
language: en
tags: Lamborghini, Urus, battery, parasitic drain, discharge, diagnosis
---

# Urus — Battery Discharge / Parasitic Drain Diagnosis

## Complaint pattern

Vehicle fails to start after 3–7 days parked, or the customer reports repeated
low-battery warnings despite normal driving. Distinguish first between a
failing battery (fails a capacity test even fully charged) and a parasitic
drain (healthy battery discharged by a consumer that does not sleep).

## Preconditions

- Battery capacity test passed; battery fully charged before measurement.
- Vehicle locked, keys at least 5 m away, wait 30 minutes for all control
  units to enter sleep mode. Bonnet latch bridged so the vehicle believes it
  is closed.

## Measurement

1. Measure quiescent current at the battery negative lead with a clamp meter.
   Sleep-mode target: below 50 mA after 30 minutes. Between 50 mA and 150 mA
   indicates one control unit awake; above 150 mA indicates an active
   consumer or a unit cycling awake.
2. If elevated, pull fuses one circuit at a time (comfort systems first) and
   watch for the current step-change. Record the circuit that drops the
   reading into range.
3. Frequent offenders on this platform: aftermarket dashcams and trackers
   wired to permanent power, the infotainment master unit failing to sleep
   after software interruptions, and tailgate/soft-close modules held awake
   by a misadjusted latch.

## Notes

- A control unit that wakes cyclically (e.g. every 15 minutes) will not show
  on a single reading — log the current for at least one full hour.
- After any repair, repeat the 30-minute sleep measurement before release and
  record the final quiescent value on the RO.
