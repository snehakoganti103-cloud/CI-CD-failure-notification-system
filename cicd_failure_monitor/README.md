# CI/CD Build Failure Monitor (starter project)

A small Flask application that receives build-result callbacks from Jenkins, GitHub Actions and GitLab CI/CD, stores them in SQLite, and displays a unified dashboard with rule-based explanations.

## 1. Architecture

Developer pushes code -> CI provider runs build/tests -> provider sends a signed/shared-secret callback -> Flask receiver validates it -> SQLite stores build -> dashboard displays status and explanation.

Important: the CI provider performs the build. This website does not replace Jenkins/GitHub Actions/GitLab runners. It centralizes monitoring and diagnosis.

## 2. Requirements

- Python 3.10+
- Git
- A GitHub, GitLab, or Jenkins project
- A publicly reachable HTTPS URL for the Flask app when receiving callbacks from cloud CI services

## 3. Run locally (Windows PowerShell)

```powershell
cd cicd_failure_monitor
py -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:WEBHOOK_TOKEN="replace-this-with-a-long-random-secret"
$env:DATABASE_PATH="builds.db"
python app.py
```

Open http://127.0.0.1:5000

For a quick local test, open a second PowerShell window and run:

```powershell
$body = @{
  project = "Demo Student Project"
  branch = "main"
  build_number = "1"
  status = "FAILURE"
  build_url = "https://example.com/build/1"
  failure_reason = "ModuleNotFoundError: No module named 'flask'"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:5000/webhooks/github-actions" `
  -Method Post -ContentType "application/json" `
  -Headers @{"X-Webhook-Token"="replace-this-with-a-long-random-secret"} `
  -Body $body
```

Refresh the dashboard. A failure explanation should appear.

## 4. Connect GitHub Actions

1. Push this project to a GitHub repository.
2. In the repository, open Settings -> Secrets and variables -> Actions.
3. Add repository secrets:
   - `MONITOR_URL`: public base URL of your deployed Flask app, e.g. `https://your-domain.example`
   - `MONITOR_WEBHOOK_TOKEN`: same secret value as `WEBHOOK_TOKEN` on the Flask server.
4. Keep `.github/workflows/ci.yml` in the repository.
5. Push a commit. Open Actions and inspect the run. The final step sends the result to your dashboard.

The included workflow uses `if: always()` so the notification step runs even if a previous step fails.

## 5. Connect GitLab CI/CD

1. Add `.gitlab-ci.yml` to the repository root.
2. In GitLab, open Settings -> CI/CD -> Variables.
3. Add:
   - `MONITOR_URL`
   - `MONITOR_WEBHOOK_TOKEN`
4. Mark the token masked and protected where appropriate.
5. Push a commit and inspect Build -> Pipelines.

The sample sends a callback from `after_script`. Test the exact behavior with your GitLab runner and project settings.

## 6. Connect Jenkins

1. Install Jenkins and create a Pipeline job connected to your Git repository.
2. Save the included `Jenkinsfile` in the repository root.
3. In Jenkins, add a Secret text credential with ID `monitor-webhook-token`.
4. Configure environment variables `MONITOR_URL` and make the credential available to the pipeline.
5. Replace the sample Build and Test commands with your actual commands.
6. Run the pipeline.

The example uses `curl`; ensure curl is installed on the Jenkins agent. For production, avoid interpolating untrusted values into shell commands; send JSON using a safer script or HTTP client.

## 7. Public callback URL for testing

A cloud CI service cannot call `127.0.0.1` on your computer. During local testing, use a secure HTTPS tunnel such as ngrok or deploy the app to a server. Do not expose Flask's development server directly to the internet.

For deployment, use a production WSGI server (for example Gunicorn on Linux) behind HTTPS/reverse proxy. Keep secrets in environment variables or a secret manager.

## 8. How to improve diagnosis

The included `diagnose()` function is rule-based, not a true AI model. It recognizes common error phrases and returns likely causes and next steps.

Next upgrades:
- Save a limited, sanitized log excerpt from each CI provider.
- Add provider API integrations to fetch complete logs after validating ownership and permissions.
- Add an LLM API behind the backend to summarize logs. Redact secrets, tokens, personal data and environment variables before sending logs to an AI service.
- Add users, project ownership, filters, pagination, email notifications and charts.
- Add retry handling and a background task queue for slow analysis.

## 9. Security checklist

- Use HTTPS.
- Replace the demo token with a long random secret.
- Use separate secrets per provider/project in production.
- Never put tokens in frontend JavaScript or commit them to Git.
- Validate provider signatures if receiving native GitHub/GitLab webhooks directly.
- Limit request body size and rate-limit endpoints.
- Redact credentials and secrets from logs before storing or analyzing them.
- Add authentication to the dashboard before hosting it publicly.
- Use a production WSGI server; do not use Flask debug mode in production.

## 10. Current MVP limitations

- It stores a short failure summary supplied by the pipeline, not full raw logs.
- The diagnosis is rule-based and may not identify every root cause.
- It uses one shared demo token for simplicity.
- It has no login or multi-user authorization yet.
