# Deploy Dexter Assistant on Render

This setup deploys Dexter Assistant as one Render web service that starts the two internal apps (ProductMix and Inventory Control 3) behind the proxy routes.

## Why this config

- Uses one Gunicorn worker so child-process app management is predictable.
- Binds to 0.0.0.0:$PORT for Render.
- Installs dependencies required by both internal apps.

## Option A: Render Blueprint (recommended)

1. Push this project to GitHub.
2. In Render, choose New > Blueprint.
3. Select your repo.
4. Set Blueprint Path to Dexter Assistant/render.yaml.
5. Wait for deploy to finish, then open the generated URL.

## Option B: Manual Web Service

1. In Render, choose New > Web Service.
2. Connect your repo.
3. Set Root Directory to Dexter Assistant.
4. Set Build Command to:

   pip install -r requirements_dexter_assistant.txt

5. Set Start Command to:

   gunicorn --workers 1 --threads 8 --timeout 120 --bind 0.0.0.0:$PORT dexter_assistant:app

6. Add environment variables:

   - PYTHONUNBUFFERED=1
   - PM_OPEN_BROWSER=0
   - PM_DEBUG=0

7. Deploy.

## DNS mapping from GoDaddy

After Render provides your public app URL:

1. In Render, add custom domain: app.dexterassist.com.
2. Copy the DNS target Render gives you.
3. In GoDaddy DNS for dexterassist.com, create or update a CNAME:
   - Host: app
   - Points to: Render target hostname
4. Wait for DNS propagation and SSL issuance.

## Important notes

- The service uses local loopback ports (127.0.0.1:5050 and 127.0.0.1:5003) internally inside one Render instance.
- Keep Gunicorn worker count at 1 unless app management logic is redesigned for multi-worker process coordination.
