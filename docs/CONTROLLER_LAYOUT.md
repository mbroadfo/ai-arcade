# Canonical AI Arcade Controller Layout

The Controller Broker exposes **two stable virtual Linux gamepads**:

- `AI Arcade Player 1`
- `AI Arcade Player 2`

The layout is intentionally designed around the target physical arcade control
panel so that AI control and future physical wiring share the same logical
contract.

## Logical controls per player

| Logical action | Linux input | Joystick index |
|---|---|---:|
| LEFT / RIGHT | ABS_X | axis 0 |
| UP / DOWN | ABS_Y | axis 1 |
| BUTTON_1 | BTN_SOUTH | button 0 |
| BUTTON_2 | BTN_EAST | button 1 |
| BUTTON_3 | BTN_C | button 2 |
| BUTTON_4 | BTN_NORTH | button 3 |
| BUTTON_5 | BTN_WEST | button 4 |
| BUTTON_6 | BTN_Z | button 5 |
| STICK_1 | BTN_TL | button 6 |
| STICK_2 | BTN_TR | button 7 |
| COIN | BTN_SELECT | button 8 |
| START | BTN_START | button 9 |

This mirrors a conventional 10-button gamepad layout while preserving arcade
semantics.

## Design rule

Game-playing intelligence emits logical actions such as:

- `P1_LEFT`
- `P1_BUTTON_1`
- `P1_COIN`
- `P2_START`

It must never depend on RetroArch button numbers or physical encoder terminals.

Later, the physical control-panel adapter will map the cabinet wiring into this
same canonical contract.

## Future cabinet controls

Menu/Exit/Pause/Reset should be treated as **cabinet/system controls**, not
player action buttons. They should be modeled separately so they do not consume
the per-player game-control namespace.
