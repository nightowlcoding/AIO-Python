# Manager Onboarding SOP (Dexter Assistant)

Last updated: 2026-06-23
Owner: Super Admin

## 1. Purpose
Use this SOP to onboard new managers consistently and safely in Dexter Assistant.

## 2. Pre-Onboarding Go/No-Go Checklist (Super Admin)
Complete this before inviting any manager.

- [ ] Email test is passing from Admin Email settings.
- [ ] Super Admin account is working and password is strong.
- [ ] Backup exists for `dexter_assistant_rbac.db`.
- [ ] Company and location records are correct.
- [ ] Each manager is assigned to the correct company and location(s).
- [ ] Audit log page is loading and recording actions.
- [ ] Security test suite status is green.

## 3. Admin Setup Steps (Create Manager Accounts)
1. Sign in as Super Admin at `/auth/login`.
2. Go to `/admin`.
3. Set company scope:
- Use Company Scope selector (or `PATCH /api/admin/company-scope`).
4. Go to Users:
- `/admin/users`
5. Create each manager account:
- Username: unique and work-identifiable.
- Role: `Manager`.
- Company: verify selected scope is correct.
- Locations: assign only their real store(s).
6. If using invite flow, send invite and verify delivery:
- `POST /admin/users/invite`
7. Verify account appears active and scoped correctly.

## 4. Manager First Login SOP
Send this to each manager.

1. Open Dexter Assistant login page: `/auth/login`.
2. Sign in with assigned credentials.
3. If prompted, complete password reset flow:
- Forgot password: `/auth/forgot-password`
- Reset link target: `/auth/reset-password/<token>`
4. Confirm access to only assigned company/location data.
5. Confirm they can open their required area from portal:
- `/portal`
- `/portal/productmix`
- `/portal/ic3`

## 5. Day-One Manager Verification (5-minute check)
A Super Admin should validate each new manager account once.

- [ ] Manager can log in.
- [ ] Manager sees only their company data.
- [ ] Manager cannot access other companies.
- [ ] Manager can perform expected work pages/actions.
- [ ] Manager cannot access Super Admin-only actions.

## 6. Daily Operations SOP (Managers)
Start of shift:
1. Log in at `/auth/login`.
2. Confirm correct company/location context.
3. Open required portal app(s) from `/portal`.

During shift:
1. Perform normal operational updates in assigned app pages.
2. Report issues immediately if scope/access looks wrong.

End of shift:
1. Confirm work saved.
2. Log out at `/auth/logout`.

## 7. Security Rules (Managers)
- Do not share credentials.
- Use only your own account.
- Log out on shared devices.
- Report suspicious access or missing data immediately.
- After repeated failed logins, wait for lockout window or contact Super Admin.

## 8. Offboarding SOP (Super Admin)
When a manager leaves or changes role:
1. Go to `/admin/users`.
2. Set account inactive for immediate access removal.
3. Reassign any needed responsibilities.
4. Record reason in internal notes.
5. Verify offboarding action appears in `/admin/audit-logs`.

## 9. Weekly Admin Audit (Recommended)
Once per week, Super Admin reviews:
- Users and role assignments (`/admin/users`)
- Company and location scope correctness
- Audit trail (`/admin/audit-logs`)
- Email settings health (`/admin/email`)

## 10. Emergency Contacts and Escalation
Define and keep this section current:
- Primary owner:
- Backup owner:
- IT/support contact:
- Escalation channel:
