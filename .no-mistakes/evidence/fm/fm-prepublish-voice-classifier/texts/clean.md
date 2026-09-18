## Intent

Make the pager return exactly one page per call, so that callers iterating with a cursor never see duplicated or skipped rows. The change adds a regression test that iterates three pages over a fixed fixture.
