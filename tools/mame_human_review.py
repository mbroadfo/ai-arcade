"""Contact sheets for the MAME 0.251 conversion (pi/mame_human/convert.py): one row per checked game, its three
screenshots (before the coin, after the coin, after start) beside what the automatic check found. For a person (or
Claude) to look at before approving a batch.

    python tools/mame_human_review.py OUTDIR [--per-sheet 6]     # needs Pillow
"""
import argparse
import json
import sys
from io import BytesIO
from pathlib import Path

import paramiko
from PIL import Image, ImageDraw

from gamelib import DEFAULT_PI_HOST

LEDGER = "/opt/retropie/configs/mame-0251/ledger.json"
SHOTS = ("1-before-coin.png", "2-after-coin.png", "3-after-start.png")
HEIGHT = 200
LABEL_W = 260


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("outdir")
    parser.add_argument("--host", default=DEFAULT_PI_HOST)
    parser.add_argument("--per-sheet", type=int, default=6)
    args = parser.parse_args()
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)

    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.connect(args.host, username="pi", timeout=10)
    sftp = ssh.open_sftp()
    with sftp.open(LEDGER) as f:
        ledger = json.loads(f.read())
    checked = [(z, e) for z, e in sorted(ledger.items()) if e["status"] == "checked"]

    rows = []
    for z, e in checked:
        c = e["check"]
        images = []
        for name in SHOTS:
            try:
                with sftp.open(f"{c['folder']}/{name}") as f:
                    img = Image.open(BytesIO(f.read())).convert("RGB")
                images.append(img.resize((max(1, img.width * HEIGHT // img.height), HEIGHT)))
            except OSError:
                images.append(None)
        label = [z if z == e["set"] else f"{z} -> {e['set']}", (c.get("description") or "")[:34],
                 f"speed {c['speed']}%", f"coin {'yes' if c['coin_reached_game'] else 'NO'}  "
                 f"start {'yes' if c['start_reached_game'] else 'NO'}",
                 f"escape {'yes' if c['quit_on_escape'] else 'NO'}",
                 f"change idle {c.get('idle_change')} coin {c.get('coin_change')} start {c.get('start_change')}",
                 "AUTO-PASS" if c["auto_pass"] else "NEEDS A LOOK"]
        rows.append((label, images))
    sftp.close()
    ssh.close()

    sheets = []
    for i in range(0, len(rows), args.per_sheet):
        chunk = rows[i:i + args.per_sheet]
        width = LABEL_W + max(sum((im.width if im else HEIGHT) + 8 for im in imgs) for _, imgs in chunk)
        sheet = Image.new("RGB", (width, len(chunk) * (HEIGHT + 10)), "white")
        draw = ImageDraw.Draw(sheet)
        for r, (label, imgs) in enumerate(chunk):
            y = r * (HEIGHT + 10)
            for n, text in enumerate(label):
                draw.text((6, y + 6 + n * 16), text, fill="black")
            x = LABEL_W
            for im in imgs:
                if im:
                    sheet.paste(im, (x, y))
                    x += im.width + 8
                else:
                    draw.rectangle((x, y, x + HEIGHT, y + HEIGHT), outline="red")
                    draw.text((x + 6, y + 6), "no screenshot", fill="red")
                    x += HEIGHT + 8
        path = out / f"sheet-{i // args.per_sheet + 1:02d}.png"
        sheet.save(path)
        sheets.append(str(path))
    print(f"{len(rows)} checked games on {len(sheets)} sheets")
    for s in sheets:
        print(s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
