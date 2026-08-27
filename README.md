# Neotec Recurring

Recurring Journal Entry engine for ERPNext v15.

Replaces the pattern of cloning the Asset doctype and driving Journal Entry
creation from a client script.

## What it does

A **Recurring Entry Template** describes a repeating Journal Entry: its lines,
its schedule, and its dimensions. On save the template generates a schedule of
dated rows. A daily scheduler task posts every row that has come due.

## Design notes

### Journal Entry type

`Recurring Entry` is not a standard ERPNext voucher type. The app appends it to
`Journal Entry.voucher_type` as a Property Setter on install and re-asserts it on
every migrate. If the option already exists with that exact spelling the install
step is a no-op, so an existing customisation is left alone.

Reusing the value is safe. ERPNext branches on `voucher_type` only for Bank
Entry, Cash Entry, Opening Entry, Depreciation Entry, Exchange Rate Revaluation,
Inter Company Journal Entry and the Deferred Revenue/Expense types. None of
those code paths are reachable from `Recurring Entry`.

### Dimensions

Nothing is hardcoded. `Accounting Dimension` is read on migrate and every active
dimension is mirrored as a Link field on both the template and its line table.
Values resolve line, then template default, then the company default from
`Accounting Dimension Detail`.

`mandatory_for_pl` and `mandatory_for_bs` are enforced when the template is
saved, checked against the root type of each line's account. A dimension that is
mandatory but unset fails at save time rather than inside the scheduler.

The dimension carrying fields on a Journal Entry Account row are `cost_center`,
`project`, and one custom field per Accounting Dimension.

### Party

`Account.account_type` decides whether a party is allowed at all. Only
Receivable and Payable accounts carry one; every other type is posted without
`party_type` or `party`.

Which party types are valid is data, not code. The `Party Type` doctype records
an `account_type` against each entry, so Receivable resolves to Customer and
Payable to Supplier by default, and any other configured Party Type on the line
is accepted. Auto-resolution determines the party type only. A Receivable or
Payable line with no party named is a template validation error.

### Idempotency

Every generated Journal Entry carries `neotec_recurring_template` and
`neotec_recurring_schedule_date`, both indexed. That pair is checked before any
write, so a retried run, an overlapping manual post, and a scheduler restart all
converge on one entry per period.

Cancelling a generated Journal Entry marks its schedule row `Cancelled` rather
than `Pending`, so the scheduler does not silently repost it the next morning.
Deleting one returns the row to `Pending`.

### Failure handling

Each row posts inside its own savepoint and commits on success, so one bad row
cannot roll back a run or poison the transaction. Failures increment an attempt
counter and stop retrying at the configured limit instead of filling the Error
Log every night forever.

Rows older than `max_backdate_days` are skipped rather than posted into a closed
period. Posting into a period covered by a submitted Period Closing Voucher is
refused up front.

## Install

    bench get-app https://github.com/jamunachi08/neotec_recurring
    bench --site <site> install-app neotec_recurring
    bench --site <site> migrate

## Configuration

**Recurring Entry Settings** holds the scheduler switch, the backdating limit,
the attempt limit and the failure notification role.

### Zero configuration per company

No fixture JSON is shipped and none is needed. Everything is created in code by
`setup/install.py` and re-asserted on `after_migrate`:

- the `Recurring Entry` voucher type, as a Property Setter
- the Journal Entry tracking fields, indexed
- one Link field per active Accounting Dimension, on the template and its lines
- Recurring Entry Settings, seeded with working defaults
- the Neotec Recurring workspace under Accounting

Nothing is stored per company. Cost centers, dimension defaults, fiscal years
and closed periods are all read live at posting time, so a company created after
installation works immediately. Creating a Company or an Accounting Dimension
re-asserts the dimension mirror through a document event, so a new dimension is
usable without waiting for a migrate.

### Closed period detection

Two mechanisms close a period in ERPNext and both are checked before posting.
An Accounting Period covering the date with Journal Entry marked closed blocks
the post. A submitted Period Closing Voucher blocks it only when the voucher
belongs to the fiscal year containing the date and is dated on or after it.

## Entering a recurring entry

The user enters three things. Everything else is derived and shown read only.

| Field | Who enters it |
|---|---|
| Source document, Main entry date | User, or carried from the source document |
| Recurring start date | User |
| Duration, a number and a unit | User |
| Total amount | User |
| Debit and credit account | User |
| **Recurring end date** | **System** |
| **First posting date** | **System** |
| **Number of postings** | **System** |
| **Amount per day** | **System** |
| **The schedule** | **System** |

Duration takes Days, Months, Years or Until a date. A 5 June start with a
duration of 180 Days ends on 1 December. The same start with 6 Months ends on
4 December. Both are shown the moment they are typed.

### When entries are posted

*Post entries on*, in the Options section, decides the posting dates. The
default is End of each month, so a 5 June start posts first on 30 June, then at
each month end, with a closing entry on the term end date. The other options are
Same day each month, End of each quarter and Every day.

### Starting from a document

A prepayment usually begins as a Purchase Invoice or a Payment Entry. Submitted
Sales Invoices, Purchase Invoices, Payment Entries, Journal Entries and Expense
Claims carry a **Create, Recurring Entry** button that opens a template with the
company, date, amount and control account already filled in, linked back to the
source.

## Party tracking

Which accounts carry a party is decided by ERPNext, not by this app. party_type
and party are permitted only on Receivable and Payable accounts, because a party
on a GL Entry means a subledger balance.

Tick *Track a party on every line*, choose Customer, Supplier or Employee, and
pick the party. Each line is then routed:

| Account type | Where the party lands |
|---|---|
| Receivable | party_type Customer (or Student, Member, Donor) |
| Payable | party_type Supplier, Employee or Shareholder |
| Blank, Asset, Expense, Income, Equity | the Accounting Dimension over that party type |
| No dimension configured | the narration only |

A note under the party field states the outcome for the current lines before the
template is saved. Choosing a party type with no dimension offers to create one.

A value already set on a line always wins: the template party never overwrites
an explicit choice.

### Accrued revenue and accrued expense

The usual pattern is to book revenue to an unbilled or accrued revenue account
and release it to the revenue account monthly against a customer. That accrued
revenue account normally has a blank account type in the chart of accounts, and
that is correct: revenue earned but not yet invoiced is not a receivable. There
is no invoice, no due date and nothing to collect.

Two ways to make the customer visible on it:

| | Set account_type to Receivable | Leave it blank, use a Customer dimension |
|---|---|---|
| Customer as party | Native | Not possible |
| AR ageing | The accrual appears as outstanding | Stays out |
| Payment Reconciliation | Offered against the accrual | Not offered |

The dimension is the recommended route. It records the customer in GL Entry and
in every dimension-aware report without creating a receivable balance that has
nothing to reconcile against. The same reasoning applies to accrued expense with
a supplier.

## Day count conventions## Day count conventions

The convention on a template answers three separate questions, and they are not
the same question: how many days lie between two dates, what end date a term in
days produces, and how many days are in a year for annualising an amount.

| Convention | Days between dates | Year basis |
|---|---|---|
| Actual (Calendar Days) | Real calendar days | 365, or 366 in a leap year |
| Actual/365 Fixed | Real calendar days | 365 always |
| Actual/360 | Real calendar days | 360 |
| 30/360 US | Every month 30 days, February ends collapsed | 360 |
| 30E/360 (Eurobond) | Every month 30 days, the 31st becomes the 30th at both ends | 360 |
| 30E/360 (ISDA) | Every month 30 days, any month end becomes the 30th except February at maturity | 360 |

The choice is money, not presentation. SAR 100,000 annual over a 30 day period
is 8,219.18 on Actual/365 and 8,333.33 on Actual/360. GCC bank facilities
normally quote Actual/360; lease and service contracts normally run 30/360.

A term entered in days is converted using the same convention. Under 30/360 a
180 day term is exactly six months regardless of which months it crosses, so it
spans 183 actual calendar days when it starts on 1 August. Both the calculated
end date and the actual span are shown on the form.

### Amount modes

| Mode | Period amount |
|---|---|
| Fixed Per Period | The same figure every period |
| Total Split Equally | Total divided by the number of periods |
| Total Split by Days | Total apportioned by the days each period covers |
| Daily Rate | Per day figure times the days in the period |
| Annual Amount | Annual figure times period days divided by the year basis |

Annual Amount under a 360 day basis will not sum to the annual figure over a
real year, and is not meant to. The Schedule Total field on the template shows
the true sum before submission.

## Troubleshooting

A template with failed rows shows a Troubleshoot menu. **Diagnose** explains in
plain sentences why rows are not posting: the scheduler switch, template status,
attempt cap, both period-closing mechanisms, an entry that already exists for
the period, and the last recorded error. **Reset Failed Rows** returns them to
Pending and clears the attempt counter.

## Open items

- Reversal posting for provision templates is scaffolded on the template but the
  runner does not yet post the reversal leg.
- Multi-currency templates post `debit_in_account_currency` only and rely on the
  Journal Entry exchange rate. Untested against non-company-currency accounts.
- No migration from the existing `Recuring Account` doctype yet.
