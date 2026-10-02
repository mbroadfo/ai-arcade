"""How a game declares the switches an experiment can set, so tools/play.py needs no game's names.

Every switch has exactly one kind, chosen by the question "does it change who chooses?" (docs/GAME_WORKSHOP.md):

    facts     changes what the model is told
    timing    changes when or how often the model is asked; never chooses
    override  changes or replaces a proposed move (booked code-override or code-late)
    skill     steers several moves on its own (booked code-skill)

Every override and skill switch must have an off position, so a "model alone" run is possible.
"""
from dataclasses import dataclass
from typing import Callable, Optional

KINDS = ("facts", "timing", "override", "skill")


@dataclass(frozen=True)
class Option:
    name: str  # the keyword the game's player takes, and the name in the manifest
    kind: str
    help: str
    default: object = False  # a bool default makes an on/off switch
    flag: Optional[str] = None  # the command-line flag; default "--" + name with "_" as "-"
    parse: Optional[Callable] = None  # int, float or str for a valued option
    choices: Optional[tuple] = None
    tag: Optional[str] = None  # added to the run label when the value is not the default, formatted with the value
    model: bool = False  # the value names a model: the manifest records its digest

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"{self.name}: kind {self.kind!r} is not one of {KINDS}")
        if self.kind in ("override", "skill") and not isinstance(self.default, bool) and not self.choices:
            raise ValueError(f"{self.name}: an {self.kind} switch needs an off position (a bool or choices)")

    @property
    def cli(self):
        return self.flag or "--" + self.name.replace("_", "-")


def add_arguments(parser, options, title):
    group = parser.add_argument_group(title)
    for o in options:
        if isinstance(o.default, bool):  # a switch: the flag turns it on, or off when it is on by default
            action = "store_false" if o.default else "store_true"
            group.add_argument(o.cli, dest=o.name, action=action, default=o.default, help=f"[{o.kind}] {o.help}")
        else:
            group.add_argument(o.cli, dest=o.name, type=o.parse, choices=o.choices, default=o.default,
                               help=f"[{o.kind}] {o.help}")


def values(args, options):
    """{name: value} for the game's options, from parsed arguments."""
    return {o.name: getattr(args, o.name) for o in options}


def label_parts(vals, options):
    """Run-label pieces for the options not at their default."""
    return [o.tag.format(vals[o.name]) for o in options if o.tag and vals[o.name] != o.default]


def describe(vals, options):
    """For the manifest: {name: {"value": ..., "kind": ...}}."""
    return {o.name: {"value": vals[o.name], "kind": o.kind} for o in options}
