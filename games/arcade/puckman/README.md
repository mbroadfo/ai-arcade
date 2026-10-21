# Puck Man (bootleg set 1)

MAME set `puckmanb`, hardware pacman/pacman.cpp. Put on the AI by `tools/new_game.py` from `arcade/pacman` with the kit `pacman_board` (`arcadekit/kits/pacman_board`); its spec.py is the template's with the name changed, plus whatever the checks found.

## Onboarding status (21 October 2026)

- on the Pi, and MAME 0.251 accepts the set puckmanb
- Puck Man (bootleg set 1): MAME driver pacman/pacman.cpp (Zilog Z80)
- kit pacman_board (maze chase) covers pacman/pacman.cpp; starting from arcade/pacman
- note: __init__.py already exists: left as it is
- note: spec.py already exists: left as it is
- the kit's validation: all 16 checks passed
- rule decider (the labelled control, not AI play): scored [6490]; the model made 0% of the moves
- model nimble: scored [5210]; the model made 81% of the moves
