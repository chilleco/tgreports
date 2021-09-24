import pytest

from . import report


@pytest.mark.asyncio
async def test_all():
    # All types
    await report.debug("test") # No TG report (only PRE / PROD)
    await report.info("test") # No TG report (only PRE / PROD)
    await report.warning("test")
    await report.error("test")
    await report.critical("test")
    await report.important("test")
    await report.request("test")

    # Extra data
    # NOTE: Not {}, [] in dict
    try:
        print(1/0)
    except Exception as e:
        await report.request("test", {
            'onigiri': 1,
            'hinkali': None,
            'hacapuri': {'1', 2, None, 4.5, 6., (7, 8), (9), (10,)},
            'ramen': e,
        })

    # Tags
    await report.request("Tag", tags=['new', 'tag'])

    # Special symbols
    await report.request("'\"_1")
