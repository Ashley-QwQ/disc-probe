"""Post-burn web adapter. GET uses the selected saved burn. POST checks the drive now."""
from . import checkburn
from .drive_lock import DriveBusy
from .works import WorkError


def check(backend, ident, burn_id, *, live):
    review = backend.works.after_burn(ident, burn_id=burn_id)
    if not live:
        return checkburn.saved_report(review['record'], review['media'])
    drive = review['record'].get('drive')
    if not drive:
        raise WorkError('这次刻录没有记录光驱 / No drive was saved with this burn', 404)
    with backend._reading_drive(drive, 'verify'):
        try:
            return checkburn.check(drive, out=backend.out)
        except DriveBusy as exc:
            raise WorkError(str(exc), 409) from exc
        except OSError as exc:
            raise WorkError(f'无法读取光驱 / Could not read the drive: {exc}') from exc
