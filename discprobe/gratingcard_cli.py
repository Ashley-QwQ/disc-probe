"""Register the grating card command without loading the numerical solver."""
from pathlib import Path


def _run(args):
    from . import gratingcard
    return gratingcard.run(args)


def add_parser(sub):
    command = sub.add_parser('gratingcard', help='make a DVD picture that changes when the disc is tilted')
    command.add_argument('images', nargs='*', help='two or three pictures, one per target angle')
    command.add_argument('--angles', nargs='+', type=float, required=True, help='target angles in degrees, in picture order')
    command.add_argument('--titles', nargs='+', help='names to show at each angle (default: picture names)')
    command.add_argument('--axis', choices=('x', 'y'), default='x', help='tilt axis through the disc centre (default: x)')
    command.add_argument('--geo', required=True, help='measured DVD geometry JSON or run folder')
    command.add_argument('--lookup', type=Path, help='override the bundled role card response table with an NPZ file')
    command.add_argument('--index', type=Path, help='eligible texture CSV (default: angle-curves-index.csv beside lookup)')
    command.add_argument('--channel-checks', type=Path, help='channel results from the original channel gate')
    command.add_argument('--camera', nargs=3, type=float, metavar=('X', 'Y', 'Z'), help='lens position in disc mm (default: lookup)')
    command.add_argument('--flash', nargs=3, type=float, metavar=('X', 'Y', 'Z'), help='flash position in disc mm (default: lookup)')
    command.add_argument('--centre', nargs=2, type=float, metavar=('X', 'Y'), default=(39., 0.),
                         help='picture centre on the data side in mm (default: 39 0)')
    command.add_argument('--width', type=float, default=24., help='picture box width in mm (default: 24)')
    command.add_argument('--r-max', type=float, default=54., help='outer image radius in mm (default: 54)')
    command.add_argument('--output', type=Path, default=Path('iso/grating-card.iso'), help='output ISO path')
    command.add_argument('--replay', type=Path, help='rebuild an archived weights NPZ or editor work JSON')
    command.add_argument('--json', action='store_true', help='print the result as JSON')
    command.set_defaults(func=_run)
    return command
