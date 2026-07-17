# Speech score retention

## Goal

Keep the last valid local speech score available for fusion for five minutes
when later four-second windows contain no usable speech.

## Rules

- A valid speech window replaces the retained score and restarts its age.
- No voice, too short, too quiet, and clipped windows keep the previous score.
- A retained score remains available through exactly 300 seconds and expires
  after that boundary.
- After the normal real-time freshness window, a retained score always has
  `speech_veto_eligible=false`; it contributes only through the 0.25 fusion
  weight.
- An I2S I/O error, device reboot, or a new guided screening clears the score
  immediately.
- The numeric MQTT schema remains unchanged and raw audio remains local.

## Verification

- Score bus returns S at 300 seconds and removes it at 300.001 seconds.
- A retained score cannot trigger the speech danger veto.
- Ordinary unavailable windows do not clear S.
- I/O failure and screening start do clear S.
