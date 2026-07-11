# StrokeGuard M1b Wiring Plan

本文件是 M1b 硬件接线与配置清单。当前外设未到货，所有 GPIO 均为待确认；固件默认不启用任何新增驱动，继续发送 synthetic frame，避免把未验证接线写死进代码。

## Scope

- 主控：ESP32-S3-WROOM-1 N16R8。
- 不新增镜端硬件，沿用原 BOM：GC2145、INMP441、MAX98357A、ST7789、RGB LED、蜂鸣器、3 个按键。
- 原始音视频只在本地处理，云端只接收数值评分与用户档案。
- Arm 因镜子视野限制不单独测量；如后续需要补 Arm 项，应通过可穿戴或外部设备另行设计。

## Kconfig Rules

在 `idf.py menuconfig` 中进入 `StrokeGuard M1a/M1b Config -> M1b hardware scaffold`：

- `STROKEGUARD_HW_CAMERA_ENABLE`：GC2145 到货并接线确认后再启用。
- `STROKEGUARD_HW_AUDIO_IN_ENABLE`：INMP441 到货并接线确认后再启用。
- `STROKEGUARD_HW_DISPLAY_ENABLE`：ST7789 到货并接线确认后再启用。
- `STROKEGUARD_HW_AUDIO_OUT_ENABLE`：MAX98357A 到货并接线确认后再启用。
- `STROKEGUARD_HW_ALERT_ENABLE`：RGB LED、蜂鸣器、按键接线确认后再启用。
- 所有引脚默认 `-1`，表示待确认/未分配。

## Wiring Checklist

| Module | Signals | Current Status |
| --- | --- | --- |
| GC2145 | PWDN, RESET, XCLK, SIOD, SIOC, PCLK, VSYNC, HREF, D0-D7 | 待确认 |
| INMP441 | BCLK, WS/LRCLK, SD/DIN | 待确认 |
| ST7789 | MOSI, SCLK, CS, DC, RST, BL | 待确认 |
| MAX98357A | BCLK, LRC, DIN | 待确认 |
| RGB LED | DATA | 待确认 |
| Buzzer | GPIO | 待确认 |
| Buttons | BTN1, BTN2, BTN3 | 待确认 |

## Bring-Up Order

1. 保持所有 `STROKEGUARD_HW_*_ENABLE=n`，确认 USB-CDC synthetic frame 仍可收帧。
2. 到货后先接 INMP441，验证 16 kHz I2S 采样与 MFCC 维度。
3. 再接 GC2145，验证 JPEG 输出能进入 `type="frame"` 的 `jpeg_b64` 字段。
4. 最后接 ST7789、MAX98357A、RGB LED、蜂鸣器和按键，用于显示/播报/报警交互。

## Safety Note

本项目是风险提示/就医提醒工具，不是诊断设备。危险等级只提示尽快就医或拨打 120，不给出诊断结论。
