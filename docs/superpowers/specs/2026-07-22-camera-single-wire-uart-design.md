# Camera single-wire UART design

## Goal

Replace the unusable camera-to-main I2C link without adding hardware. The
camera coprocessor continues to perform local F/E/T perception. The N16R8
remains the Wi-Fi, MQTT, speech, CSI, fusion, and alarm controller. Raw images
remain local and never enter this link or the cloud.

## Wiring

- Camera GPIO48 (UART TX) -> N16R8 GPIO9 (UART RX)
- Camera SDA/GPIO47 remains disconnected
- Grounds remain connected
- Both boards keep independent USB power
- No board-to-board 5 V connection is used

UART0 on the camera remains reserved for the optional COM8 preview. The score
link uses UART1 at 115200 baud, 8 data bits, no parity, and 1 stop bit.

## Data protocol

The camera transmits a fixed-size binary packet five times per second. Each
packet contains:

- two-byte `SG` magic, protocol version, and packet length
- monotonically increasing sequence number
- F/E/T validity flags
- F score, signed mouth angle, and quality
- E score, signed eye detail, and quality
- T score, signed tongue offset, and quality
- guided stage and progress
- CRC16-CCITT over every byte except the CRC field

Only numeric perception results cross the link. The shared encoder and parser
live in `firmware_common` so both firmware projects use the same layout and CRC.
The main parser scans for magic, rejects unsupported versions or lengths,
rejects bad CRC packets, and resumes at the next possible magic sequence.

## Screening behavior

The camera runs the existing guided F/E/T session continuously. It automatically
starts a new cycle after boot and restarts after `done` or `error` with a short
cooldown. This is necessary because the one-way link cannot carry a start
command back to the camera.

The web start command still reaches the N16R8 over MQTT. It clears retained
speech and prior camera values, arms a new fusion session, and accepts fresh
camera packets. The UI displays the camera-reported stage and progress. A camera
cycle may already be in progress when the user clicks start; this is an explicit
initial-competition limitation, not a hidden synchronization guarantee.

## Failure handling

- No valid packet for two seconds marks F/E/T unavailable.
- Sequence gaps are logged but do not fabricate scores.
- CRC, version, and length failures are discarded.
- MQTT and CSI continue when the camera link is unavailable.
- Fusion remains `insufficient` when available modality weight is too low.
- This remains a risk prompt and care-seeking reminder, not a diagnosis.

## Verification

1. Unit-test packet round trips, CRC rejection, framing resynchronization, and
   timeout behavior.
2. Build both ESP-IDF projects with ESP-IDF v5.5.3.
3. Flash camera COM8 and main COM3.
4. Confirm the main logs fresh camera packets and non-null F/E/T values.
5. Publish a screening start command and confirm the main clears old state,
   accepts fresh scores, computes fusion, and uploads numeric data to the VPS.
6. Disconnect the GPIO48 link and confirm the system reports camera modalities
   unavailable rather than retaining or simulating them.

## Deferred options

Adding 4.7 kOhm pull-ups can restore the original bidirectional I2C design in a
later hardware revision. PC serial bridging is not part of the standalone demo.
