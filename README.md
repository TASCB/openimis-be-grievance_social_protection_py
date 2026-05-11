# openIMIS Backend Grievance Social Protection reference module
This repository holds the files of the openIMIS Backend grievance social protection reference module.
It is dedicated to be deployed as a module of [openimis-be_py](https://github.com/openimis/openimis-be_py).

## Configuration options (can be changed via core.ModuleConfiguration)
Rights required:
* `resolution_times`: time to resolution in form of CRON timedelta: {days},{hours} where days are values between <0, 99) and hours are between 0 and 24. 
(default: `5,0`)
* `default_resolution`: The field will be in form of the JSON dictionary with pairs like: 
Key - type of the grievance, 
Value - time to resolution in form of CRON timedelta: `{days},{hours}` where days are values between <0, 99) and hours are between 0 and 24.
(default: `{Default: '5,0'}`)
Note: If for given type of the grievance time is not provided then default value is used from `resolution_times`. 

## Email notifications

When a user is set as `attending_staff` on a ticket — either at creation or via update —
an email is sent to that user's address. Triggered by `TicketService.create` and
`TicketService.update` (see `notifications.notify_assignment`). On update, the email
fires only when the assignee changes to a non-null value, so re-saves don't re-notify.

Delivery uses Django's `send_mail` with the SMTP backend already configured in
`openIMIS/settings/base.py`. Failures are logged and never block the mutation —
if the assignee has no email, the send is skipped silently.

### Mailtrap configuration

Set these environment variables before starting the backend (Mailtrap → My Inbox → SMTP Settings):

```
EMAIL_HOST=sandbox.smtp.mailtrap.io
EMAIL_PORT=2525
EMAIL_HOST_USER=<your mailtrap username>
EMAIL_HOST_PASSWORD=<your mailtrap password>
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=no-reply@openimis.local
```

All assignment emails will appear in your Mailtrap inbox instead of being sent to real recipients.
