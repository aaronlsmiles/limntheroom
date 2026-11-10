"""seam.regions.measured_region before the creature leaves the page: A(t) is the dilated home."""
import numpy as np

from seam import regions


def test_at_home_uses_the_home_only():
    home = np.zeros((40, 60), bool)
    home[10:20, 10:20] = True
    stray = np.zeros_like(home)
    stray[30:35, 50:55] = True                      # whatever a mask says before the prompt frame is ignored
    want = ~regions.dilate(home, 4)
    assert np.array_equal(regions.measured_region(stray, home, 4, at_home=True), want)
    # an empty creature mask gives the same region without the flag
    assert np.array_equal(regions.measured_region(np.zeros_like(home), home, 4), want)
    # off the page, the creature counts
    assert not np.array_equal(regions.measured_region(stray, home, 4), want)
