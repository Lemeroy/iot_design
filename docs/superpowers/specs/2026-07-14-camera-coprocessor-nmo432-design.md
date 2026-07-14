# ESP32-S3 Camera Coprocessor and NMO432 Design

## Scope

The preliminary-demo device uses two ESP32-S3 boards:

- The existing ESP32-S3-WROOM-1 N16R8 board remains the StrokeGuard main controller.
- The Hiwonder ESP32-S3-Cam board and its expansion board form a camera coprocessor.
- The NMO432 digital microphone connects directly to the N16R8 main controller.

ST7789, MAX98357A, RGB LED, buzzer, and buttons are outside this phase. The
camera product is not a raw GC2145 module and must not be described or driven as
one. Its published material identifies a self-contained ESP32-S3 camera module;
the exact image sensor remains unverified.

## Architecture

```text
ESP32-S3-Cam camera coprocessor
  - local image capture
  - image quality checks
  - future local F/T/E inference
             |
             | I2C: structured values only
             v
ESP32-S3-WROOM-1 N16R8 main controller
  - NMO432 audio capture and future S inference
  - Wi-Fi CSI auxiliary stability score
  - five-modal fusion and veto rules
  - Wi-Fi/MQTT uplink and advice downlink
```

Continuous JPEG transfer is not part of the production path. The camera
module's Type-C/UART connection is reserved for flashing, logs, and optional
single-frame development diagnostics.

## Wiring Allocation

The proposed N16R8 signal allocation avoids the boot-strapping pins and keeps
the camera and microphone buses separate:

| Function | Peripheral pin | N16R8 pin |
| --- | --- | --- |
| Camera I2C data | SDA | GPIO8 |
| Camera I2C clock | SCL | GPIO9 |
| Camera power | 5V | 5V supply rail |
| Camera ground | GND | GND |
| NMO432 bit clock | SCK | GPIO17 |
| NMO432 word select | WS | GPIO18 |
| NMO432 sample data | SD | GPIO16 |
| NMO432 power | VDD | 3.3V |
| NMO432 ground | GND | GND |

The camera expansion-board I2C connector order must be checked against its
silkscreen or vendor schematic before power is applied. The NMO432 L/R pin must
be tied to GND or 3.3V according to the channel selected in firmware. All boards
must share ground. The camera module's documented input supply is 4.75-5.25 V;
its I2C GPIO logic is expected to be 3.3 V but must be verified before wiring.

## I2C Contract

The N16R8 is the I2C controller and the camera module is target address `0x42`.
The controller reads the fixed-size version 1 frame every 500 ms. Multi-byte
fields are little-endian.

```c
typedef struct __attribute__((packed)) {
    uint8_t version;          // Always 1 for this layout
    uint8_t sequence;         // Increments after each completed inference
    uint8_t face;             // 0-100 when valid
    uint8_t tongue;           // 0-100 when valid
    uint8_t eye;              // 0-100 when valid
    uint8_t quality;          // 0-100 image quality
    uint8_t valid_mask;       // bit0=F, bit1=T, bit2=E
    uint8_t status;           // ready, busy, no_face, or error
    int16_t mouth_angle_x10;  // Signed degrees multiplied by 10
    uint16_t latency_ms;      // Last completed processing latency
    uint16_t crc16;           // CRC-16 over all preceding bytes
} camera_scores_v1_t;
```

The status numeric values and CRC parameters will be defined in a shared header
used by both firmware projects. A protocol-version mismatch is an unavailable
camera result, not a score of zero.

## Data and Privacy

- Raw images remain on the camera module or a directly attached local
  development computer.
- Raw audio remains on the N16R8 or a directly attached local development
  computer.
- MQTT and the VPS receive only scores, quality/status metadata, profile data,
  fused level, reasons, and model-generated advice.
- The cloud model never receives images, audio, or MFCC arrays.

## Failure Handling

- No face, poor exposure, a missing model, or incomplete inference clears the
  corresponding validity bit. It must not emit a fabricated normal or zero
  score.
- Repeated I2C failures mark the camera coprocessor offline. NMO432, CSI,
  networking, and device management continue to run.
- Reconnection is automatic after valid version and CRC frames resume.
- Missing F/T/E produces fusion level `insufficient`; it cannot produce a
  misleading complete risk score.
- The device remains a risk-prompt and medical-attention reminder product, not
  a diagnostic device. Arm weakness is not independently measured.

## Delivery Order

1. Confirm the camera expansion-board I2C connector order and logic voltage.
2. Obtain or build the camera-module firmware project and establish local image
   capture plus diagnostic logs.
3. Implement the shared I2C frame on the camera target and N16R8 controller.
4. Implement NMO432 16 kHz mono capture on N16R8 with signal-quality metrics.
5. Integrate real F/T/E and S models only after versioned weights and evaluation
   data are available.
6. Feed validity-aware scores into the existing fusion and MQTT path.

No medical accuracy is claimed before representative data evaluation. Latency,
frame rate, current draw, and I2C reliability remain measurements to be recorded
on the actual hardware.

## First-Stage Acceptance

- Both boards run continuously for 30 minutes without reset or buffer growth.
- N16R8 receives valid CRC frames with increasing sequence values.
- Disconnecting the I2C cable marks the camera offline without stopping audio,
  CSI, Wi-Fi, or MQTT tasks.
- Reconnecting restores camera communication without rebooting N16R8.
- Missing models and invalid images never produce fabricated F/T/E scores.
- Raw images and audio are absent from MQTT payloads and VPS storage.

