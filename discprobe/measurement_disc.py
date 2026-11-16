"""Read-only suitability checks for a full random-data measurement disc."""


def short_recording(disc, expected=None):
    """Only diagnose a finalized, known nonblank disc, far below a full image.

    With no capacity evidence, restrict the fallback to at most 4096 sectors.
    An open session or an unknown length is not evidence of an interrupted burn.
    """
    sectors = disc.get('sectors')
    capacity = expected or disc.get('capacity_sectors')
    if disc.get('closed') is not True or disc.get('blank') is not False:
        return None
    if type(sectors) is not int or sectors <= 0:
        return None
    limit = capacity * .01 if type(capacity) is int and capacity > 0 else 4096
    if sectors > limit:
        return None
    return (f'This disc has only the beginning recorded ({sectors} sectors, about '
            f'{sectors * 2048 / 1048576:.0f} MB). Burning probably stopped partway; '
            'it cannot be used for measurement. Replace it with a blank disc and burn again.')
