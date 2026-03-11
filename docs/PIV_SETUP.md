# ASTRA — CAC / PIV Smart Card Authentication Setup

This document covers the reverse-proxy configuration required for
CAC/PIV (X.509 client certificate) authentication to work with ASTRA.

## How It Works

1. The user inserts their CAC/PIV smart card and navigates to ASTRA.
2. The TLS-terminating reverse proxy (nginx or Apache) performs the
   TLS client-certificate handshake.
3. The proxy extracts the client certificate and forwards it to the
   ASTRA backend in the `X-Client-Cert` HTTP header (PEM, URL-encoded).
4. ASTRA's `/api/v1/auth/piv/authenticate` endpoint validates the
   certificate chain against the DoD CA bundle and extracts the user's
   identity (CN, EDIPI, email) from the Subject DN and SANs.

---

## Environment Variables

Set these in the ASTRA backend `.env` file:

```env
AUTH_PROVIDER=piv                     # or keep "local" and access PIV via /auth/piv/authenticate
PIV_CA_BUNDLE_PATH=/etc/ssl/dod-ca-bundle.pem
PIV_REQUIRE_OCSP=false                # set true for OCSP stapling validation
PIV_CRL_URL=                          # optional CRL override
```

## Obtaining the DoD CA Bundle

Download the latest DoD PKI CA certificates from:
- https://public.cyber.mil/pki-pke/

Combine the root and intermediate CAs into a single PEM bundle:

```bash
cat DoD_Root_CA_*.pem DoD_ID_CA_*.pem > /etc/ssl/dod-ca-bundle.pem
```

---

## nginx Configuration

```nginx
server {
    listen 443 ssl;
    server_name astra.mil;

    # ── Server TLS ──
    ssl_certificate     /etc/ssl/astra-server.crt;
    ssl_certificate_key /etc/ssl/astra-server.key;
    ssl_protocols       TLSv1.2 TLSv1.3;

    # ── Client Certificate (CAC/PIV) ──
    ssl_client_certificate /etc/ssl/dod-ca-bundle.pem;
    ssl_verify_client      optional;   # "optional" = prompt but don't require
    ssl_verify_depth       4;          # DoD chain depth

    # Forward the client cert to the backend
    location /api/ {
        proxy_pass http://127.0.0.1:8000;

        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # URL-encode the PEM cert and pass as a header
        proxy_set_header X-Client-Cert     $ssl_client_escaped_cert;

        # Also forward verification status
        proxy_set_header X-Client-Verify   $ssl_client_verify;
        proxy_set_header X-Client-DN       $ssl_client_s_dn;
    }

    # Frontend (Next.js)
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
    }
}
```

### Key nginx directives

| Directive | Purpose |
|-----------|---------|
| `ssl_client_certificate` | Path to the trusted CA bundle (DoD CAs) |
| `ssl_verify_client optional` | Prompts the browser for a cert but doesn't block if none is provided |
| `ssl_verify_depth 4` | Allows the 3-4 level DoD certificate chain |
| `$ssl_client_escaped_cert` | Built-in nginx variable: PEM cert, URL-encoded |

---

## Apache Configuration

```apache
<VirtualHost *:443>
    ServerName astra.mil

    # ── Server TLS ──
    SSLEngine on
    SSLCertificateFile    /etc/ssl/astra-server.crt
    SSLCertificateKeyFile /etc/ssl/astra-server.key

    # ── Client Certificate (CAC/PIV) ──
    SSLCACertificateFile /etc/ssl/dod-ca-bundle.pem
    SSLVerifyClient      optional
    SSLVerifyDepth       4

    # Forward cert to backend
    RequestHeader set X-Client-Cert "%{SSL_CLIENT_CERT}e"
    RequestHeader set X-Client-Verify "%{SSL_CLIENT_VERIFY}s"

    # Backend
    ProxyPass        /api/ http://127.0.0.1:8000/api/
    ProxyPassReverse /api/ http://127.0.0.1:8000/api/

    # Frontend
    ProxyPass        / http://127.0.0.1:3000/
    ProxyPassReverse / http://127.0.0.1:3000/
</VirtualHost>
```

---

## Browser Configuration

### Windows (Chrome / Edge)
CAC middleware (e.g. ActivClient) automatically registers the smart-card
certificates in the Windows certificate store. Chrome and Edge will
prompt the user to select a certificate during the TLS handshake.

### Firefox
Firefox uses its own certificate store. You need to:
1. Go to `about:preferences#privacy` → Certificates → Security Devices
2. Load the PKCS#11 module for your smart-card reader
3. Import the DoD root CAs into Firefox's trust store

### macOS
Install the DoD certificates into the System Keychain and mark the
root CAs as trusted for SSL.

---

## Testing Without a Real CAC

For development, you can generate a self-signed client cert:

```bash
# Generate CA
openssl req -x509 -newkey rsa:2048 -keyout ca.key -out ca.crt -days 365 -nodes -subj "/CN=Test CA"

# Generate client cert
openssl req -newkey rsa:2048 -keyout client.key -out client.csr -nodes \
    -subj "/CN=DOE.JOHN.Q.1234567890/emailAddress=john.doe@mil"
openssl x509 -req -in client.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
    -out client.crt -days 365

# Test with curl
curl -k --cert client.crt --key client.key https://localhost/api/v1/auth/piv/authenticate
```

Set `PIV_CA_BUNDLE_PATH` to your `ca.crt` for local testing.

---

## Security Considerations

- **OCSP Stapling**: Set `PIV_REQUIRE_OCSP=true` in production to verify
  certificate revocation in real time.
- **CRL Checking**: Configure `PIV_CRL_URL` to point to the DoD CRL
  distribution point for offline revocation checking.
- **Pin Caching**: The smart-card PIN is cached by the OS/middleware for the
  duration of the session. ASTRA does not handle PIN entry.
- **Certificate Rotation**: DoD CA bundles are updated periodically.
  Automate the download and reload of `dod-ca-bundle.pem`.
