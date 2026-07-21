# CBE Exchange Rates JSON

This project fetches daily exchange rates from the Central Bank of Egypt website and saves them as a clean JSON file for reuse by other systems.

Source page:

https://www.cbe.org.eg/en/economic-research/statistics/cbe-exchange-rates

## Output

The updater writes the latest parsed data to:

```text
rates/latest.json
```

The file is a flat JSON array. Each row follows this shape:

```json
{
  "rate_date": "2026-07-20",
  "updated_at": "2026-07-20T00:30:15",
  "currency_code": "USD",
  "currency_name": "US Dollar",
  "buy_rate": 48.25,
  "sell_rate": 48.35,
  "source": "Central Bank of Egypt",
  "source_url": "https://www.cbe.org.eg/en/economic-research/statistics/cbe-exchange-rates"
}
```

## Run Locally

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Run the updater:

```bash
python update_rates.py
```

The script creates the `rates` directory automatically if it does not already exist.

SSL certificate verification is enabled by default. If a controlled local environment has certificate-chain problems, you can opt in to an insecure local run:

```bash
CBE_ALLOW_INSECURE_SSL=true python update_rates.py
```

PowerShell equivalent:

```powershell
$env:CBE_ALLOW_INSECURE_SSL = "true"; python update_rates.py
```

Use that only as a local workaround. Scheduled production runs should keep normal certificate verification enabled.

## GitHub Actions

The workflow at `.github/workflows/update-cbe-rates.yml` runs every day at 12:30 AM Cairo time.

GitHub Actions cron uses UTC, so the workflow schedule is:

```yaml
cron: "30 22 * * *"
```

You can also run it manually from GitHub:

1. Open the repository on GitHub.
2. Go to the Actions tab.
3. Select `Update CBE exchange rates`.
4. Click `Run workflow`.

If `rates/latest.json` changes, the workflow commits and pushes the updated file. If nothing changes, it exits gracefully without committing.

## Raw GitHub URL

After publishing this project to GitHub, the raw JSON URL will usually look like:

```text
https://raw.githubusercontent.com/<owner>/<repo>/<branch>/rates/latest.json
```

Replace `<owner>`, `<repo>`, and `<branch>` with your repository details, for example:

```text
https://raw.githubusercontent.com/itaxii/cbe-exchange-rates/main/rates/latest.json
```

## Source Attribution

Exchange rates are sourced from the Central Bank of Egypt website. Reuse should clearly attribute the Central Bank of Egypt and include the source URL. This project republishes parsed source data and does not own, create, or independently verify the exchange-rate data.

The scheduled job fetches the CBE page once per run. Avoid running it repeatedly or aggressively so the source website is not unnecessarily burdened.
