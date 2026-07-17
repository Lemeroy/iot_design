# PushPlus self-alert design

## Goal

Send a WeChat risk reminder to the PushPlus account that owns the configured
message token after StrokeGuard produces a warning or danger fusion result.

## Delivery contract

- Endpoint: `POST https://www.pushplus.plus/send` with JSON.
- Channel: `wechat`.
- Template: `markdown`.
- Recipient mode: self. The request includes neither `topic` nor `to`.
- A PushPlus `code` of `200` means the asynchronous request was accepted; it
  does not prove final WeChat delivery.
- The token owner must follow the PushPlus service account and complete the
  account requirements imposed by PushPlus, including real-name verification.

## Trigger policy

- Alerts are enabled only for an active guided screening session. A session is
  activated and reset by an accepted web `start` command or by a device
  transition into screening stage `1`.
- A web `cancel` command or device stage `7` deactivates the session. Stage `6`
  remains active so repeated completed-result uplinks can satisfy the warning
  confirmation rule.
- Backend restart does not infer an active session from an existing stage `6`
  uplink. The user or device must start a new screening.
- The first `danger` result in an active session sends immediately.
- `warning` sends only after three consecutive `warning` result uplinks in the
  same active session. `normal` or `insufficient` resets the consecutive count.
- Each session sends at most one warning alert and one danger alert. A later
  `warning` to `danger` escalation sends the danger alert even if the warning
  alert was already sent.
- Trigger only after valid fusion advice has been accepted for MQTT downlink.
  Counting warning uplinks must not generate extra LLM requests.
- Local sound/light alarms remain independent of cloud notification state.

## Message content

Include device ID, event time, F/S/T/E/CSI/final numeric scores, risk level,
the generated advice, and the non-diagnostic safety statement. Do not include
raw audio/video, MFCC, landmarks, eye trajectories, medication, conditions,
gender, age, phone number, or PushPlus token.

## Failure behavior

- Use a bounded HTTPS timeout and run the request outside the MQTT callback.
- Network, timeout, malformed JSON, and non-200 PushPlus codes are logged
  without token or message body.
- PushPlus failure must not block MQTT downlink, InfluxDB writes, the web page,
  or local alerts.
- Code `900` disables further attempts until process restart to avoid worsening
  an account request-limit restriction.

## Configuration

- `PUSHPLUS_ENABLED=1`
- `PUSHPLUS_TOKEN=<secret message token>`
- `PUSHPLUS_DEVICE_NAME=StrokeGuard Mirror 1` (optional)
- A PowerShell configurator reads the token with masked input and updates the
  untracked `cloud/.env` without writing the secret to transcripts.

## Verification

- Unit tests cover session activation and reset, three-warning confirmation,
  interruption by normal/insufficient, per-session limits, warning-to-danger
  escalation, request shape, response codes, timeout, and secret-free logs.
- Deployment first sends an explicit test message after user confirmation.
- End-to-end verification publishes a temporary warning fusion payload and
  confirms PushPlus returns an accepted message serial number.

## User prerequisites

1. Follow the PushPlus WeChat service account.
2. Complete PushPlus real-name verification if required by the account.
3. Create a dedicated message token on the one-to-one message page.
4. Enter the token only through the masked local configurator.
5. Approve one test notification during deployment.

## Official references

- https://www.pushplus.plus/push1.html
- https://www.pushplus.plus/doc/guide/api.html
- https://www.pushplus.plus/doc/guide/code.html
