# Payment Provider Secrets

This directory holds PEM keys and other sensitive credentials for payment
providers used by the Dify API.

**Never commit any actual secrets.** The `.gitignore` rule keeps this
directory empty in git — only `README.md` and `.gitkeep` are tracked.

## Alipay

Place these files locally (or mount via Kubernetes Secret in production):

- `alipay/app_private_key.pem` — Merchant application private key
- `alipay/alipay_public_key.pem` — Alipay platform public key

Configure their paths in `api/.env`:

```env
ALIPAY_APP_PRIVATE_KEY_PATH=/absolute/path/to/api/secrets/alipay/app_private_key.pem
ALIPAY_PUBLIC_KEY_PATH=/absolute/path/to/api/secrets/alipay/alipay_public_key.pem
```

## Generating Keys

1. Generate an RSA 2048 keypair locally:

   ```bash
   openssl genrsa -out app_private_key.pem 2048
   openssl rsa -in app_private_key.pem -pubout -out app_public_key.pem
   ```

2. Upload the **application public key** (`app_public_key.pem`) to the
   Alipay merchant console.

3. Download the **Alipay platform public key** from the merchant console
   and save it as `alipay_public_key.pem` in this directory.
