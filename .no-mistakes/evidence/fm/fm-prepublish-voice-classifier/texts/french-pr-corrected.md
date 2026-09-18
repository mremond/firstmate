This change refreshes the pager so each call returns exactly one page.
It fixes the pagination bug where a retried call could return a page twice; the regression test covers two consecutive timeouts.
