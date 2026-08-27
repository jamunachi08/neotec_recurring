# Changelog

## 0.9.0

### Changed

- **Party tracking generalised from Employee to any party type.** Tick *Track a
  party on every line*, choose Customer, Supplier or Employee, and pick the
  party. Each line is routed to whichever field its account can legally hold, as
  before:

  | Account | Where the party lands |
  |---|---|
  | Receivable | party_type Customer, party set |
  | Payable | party_type Supplier or Employee, party set |
  | Blank account type, Asset, Expense, Income, Equity | the Accounting Dimension over that party type |
  | No dimension configured | the narration, which does not reach the ledger |

  This is what the accrued revenue pattern needs. An unbilled revenue account
  normally has a blank account type, so ERPNext will not accept a customer as a
  party on it. The dimension records the customer without inventing a receivable
  balance and without pulling the accrual into AR ageing.

- **The source document now carries more across.** Choosing a document type and
  a document fills the main entry date, the company, the amount and, where the
  source has one, the party. Previously only the date was fetched.

### Added

- **create_party_dimension and party_tracking_status endpoints**, replacing the
  employee-only versions. Choosing a party type with no dimension configured
  offers to create one in place.

### Migration

The v0_9_0 patch carries existing employee tracking onto the general fields. The
old employee fields remain as hidden columns.

## 0.8.0

The form was rebuilt around three dates. The user enters two; the system derives
the third and everything below it.

### Changed

- **Three dates, not four.** *Main entry date* is the source document's date.
  *Recurring start date* is when coverage begins. *Recurring end date* is
  calculated. The old form also asked for a first posting date, which nobody
  should have to work out: it is now derived from the posting rule and shown
  read only.

- **Duration replaces the rhythm and term pair.** One number and one unit -
  Days, Months, Years or Until a date. *Post every* and *Continue for* are gone,
  along with the failure mode where a term was typed into the rhythm box.

- **Posting dates come from a rule, not a date.** *Post entries on* takes End of
  each month, Same day each month, End of each quarter or Every day, and sits in
  Options with a month end default. A 5 June start with a 180 day duration posts
  first on 30 June without anything else being entered.

- **Amount per day is shown.** Total divided by the days in the term, read only,
  updating as the figures change.

### Added

- **Create a template from a source document.** Sales Invoice, Purchase Invoice,
  Payment Entry, Journal Entry and Expense Claim gain a Create, Recurring Entry
  button on submitted documents. Company, date, amount and the relevant control
  account are carried across, and the template is linked back to the document.
  A second template against the same document asks for confirmation first.

- **Live derivation.** End date, first posting date, number of postings, amount
  per day and the plan sentence all update as the user types, without saving.

### Migration

The v0_8_0 patch maps existing templates onto the new fields: covers from and
the first posting date collapse into the recurring start date, the rhythm and
term collapse into a duration, and the day adjustment becomes a posting rule.
Retired fields are kept as hidden columns. Schedules are not rebuilt, so nothing
already posted moves.

## 0.7.0

### Added

- **One checkbox for employee costs.** Tick *This is an employee cost*, choose
  the employee, and every line of the entry carries that employee. No party type
  to select, no dimension field to find on each row.

- **The destination is chosen per line.** ERPNext permits party_type and party
  only on receivable and payable accounts, and throws at submit on anything
  else, so the employee cannot simply be written as a party everywhere. Each
  line is routed to whichever field its account can legally hold:

  | Account | Where the employee lands |
  |---|---|
  | Payable | party_type Employee, party set |
  | Asset, Expense, Income, Equity | the Accounting Dimension over Employee |
  | Receivable | the dimension, since ERPNext types Employee as Payable |
  | No dimension configured | the narration, which does not reach the ledger |

- **The routing is shown before saving.** A read only note under the employee
  field states how many lines will carry the party, how many the dimension, and
  how many only the narration.

- **The dimension is offered when the box is ticked.** If no Accounting
  Dimension over Employee exists, ticking the box asks whether to create one and
  does it in place. Declining is allowed, with a plain statement of what is lost.

- **A value already on a line always wins.** An explicit party or dimension value
  is never overwritten by the template employee.

### Migration

The v0_7_0 patch initialises the flag to off. No existing template changes
behaviour.

## 0.6.0

### Fixed

- **Employee could not be selected in Simple mode.** Employee is a valid Payable
  party type in ERPNext, and the posting engine has always copied it correctly,
  but the party type fields on the main form were hidden and locked to Customer
  or Supplier. An employee advance or an employee payable was unreachable
  without switching to Advanced mode. Both party type fields are now visible on
  any account that accepts a party, and the picker offers every party type valid
  for that account type rather than assuming one.

### Added

- **Guidance for accounts that cannot carry a party.** A prepaid Iqama, an
  insurance prepayment or an expense account is neither receivable nor payable,
  so ERPNext refuses a Party on it. The message now explains why and names the
  alternative: an Accounting Dimension over Employee, which posts to the ledger
  and works on every account type. If such a dimension already exists, the
  message names its field.

- **create_employee_dimension endpoint.** Creates the Accounting Dimension over
  Employee and mirrors it onto the template and its lines immediately, rather
  than waiting for the next migrate. Idempotent.

- **party_capability endpoint.** Returns what a given account can carry: its
  account type, whether a party is allowed, which party types are valid, and the
  employee dimension fieldname if one is configured. Drives the form behaviour
  in both Simple and Advanced mode.

- **A note when employee traceability is missing.** A template posting to an
  account whose name suggests an employee cost, with no employee dimension
  configured, shows an informational message on save. It does not block: the
  entry is valid, but the cost will not be traceable to the employee in any
  report.

## 0.5.1

### Added

- **A guard against very large schedules.** Entering a term in the rhythm box,
  Post every 1 Day continuing for 174 Postings, produces a hundred and
  seventy-four daily journal entries when a seven posting monthly schedule was
  meant. Both are legitimate, so the save is stopped rather than refused: it
  names the exact correction, and a confirmation tick lets a genuinely long
  daily schedule through. The threshold is configurable in Recurring Entry
  Settings and defaults to forty.

- **Both day count families in the preview.** Each period now shows its length
  under the chosen convention and under the other family, with totals, so the
  effect of the choice can be read off the screen instead of worked out on
  paper.

### Fixed

- **Amounts displayed with too many decimals.** The preview rendered a two
  decimal riyal amount as 66.0900, because formatting happened in the browser at
  the site float precision. Amounts are now formatted on the server at the
  template's own currency precision. Stored values were always correct.

## 0.5.0

### Fixed

- **End of month collapsed every posting on a daily or weekly rhythm.** Applying
  it to a daily schedule forced all thirty-one August dates onto 31 August, so
  distinct periods merged, coverage windows fell out of order, and the schedule
  could not post. The adjustment is now offered only on a monthly, quarterly or
  yearly rhythm, is cleared automatically when the rhythm changes, and is
  refused on save if it somehow persists.

- **Posting dates are now guaranteed unique and ascending.** A day adjustment or
  a holiday rule could push two postings onto one date, which breaks the period
  model and would breach the one entry per period idempotency key. Any collision
  is nudged forward by a day.

- **Amounts were not rounded to the currency.** A schedule built on an unsaved
  document in preview showed four decimals, such as 68.9655 on a SAR amount, and
  the rounding residual did not tie back to the total. Precision is now resolved
  from the company currency, which also handles the three decimal Gulf
  currencies, and the residual always lands on the final period so the schedule
  sums exactly.

### Added

- **Final entry posts on.** A term ending mid month leaves a short final period.
  The default keeps it on the normal schedule date, so a month end series stays
  a month end series throughout. Set it to the day the term ends if the closing
  entry should carry the exact end date.

- **Days left column in the preview.** A running remainder beside each period,
  so a schedule can be checked the way it is checked by hand: the term total
  less each period until nothing is left.

### Migration

The v0_5_0 patch clears End of month from any template on a daily or weekly
rhythm and sets the final posting basis. Pending rows rebuild on the next save.

## 0.4.0

### Added

- **Covers from.** A charge is often paid on one date and first posted on
  another. An Iqama fee paid on 15 July and first posted at month end covers
  seventeen days in its first period, not one day and not a whole month. Covers
  from records when the service period begins; First posting date records when
  the first entry is dated. The term is measured from Covers from. Leave it
  blank when the two are the same.

- **Each entry covers.** Chooses whether a period ends on its posting date, in
  arrears, or starts on it, in advance. In arrears is the default and is what an
  accrual or an amortisation needs: an entry dated 31 July then covers July.
  In advance suits rent or a subscription billed for the period ahead.

### Fixed

- **Periods were recognising the wrong month.** An entry dated 31 July covered
  from 31 July to 30 August, so July's entry carried August's expense. Periods
  now end on their posting date by default.

- **The tail of a term was being dropped.** When the last scheduled posting fell
  before the end of the term, the remaining days were not recognised at all. A
  closing posting is now added and dated on the term end, so the schedule always
  sums to the full amount over the full term.

### Migration

The v0_4_0 patch sets existing templates to the in advance basis, preserving
their current behaviour exactly. No schedule is rebuilt. Review the basis on any
amortisation template and switch it to in arrears if that is what it should be;
only pending rows change when you save.

## 0.3.1

### Changed

- **The calculated end date is now visible while typing.** A term entered in
  days shows *Ends on* directly beside the day count, updating as the number is
  typed. In 0.3.0 the date was calculated correctly but sat in a collapsed
  section at the bottom of the form, which meant a clerk entering a ninety day
  term had to go looking for the date it ended on.

- **The reverse is shown too.** Choosing *Until a date* displays how long that
  term is, in days and approximate months, so a term stated either way can be
  checked against the contract without arithmetic.

## 0.3.0

The form was rebuilt around how a clerk reads a contract rather than how the
posting engine works. Nothing in the engine changed.

### Changed

- **Post every / Continue for.** Frequency, Repeat Every, Ends, Number of
  Occurrences, Number of Days, End Date and Term Includes Start Date collapse
  into two number-and-unit pairs. *Post every 1 Month, continue for 12
  Postings.* Continue for accepts Postings, Days, Weeks, Months, Years or Until
  a date, so any way a contract states its term can be typed in directly.

- **One amount field.** Amount Mode plus five separate currency fields become
  Amount and a This amount is selector: Per posting, Total for the whole term,
  Per day, Per year. The clerk types the number printed on the document and says
  what it means.

- **Simple entry mode.** The common two line entry is now a Debit account and a
  Credit account on the main form. The lines grid is not shown at all. Advanced
  mode reveals the grid for tax lines and splits, and carries the two simple
  accounts across so nothing is retyped.

- **Party fields resolve and relabel themselves.** Choosing a receivable account
  labels the field Customer and makes it required. A payable account labels it
  Supplier. Any other account hides it. The clerk never sees a party field that
  does not apply.

- **Day count convention moved to Options** with a default of Actual and a note
  that it only matters for day based terms and amounts. It is no longer a
  decision on the main path.

### Added

- **Live summary.** A sentence under the schedule fields updates as the clerk
  types: *Posts every month, 12 times. Each posting is SAR 20,000.00.*

- **Preview Schedule.** A button on draft templates showing every posting date,
  the period it covers, its day count and its amount, with totals, before
  anything is saved.

- **Contextual headlines.** A warning appears only when it is needed: when a
  30/360 term spans a different number of actual days, or when a per year amount
  on a 360 day basis will not sum to the annual figure.

### Migration

The v0_3_0 patch maps every 0.2.x template onto the new fields. Frequency and
interval become Post every, the end condition becomes Continue for, and the
amount mode becomes Amount type. A two line balancing template is set to Simple
mode with its accounts and parties carried across; anything else becomes
Advanced. Schedules are not rebuilt, so nothing already posted moves.


## 0.2.0

### Added

- **Day count conventions.** Six conventions are supported: Actual (Calendar
  Days), Actual/365 Fixed, Actual/360, 30/360 US, 30E/360 Eurobond and
  30E/360 ISDA. The convention governs three things at once: how a term in days
  converts to an end date, how many days each schedule period covers, and the
  year denominator used to annualise an amount.

- **Term expressed in days.** End condition gained *After Number of Days*. Enter
  a start date and a term, and the end date is calculated from the convention. A
  180 day term under 30/360 US starting 1 August 2026 ends 30 January 2027,
  which is 183 actual calendar days; both figures are shown on the form.

- **Term Includes Start Date.** Controls whether day one is the start date
  itself. A 30 day term from 1 August ends 30 August when on, 31 August when off.

- **Three new amount modes.**
  - *Total Split by Days* apportions a total in proportion to the days each
    period covers, so a 31 day month carries more than a 30 day month.
  - *Daily Rate* multiplies a per day figure by the days in each period.
  - *Annual Amount* apportions an annual figure as amount times period days
    divided by the year basis.

- **Period coverage on every schedule row.** Period From, Period To and Days are
  recorded, so a stub first or last period is visible and auditable.

- **Schedule Total and Total Days Covered** on the template, calculated on save.
  Under a 360 day basis the total will legitimately differ from the annual
  amount, and this makes that visible before submission rather than after
  posting.

- **Live term preview.** Changing the convention, the term or the start date
  updates the calculated end date immediately, without saving.

- **compare_conventions endpoint** returning the end date and actual span under
  all six conventions for a given start date and term.

### Notes

Existing templates are backfilled to Actual (Calendar Days), which reproduces
the previous behaviour exactly. No existing schedule changes.


## 0.1.1

### Fixed

- **Period detection was rejecting open dates.** `is_period_closed` treated any
  submitted Period Closing Voucher dated on or after the schedule date as
  closing that date, with no fiscal year check. A voucher closing one year
  blocked every date in every other year for the same company, producing
  `Accounting period is closed.` on rows that were genuinely open. The check now
  matches the voucher against the fiscal year containing the posting date.

- **Accounting Period was not checked at all.** Rows falling inside an
  Accounting Period with Journal Entry marked closed passed the guard and then
  failed inside ERPNext with an unrelated message. Now detected up front.

- **Cost center on Profit and Loss accounts was not validated at save.** ERPNext
  requires a cost center on income and expense accounts independently of any
  Accounting Dimension configuration. The template saved cleanly and then failed
  at posting time. Now checked during template validation.

### Added

- **Company main cost center as a fallback.** Dimension resolution gained a
  fourth level: line, then template default, then Accounting Dimension Detail,
  then `Company.cost_center`. A correctly configured company needs no cost
  center set on any template.

- **Workspace, built in code.** A Neotec Recurring workspace under Accounting
  with shortcuts and link cards. Created on install and rebuilt on every
  migrate, so a deleted or damaged workspace repairs itself.

- **Settings seeded on install.** Scheduler on, 90 day backdating limit, 3
  attempt cap, notification to Accounts Manager. Only blank fields are
  populated; a value an administrator changed is never overwritten.

- **Live dimension mirroring.** Creating or updating an Accounting Dimension now
  mirrors it onto the template and line doctypes immediately, rather than
  waiting for the next migrate.

- **Company creation hook.** A new company re-asserts the dimension mirror. No
  per company configuration is stored or required.

- **Failure notifications.** The Notify On Failure setting now delivers. Users
  holding the notify role receive a Notification Log entry naming the template
  and the counts.

- **Troubleshoot menu on the template.** Diagnose explains in plain sentences
  why rows are not posting, covering the scheduler switch, template status,
  attempt cap, both period mechanisms, an existing entry for the period, and the
  last recorded error. Reset Failed Rows returns them to Pending.

### Notes

No fixture JSON is shipped. All setup is code driven in `setup/install.py` and
re-asserted on `after_migrate`, so installing the app is the only step required
on a new site or a new company.

## 0.1.0

Initial release.
