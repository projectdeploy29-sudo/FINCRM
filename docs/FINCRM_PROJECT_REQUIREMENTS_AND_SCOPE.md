# FINCRM - Project Requirements and Scope

**Document type:** Product requirements and UI scope  
**Current state:** Implemented React and Django application with role-based access  
**Theme state:** Navy and red branded workspace  
**Last updated:** 2026-11-23

---

## 1. Product overview

FINCRM is a multi-organization finance CRM for managing customer-to-lead conversion, loan terms, staff, follow-ups, tasks, repayment schedules, payments, subscriptions, reporting, and organization structure.

The application has two main experience groups:

- **Authenticated organization workspace:** Dashboard and CRM screens for administrators, managers, team leads, employees, and other authorized roles.
- **Lead portal:** A read-only customer-style dashboard for a lead or borrower, showing loan, repayment, payment, and follow-up information.

The system is tenant-oriented. Data is intended to be visible only within the signed-in organization and the user's role/hierarchy scope.

---

## 2. Technical requirements

### 2.1 Frontend

- React with Vite
- JavaScript JSX
- Responsive desktop and mobile layouts
- Role-aware navigation
- JWT/API integration
- Local token and active-role persistence
- Razorpay browser checkout integration
- Accessible dialogs, forms, tables, navigation, and labels

Main frontend location:

- `frientend/fincrm`
- Primary source: `frientend/fincrm/src`
- Public logo source: `frientend/fincrm/src/assets/logo.jpg`

### 2.2 Backend

- Django
- Django REST Framework
- JWT authentication
- Multi-role and hierarchy-based authorization
- SQLite for development
- Optional PostgreSQL configuration for production
- Django Admin
- Razorpay server-side checkout support
- Optional OpenAI-compatible AI assistant provider

Backend location:

- `backend/aron_fincrm`

Backend areas include accounts, AI assistant, communications, customers, documents, employees, finance, leads, organizations, permissions, subscriptions, tasks, and WhatsApp.

---

## 3. Core project scope

### 3.1 Organization and staff management

- Manage organization details
- View organization hierarchy
- Manage managers
- Manage team leads
- Manage departments
- Manage teams
- Manage employees
- Assign reporting relationships
- Assign employee roles
- Update staff employment status
- Add, view, edit, and onboard staff records according to role level

### 3.2 Customer and lead management

- Create and maintain customer records
- Customer stages: New → Contacted → Under review → Convert to lead
- Moving a customer to Contacted requires a contact note and a changed customer tag
- Keep customer status changes in the status history
- Track customer type, priority, tags, channel, and assigned employee
- Maintain lead records
- Lead stages: New → Contacted → Approved → Disbursed → Completed
- Record approved loan amount, interest method/rate, and tenure at approval
- Require lead portal login credentials at disbursement
- Require a repayment schedule before completing a lead
- Track expected value and loan terms on the lead
- Assign leads to staff
- View lead assignment history
- View lead status history
- Create lead portal login credentials during disbursement

### 3.3 Tasks and follow-ups

- Create tasks
- Assign tasks to recipients
- Set due date and priority
- Track pending, in-progress, completed, and cancelled tasks
- Create customer and lead follow-ups
- Support call, meeting, visit, email, and other follow-up types
- Schedule meetings and meeting details
- Download calendar invites
- Prepare meeting email invitations
- Send WhatsApp messages from follow-up records
- Mark tasks and follow-ups complete

### 3.4 Finance and payments

- Generate repayment schedules
- Record principal, interest, dues, balances, and installment dates
- Record payments against repayment schedules
- Record payment method and transaction reference
- Verify or reject pending payments
- Show overdue and paid payment states
- Show loan principal, approved amount, deductions, repayment, and remaining balance

### 3.5 Reporting

- Dashboard metrics
- Date-range filtering
- Active lead totals
- Follow-up totals
- Overdue task totals
- Customers under review
- Lead value and payment totals
- Pipeline stages
- Customer, lead, and task status charts
- Revenue in selected reporting periods
- Drill-down panels for records and detail history

### 3.6 Plans and subscriptions

- Public pricing-plan catalog
- Monthly and yearly billing selection
- Enterprise custom-pricing inquiry
- Razorpay payment checkout
- Organization registration after verified payment
- Organization subscription overview
- Billing history
- Plan administration
- Checkout enable/disable controls
- Enterprise inquiry review
- Custom plan creation
- Payment invitation and registration-link resend
- Subscription status and payment status review

### 3.7 AI assistant

- Read-only, role-scoped CRM chat
- User questions about authorized CRM records
- Short conversation history
- Backend-only provider configuration
- No model-generated SQL or direct write actions

---

## 4. Roles and access levels

The navigation and API scope vary by role and hierarchy level.

| Role area | Typical access |
|---|---|
| Super administrator | Enterprise inquiries and public plan administration |
| Organization administrator | Organization settings, plans, subscriptions, hierarchy, staff, CRM records, reports, and settings |
| Manager | Team and staff-related records, customers, leads, tasks, follow-ups, and payments |
| Team lead | Employee and operational records, customers, leads, tasks, follow-ups, and payments |
| General employee | Customers, leads, tasks, follow-ups, and payments |
| Lead portal | Borrower dashboard only |

Available roles may be switched when the signed-in account has more than one role. Role changes reset the active workspace to the dashboard.

---

## 5. Screen inventory

## 5.1 Public screens

### Login

**Purpose:** Authenticate a username and password.

**Elements:**

- FINCRM logo and brand
- Plans navigation button
- Login navigation button
- Username field
- Password field
- Sign-in button
- Validation and API error state

### Plans

**Purpose:** Show active subscription options.

**Elements:**

- Billing-cycle tabs: Monthly and Yearly
- Public plan cards
- Popular-plan indicator
- Plan description
- Price
- Staff and lead limits
- Feature list
- Select-plan or unavailable button
- Enterprise Contact Sales button
- Checkout modal
- Enterprise inquiry modal

### Enterprise checkout

**Purpose:** Complete an approved Enterprise quote through Razorpay.

**Elements:**

- Enterprise title
- Agreed price and billing cycle
- Included services and feature summary
- Continue-to-payment button
- Waiting confirmation state
- Success, error, and registration-link messages

### Registration

**Purpose:** Complete organization registration from a secure invitation.

**Elements:**

- Organization details
- Admin username
- Email
- Password and confirmation
- First and last name
- Organization email and phone
- Create organization button

---

## 5.2 Organization workspace

### Fixed sidebar

**Purpose:** Primary navigation.

**Elements:**

- FINCRM red dragon logo
- Organization name
- Role badge
- Optional role selector
- Scrollable main navigation
- Records section
- Fixed profile area
- Fixed sign-out icon

The navigation area scrolls independently when Records is expanded. The logo/header and profile/footer remain fixed.

### Dashboard

**Purpose:** At-a-glance organizational performance and urgent work.

**Elements:**

- Navy/red welcome hero
- WORKSPACE OVERVIEW label
- View Today button
- Activity overview
- Active lead metric
- Follow-up metric
- Overdue task metric
- Customers under review metric
- Tasks in selected range
- Follow-ups in selected range
- Pipeline metrics
- Lead value
- Payments in selected range
- Paid leads
- Overdue payments
- Lead status summary
- Open Pipeline and Open Report buttons

### Today

**Purpose:** Show work due now.

**Elements:**

- Refresh today button
- Today's follow-ups table
- Follow-up type
- Record
- Scheduled time
- Notes
- Mark complete button
- Complete follow-up outcome dialog
- Tasks due today or overdue table
- Start task button
- Complete task button

### Send / Tasks

**Purpose:** Create and track assigned work.

**Elements:**

- Search
- Refresh
- Add task
- Record table
- Task detail
- Edit button
- Start task button
- Complete task button
- Task history
- Add/edit task dialog

### Follow-ups

**Purpose:** Organize contact follow-ups by record type.

**Tabs:**

- Customers
- Leads

**Elements:**

- Search
- Add follow-up
- Follow-up table
- Call link
- Email link
- WhatsApp button
- Calendar invite button
- Prepare invite email button
- Edit button
- Mark complete button

### Records

**Purpose:** Access core CRM and organization entities.

**Record tabs:**

- Manager
- Team Lead
- Department
- Team
- Employee
- Customer
- Lead
- Payments
- Organization hierarchy

Each record screen provides role-appropriate:

- Search
- Refresh
- Add
- Record table
- Row detail button
- Edit
- Context actions
- Status transitions
- Assignment actions
- History actions
- Detail drawer
- Add/edit record dialog

### Pipeline

**Purpose:** Visualize lead stages and expected value.

**Elements:**

- Total leads metric
- Total expected-value metric
- Payments metric
- Overdue metric
- Lead search
- New column
- Contacted column
- Approved column
- Disbursed column
- Completed column
- Column total value
- Lead card
- Lead detail drawer
- Payment-status badge

### Report

**Purpose:** Summarize CRM activity and status trends.

**Elements:**

- Active leads metric
- Won leads metric
- Customers metric
- Follow-ups metric
- Overdue tasks metric
- Revenue metric
- Leads by stage chart
- Customers by status chart
- Tasks by status chart
- Chart drill-down buttons

### Settings

**Purpose:** Maintain profile and account security.

**Elements:**

- Profile form
- First name
- Last name
- Email
- Save profile button
- Change password form
- Current password
- New password
- Update password button
- Organization plan card for organization administrators

### My subscription

**Purpose:** Show the organization's active subscription.

**Elements:**

- Plan name
- Billing status
- Monthly/yearly cycle
- Subscription reference
- Price
- Start date
- Renewal date
- Remaining days
- Staff usage
- Lead usage
- Renew or change plan button
- Cancel subscription button

### Billing history

**Purpose:** Review organization subscription payments.

**Elements:**

- Billing records table
- Amount
- Status
- Date
- Provider reference

### Plans

**Purpose:** View and select a plan from the signed-in workspace.

**Elements:**

- Monthly/yearly tabs
- Plan cards
- Plan limits
- Plan features
- Checkout or unavailable action

### Organization hierarchy

**Purpose:** Visualize managers, team leads, teams, and employees.

**Elements:**

- Organization summary counts
- Search
- Expand/collapse control
- Department cards
- Manager cards
- Team cards
- Team-lead cards
- Employee cards

### Pipeline and record detail drawers

**Purpose:** Review record-level data without leaving the current screen.

**Elements:**

- Close/Back button
- Record title
- Record context
- Summary card
- Field grid
- Status history
- Assignment history
- Loan terms
- Repayment schedules
- Payments
- Customer and lead details

---

## 5.3 Platform-administrator screens

### Enterprise inquiries

**Purpose:** Review and convert Enterprise sales inquiries.

**Elements:**

- Inquiry search
- Status filter
- Inquiry table
- Organization
- Contact
- Status
- Assigned administrator
- Received date
- Inquiry detail
- Edit customer details
- Status selector
- Assigned-admin selector
- Internal notes
- Save review button
- Create custom plan form
- Send payment invitation button
- Resend registration link button
- Custom subscriptions table
- Payments table
- Registered Enterprise customers table

### Edit plans

**Purpose:** Manage the public subscription catalog.

**Elements:**

- Add plan button
- Paid checkout status
- Enable checkout button
- Disable checkout button
- Missing-price blocker list
- Public-plan cards
- Monthly and yearly prices
- Staff and lead limits
- Price confirmation state
- Active/inactive state
- Edit plan button
- Activate/deactivate button
- Plan editor form

---

## 5.4 Lead portal

**Purpose:** Give a lead or borrower a private, read-only view of their loan.

**Elements:**

- Borrower Portal hero
- Next payment button
- Approved loan
- Loan principal
- Cash paid
- Upfront deductions
- Monthly repayment
- Interest rate and method
- Tenure
- Disbursed date
- Next payment due
- Total paid
- Remaining balance
- Upcoming payments table
- Overdue payments table
- Payment history
- Completed payments
- Upcoming and completed follow-ups

---

## 5.5 Linked pages, record details, dialogs, and drill-through behavior

FINCRM uses two detail experiences:

1. **Record modal:** Opens over the current record page for a selected row or action.
2. **Drill-through drawer:** Opens from Dashboard, Pipeline, Report, or a dashboard preview and supports Back and Close navigation through multiple levels.

Both experiences use the signed-in user's organization and role scope. Restricted or missing related records are not shown.

### Dashboard linked actions

| Dashboard link or card | Destination | Information shown |
|---|---|---|
| View Today | Today screen | Today's due follow-ups and due or overdue tasks |
| Active leads | Drill-through drawer | Matching active lead records |
| Follow-ups | Drill-through drawer | Customer and lead follow-ups |
| Overdue tasks | Drill-through drawer | Overdue tasks in the selected date scope |
| Lead value | Pipeline-lead drawer | Lead list and expected value |
| Payments in selected range | Payment drawer | Payment records and verification status |
| Paid leads | Filtered lead drawer | Leads with a paid payment state |
| Overdue payments | Filtered lead drawer | Leads with an overdue payment state |
| Lead status card | Filtered lead drawer | Leads in that status |
| Task preview row | Task record detail | Task fields and task history |
| Follow-up preview row | Follow-up record detail | Follow-up fields and related collection |
| Call follow-up number | Phone dialer | Opens the contact's telephone link |
| Email follow-up address | Email client | Opens an email-compose action |
| Open Pipeline | Pipeline screen | Stage board and values |
| Open Report | Report screen | Charts and reporting metrics |

### Date-range behavior

The global date-range control appears on Dashboard, Pipeline, and Report:

- **Today:** Current local day.
- **Month to date:** Start of the current month through today.
- **Year to date:** Start of the current year through today.
- **Custom range:** Displays From and To fields.
- A custom From date cannot be set after the selected To date.
- Every metric, chart, preview, and applicable drawer reloads using the selected range.

### Metric and chart drawer behavior

The shared right-side drawer:

- Starts with a filtered record list.
- Uses **Open details** to enter a record.
- Uses **Close** on the first level.
- Uses **Back** after entering a deeper level.
- Can be closed by X or by selecting the backdrop.
- Shows Loading, No matching records, and API error states.
- Preserves the active date range through navigation.

Supported drawer list types:

| Drawer type | Source | Next level |
|---|---|---|
| Leads | `/leads/` | Lead detail or generic lead record |
| Pipeline leads | Pipeline response | Lead detail |
| Tasks | `/tasks/` | Task record detail |
| Customers | `/customers/` | Customer record detail |
| Payments | `/finance/payments/` | Payment record detail |
| Follow-ups | Customer and lead collections | Follow-up record detail |

### Lead-detail drill-through

Selecting a lead card or lead drawer row opens a lead summary containing:

- Contact name
- Lead code
- Lead status
- Assigned employee
- Expected amount
- Payment status: Paid, Overdue, or Not paid
- Phone
- Email
- City or location

The lead detail includes these linked sections:

| Section | Details |
|---|---|
| Customer | Converted or linked customer name |
| Loan terms | Requested amount, approved amount, interest rate and method, tenure, disbursed amount, and deductions |
| Repayment schedule | Installment, principal, interest, expected amount, paid amount, outstanding amount, due date, and status |
| Payments | Amount, date, and verification status |
| Status history | Previous status to new status transitions |
| Assignment history | Assignment reason and change date |

Status and assignment histories load independently. An unavailable history is displayed as a section-specific error without blocking the rest of the lead.

### Generic record detail drawer

Selecting a non-lead record in the drawer opens:

- Record title and subtitle
- Responsive field grid
- Human-readable labels
- Related names instead of raw IDs
- Organization details where available
- Assigned staff details
- Creator or assignee details
- Supported task and follow-up history

The drawer resolves relationships to customers, leads, departments, teams, assigned employees, managers, team leads, users, and the organization. UUID values and internal IDs are hidden unless useful. Dates are converted to readable local formats.

### Pipeline interactions

| Interaction | Result |
|---|---|
| Total leads | Opens all pipeline leads |
| Total expected value | Opens pipeline leads |
| Payments in selected range | Opens payment records |
| Overdue | Opens leads with overdue payment status |
| Stage heading | Opens leads in that stage |
| Lead card | Opens full lead detail |
| Lead search | Filters cards by name or lead code |
| Payment badge | Shows paid, overdue, or unpaid state |

### Report interactions

| Interaction | Result |
|---|---|
| Active leads | Opens active lead records |
| Won | Opens completed leads |
| Customers | Opens customer records |
| Follow-ups | Opens customer and lead follow-ups |
| Overdue tasks | Opens overdue task records |
| Revenue | Opens payments in the selected range |
| Lead chart row | Opens leads with that status |
| Customer chart row | Opens customers with that status |
| Task chart row | Opens tasks with that status |

---

## 5.6 Record-page detail, edit, and action flows

Selecting the first field of a record table row opens an in-page detail modal. Edit, status, assignment, and history remain separate table actions.

### Common record detail modal

The modal contains:

- Record title
- Close X
- Loading state
- API error state
- Human-readable record fields
- Related names
- Close button

UUID-only values and internal ID fields are omitted. Lead details add separate Assignment History and Status History sections.

### Add/Edit record flow

Add and Edit open `RecordForm` as a modal. Supported fields include:

- Text
- Password
- Email
- URL
- Number
- Date
- Date/time
- Checkbox
- Text area
- JSON
- Single-select
- Multi-select
- Dynamic API options
- Dependent selects
- Conditional fields

Dynamic option errors, empty options, and invalid JSON are shown before save. Employee onboarding uses staff-type-specific fields. Successful save closes the form and reloads the table.

### Manager, Team Lead, Department, Team, and Employee pages

| Record | Available actions |
|---|---|
| Manager | View, edit, history, and role-approved delete behavior |
| Team Lead | View, edit, history, and role-approved delete behavior |
| Department | View, add, edit, and delete |
| Team | View, add, edit, and delete |
| Employee | View, add, edit, history, and role-approved delete behavior |
| Organization hierarchy | Expand/collapse departments, managers, teams, team leads, and employees |

### Customer page

- Add customer
- Edit customer
- Change assignment
- Add or remove tags
- Open customer detail
- Delete according to role policy
- Create follow-ups
- Move New to Contacted with a contact note and a changed tag
- Move Contacted to Under review
- Convert an Under review customer directly to a lead

### Lead page

- Open lead detail
- Edit permitted fields
- Change lead status
- Assign to employee
- View assignment history
- View status history
- Create the lead portal login while disbursing
- Create lead follow-up
- Generate or preserve repayment schedules

Lead status transitions are New → Contacted → Approved → Disbursed → Completed. Approved loan terms are stored on the lead. Disbursement requires portal-login credentials, and completion requires at least one repayment schedule.

### Task page

- Create task
- Edit task
- Assign recipient
- Set due date and priority
- Start pending task
- Complete in-progress task
- View task history
- Open task detail

Due and overdue tasks are included on Today. Completed and cancelled tasks are excluded from active previews.

### Follow-up pages

Customer and Lead follow-ups are separate tabs.

| Action | Result |
|---|---|
| Add | Opens follow-up create form |
| Edit | Opens follow-up update form |
| Call | Opens the contact phone number |
| Email | Opens the contact email |
| WhatsApp | Opens the WhatsApp composer |
| Add to calendar | Downloads an `.ics` meeting invite |
| Prepare invite email | Opens a prefilled email with meeting details |
| Mark complete | Opens the outcome form and completes the follow-up |
| Delete | Deletes according to role policy |

### Meeting invite flow

Meeting follow-ups include duration, location, meeting URL, and additional invitee emails.

- **Add to calendar** creates a title, start/end time, description, location, and attendees.
- **Prepare invite email** opens a mail link containing time, duration, location, URL, and notes.

### WhatsApp follow-up flow

The WhatsApp dialog loads saved templates and follow-up history.

It shows contact name, phone, follow-up type, scheduled time, and reason. It supports:

- Saved message
- Custom message
- Message preview
- Recent message status
- Expandable message body
- API error state

FINCRM prepares a WhatsApp URL but does not send silently. The user reviews and sends in WhatsApp.

### Repayment schedule and payment flows

**Repayment schedule**

- Generate schedule
- Select disbursed lead
- Set installment count
- Set first due date
- Select payment type

**Payment**

- Record payment
- Select repayment schedule
- Enter amount
- Enter payment date
- Select method and recipient
- Enter transaction reference
- Verify pending payment
- Reject pending payment
- Open payment detail

### Staff history flow

Employee, manager, and team-lead history actions open a history modal with assignment or employment entries and a no-history state.

---

## 5.7 Plan, subscription, settings, and Enterprise interactions

### Public plan checkout

1. Select Monthly or Yearly.
2. Load active plan catalog data.
3. View or confirm plan price.
4. Select a plan.
5. Confirm or change registration email in the checkout modal.
6. Provider order is created.
7. Razorpay Checkout opens.
8. After provider verification, a secure registration link is processed.
9. Registration creates the organization and subscription.

Unconfirmed or unavailable plans remain visible but disable the paid action.

### Enterprise inquiry

1. Select Enterprise.
2. Open Enterprise inquiry modal.
3. Enter contact, organization, website, LinkedIn, and requirements.
4. Submit with one-time client idempotency protection.
5. Receive acknowledgment.
6. Superadmin reviews the inquiry.
7. The team approves and creates an agreed plan.
8. The team sends a payment invitation.

### Enterprise custom-plan flow

- Edit customer details
- Change status
- Assign administrator
- Save internal notes
- Enter custom price and billing cycle
- Set maximum users and storage
- Add included services
- Add additional services
- Add feature JSON
- Add terms
- Send checkout invitation
- Resend registration link

Creation is blocked until the status is Approved and details are saved.

### Settings subscription card

Organization administrators see:

- Current or missing subscription
- Plan name
- Billing cycle
- Subscription reference
- Price
- Start date
- Renewal date
- Remaining days
- Staff usage
- Lead usage
- Renew/change plan action

The card links directly to Plans.

### Profile and password

- Save profile updates the backend and active profile state.
- Password change validates current password and new password before success.

---

## 5.8 AI assistant interactions

The Ask AI button opens a fixed chat panel containing:

- CRM Assistant title
- Role-scoped description
- Active status
- Close
- Welcome message
- User and assistant messages
- Thinking state
- Textarea
- Send button

The assistant sends only allowlisted, role-scoped records and summaries. It does not execute writes or expose raw sensitive fields.

---

## 5.9 Pagination and loading states

Record tables show Loading, Previous, Next, Empty, and API error states.

Drawers show Loading details and No matching records. Record modals show Loading record details and no-history states. Close and Back actions remain available.

---

## 6. Common buttons and actions

| Button/action | Usage |
|---|---|
| Add | Create a record |
| Refresh | Reload current data |
| Search | Filter records |
| Edit | Open record update form |
| Save / Update | Submit profile or record changes |
| Cancel | Close a form or dialog |
| Close / Back | Close a drawer or return to the previous level |
| Sign out | Revoke refresh session and return to login |
| View today | Open today's tasks and follow-ups |
| Open pipeline | Open pipeline board |
| Open report | Open report page |
| Start task | Move a task to in progress |
| Complete task | Move a task to completed |
| Mark complete | Complete a follow-up |
| Verify payment | Mark a payment verified |
| Reject payment | Mark a payment rejected |
| Call | Open a phone dialer |
| Email | Open an email composer |
| WhatsApp | Open the WhatsApp composer |
| Add to calendar | Download a meeting calendar invite |
| Ask AI | Open read-only CRM assistant |
| Send | Submit a question to the AI assistant |
| Enable checkout | Activate confirmed paid plans |
| Disable checkout | Suspend paid checkout |
| Send payment invitation | Email an approved Enterprise checkout |
| Resend registration | Replace the paid checkout registration link |

---

## 7. Current UI design system

### 7.1 Brand

- Brand: FINCRM
- Logo: red dragon in a circular white/red badge
- FIN letters use red
- CRM letters use dark navy or white according to the surface

### 7.2 Primary colors

| Purpose | Color | Hex |
|---|---|---|
| Primary navy | Sidebar and dark heroes | `#171D35` |
| Deep navy | Checkout and dark overlays | `#111629` |
| Primary red | Main brand, CTA, active accents | `#EC303B` |
| Red hover | Hover/pressed state | `#D82732` |
| Main text | Headings and strong labels | `#171D35` |
| Secondary text | Descriptions and metadata | `#768197` |
| Muted text | Helper and empty states | `#8793A6` |
| Page canvas | Workspace background | `#F5F6FA` |
| Card white | Cards and surfaces | `#FFFFFF` |
| Border | Card and input borders | `#E4E7EE` |
| Soft border | Separators and table lines | `#EDF0F4` |

### 7.3 Status colors

| State | Background | Text |
|---|---:|---:|
| Success/Paid/Completed/Verified | `#EDF8F2` | `#16845A` |
| Warning/Pending/Partial | `#FFF7E7` | `#9A6A10` |
| Error/Overdue/Rejected/Cancelled | `#FFF0F1` | `#C12B38` |
| Neutral | `#F2F4F7` | `#536177` |

### 7.4 Surface design

- Fixed left sidebar on desktop
- Width: 248px
- Independently scrollable navigation
- Fixed sidebar profile and sign-out footer
- Navy sidebar with subtle section separators
- Red active-navigation marker
- Rounded cards
- Card radius: approximately 14px
- Form radius: approximately 9px
- Modal radius: approximately 16px
- Soft neutral borders
- Subtle card shadows
- White content surfaces on a light gray canvas
- Dark welcome and dashboard heroes
- Right-side detail drawer
- Full-screen modal overlays

### 7.5 Typography

- Font stack: Inter, Segoe UI, system sans-serif
- Brand weight: Extra bold
- Page headings: Bold
- Section headings: Semi-bold
- Labels: Bold and compact
- Secondary text: Regular
- Uppercase labels are used sparingly for status, role, and eyebrow text

### 7.6 Responsive behavior

- Desktop: Fixed 248px sidebar and main content area
- Record tables use horizontal overflow
- Pipeline uses horizontal columns
- Mobile: Sidebar becomes a fixed bottom navigation bar
- Records list is hidden or reduced on mobile
- Dashboard hero remains readable and keeps its main action visible
- Settings forms change to one column
- Details drawer fills the available mobile width
- Plan grid changes from desktop columns to one column

---

## 8. Interaction requirements

- Active navigation item must be visually clear
- The Records section should expand without moving the profile/footer
- Sidebar navigation must scroll independently
- Profile and sign-out must remain at the bottom of the desktop sidebar
- Active role must be displayed clearly
- Table rows should open detail views when the first record field is selected
- Forms must show validation and loading states
- API and network errors must be visible
- Dialogs must support close/cancel actions
- Mobile controls must remain reachable
- Primary destructive actions should require confirmation where appropriate
- Date filters must apply to dashboard, pipeline, and reports
- Record detail actions must remain role-checked

---

## 9. Functional exclusions and unresolved scope

The following items require approved business or deployment decisions and are not considered complete:

- Real approved plan prices
- Live checkout enablement
- Automatic recurring-billing reconciliation
- Razorpay failed-payment/renewal webhook workflow
- Proration or downgrade refunds
- Grace-period policy for expired or cancelled subscriptions
- Customer/storage/advanced-report entitlement enforcement
- Production database migration rehearsal
- SMTP production delivery verification
- WhatsApp provider delivery
- Document and payment-proof customer workflows
- Production Redis rate limiting
- Final security and deployment hardening

---

## 10. Acceptance criteria

The UI and functional scope should be considered complete for a release only when:

1. The current role can access only authorized screens and records.
2. Desktop and mobile layouts render without clipped sidebar actions.
3. Records remain one item per row and expand correctly.
4. The sidebar logo, organization name, role, and profile area remain visually consistent.
5. Profile/sign-out remain fixed at the bottom of the desktop sidebar.
6. Dashboard, Pipeline, Report, Today, Settings, and record screens use the same theme.
7. Primary actions use the FINCRM red treatment.
8. Success, warning, and error states use the documented colors.
9. Dialog and drawer controls remain usable on desktop and mobile.
10. Public plans, Enterprise checkout, and Lead Portal remain aligned with the same brand system.
11. Frontend production build passes.
12. Backend and payment features are verified against the approved environment.
