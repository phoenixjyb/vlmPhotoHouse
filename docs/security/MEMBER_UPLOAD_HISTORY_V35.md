# Member upload history and additional libraries

This local release adds account-only receipt history to the secured WebUI and
native phone adapter. See the candidate.24 protected native contract for the wire
shape. The anonymous TV surface does not expose member receipts.

A member can manually refresh or page their own uploads and open an approved
photo after current destination membership and ordinary media authorization.
Awaiting review, available and unavailable are the only states. Available means
assigned and authorized; it does not promise prepared previews or captions.
Closing/backgrounding, logout and library/account changes clear private rows.
Older servers returning 403/404/503 leave existing upload submission usable.

The requested bilingual presets are Home Renovation / 装修 (`home-renovation`)
and Expense Receipts / 报销单 (`expense-receipts`). The existing explicit operator
creation command creates empty owner-only libraries, preserves existing libraries,
grants no originals and moves no photos. Family remains the default.

Validation: 115 affected backend tests (including ten new history checks); ten
new Chromium/real-ASGI history scenarios and all 63 existing WebUI checkpoints.
Desktop and narrow Chinese history renders inspected. Candidate.24 adds nine
native wire cases, retaining the previous 89 byte-for-byte exchanges.

Delivery is separate: source commits/package are not Windows activation, library
provisioning, or physical-phone acceptance. No runtime DB, job or service is
changed by these source checks. Activate the reviewed package and explicitly
provision the two new empty libraries before claiming live availability.
