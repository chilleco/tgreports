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
