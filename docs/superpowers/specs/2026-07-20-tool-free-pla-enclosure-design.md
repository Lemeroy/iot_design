# Tool-Free PLA Enclosure Design

## Goal

Replace all M3 assembly interfaces with low-deflection sliding and latching
features suitable for a preliminary PLA prototype. Correct the front-panel fit
and give the camera board and N16R8 equal-width locating guides.

## Five-Part Contract

The production set remains exactly five parts: shell, front panel, electronics
tray, rear cover, and desktop base. No screw, nut, insert, or separate printed
pin is required.

## Front Panel

The current panel exactly matches the shell opening and has no physical print
clearance. The replacement uses `0.6 mm` clearance on every edge. A fused front
retaining lip prevents the smaller panel from falling through the opening, and
four short rear stop tabs replace the full-height internal rails. The upper
tabs sit below the top edge so the panel can be tilted in from the rear and
seated without flexing the full shell.

## Electronics Tray

The camera board and N16R8 are physically reported to have the same `27 mm`
width. A shared open-ended guide channel therefore uses the approved `30 mm`
clear opening. The guides provide lateral location only; separate cable ties
through the existing tray slots retain each board. The antenna and connector
ends remain open. The NMO432 area is unchanged.

## Rear Cover

The cover slides downward in two shell-mounted side channels. The channels
carry service loads; one long in-plane PLA tongue near the lower side supplies
only the locking force and enters a shell pocket at the final position. The
tongue can be pressed inward by hand before the cover is slid upward. Tool-free
tray spacer ribs retain the electronics tray with the existing nominal gap and
do not apply spring pressure.

## Desktop Base

The body continues to enter the existing `7 degree` inclined socket. One rear
release tongue rises from an isolated pocket in the base and catches the lower
rear shell edge. The tongue uses a long thin PLA flexure and a sloped hook so it
can be pressed rearward by hand. The previous two screw holes and shell pilot
bosses are removed.

## Prototype Parameters

- panel edge clearance: `0.6 mm`;
- front retaining-lip overlap: `1.5 mm`;
- board-guide clear width: `30 mm`;
- rear slide-channel total running clearance: `0.5 mm`;
- rear-cover latch nominal engagement: `0.6 mm`;
- base latch nominal engagement: `0.5 mm`.

These values are starting dimensions for the next PLA print, not production
tolerances. Snap features should be operated only as needed during the
preliminary demonstration; repeated-cycle durability remains unmeasured.

## Validation And Reprint Scope

Automated tests must reject M3 holes and the old pressure-post/screw-boss
modules, verify all new retention modules and parameters, and retain the five
watertight single-component STL checks. The front-panel envelope must reflect
the new edge clearance. All five parts must be reprinted because each receives
either a fit, guide, rail, latch, or mating-interface change.

