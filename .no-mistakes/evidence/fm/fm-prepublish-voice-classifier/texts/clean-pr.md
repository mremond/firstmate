Refresh the pager so each call returns exactly one page.

The previous implementation reused a stale cursor after a timeout, so a retried call could return a page twice. This change resets the cursor on retry and adds a regression test that drives two consecutive timeouts.
