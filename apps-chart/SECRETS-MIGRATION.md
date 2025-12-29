# Secrets Migration Summary

## Overview

All sensitive data (passwords, secret keys) have been migrated from plain text environment variables to Kubernetes Secrets for improved security.

## Changes Made

### 1. Secret Resources Created

The following Secret resources have been created:

- **`compote-secret.yaml`**: CapRover password
- **`nextcloud-secret.yaml`**: Admin password, MySQL password, MySQL root password
- **`bugsink-secret.yaml`**: Secret key
- **`paperless-secret.yaml`**: Secret key
- **`hoarder-secret.yaml`**: NextAuth secret, MeiliSearch master key
- **`immich-secret.yaml`**: Database password, PostgreSQL password

### 2. Deployment Templates Updated

All deployment templates now reference Secrets using `secretKeyRef` instead of plain environment variables:

```yaml
env:
- name: SECRET_KEY
  valueFrom:
    secretKeyRef:
      name: bugsink-secrets
      key: secret-key
```

### 3. Values.yaml Structure

Sensitive values have been moved from `environment:` to `secrets:` sections:

**Before:**
```yaml
environment:
  SECRET_KEY: ""
  PASSWORD: "plaintext"
```

**After:**
```yaml
environment:
  # Non-sensitive env vars only
secrets:
  secretKey: ""
  password: "plaintext"
```

### 4. Questions.yaml Updated

Password fields in `questions.yaml` now reference the `secrets` paths:

- `nextcloud.secrets.adminPassword`
- `bugsink.secrets.secretKey`
- `paperless.secrets.secretKey`
- `compote.secrets.caproverPassword`
- `nextcloud.secrets.mysqlPassword`
- `nextcloud.secrets.mysqlRootPassword`

## Security Improvements

✅ **Passwords are now stored in Kubernetes Secrets** (encrypted at rest)
✅ **No plain text passwords in environment variables**
✅ **Rancher will automatically handle password fields as Secrets**
✅ **Secrets are base64 encoded by Kubernetes**

## Applications Updated

1. **Compote** - CapRover password
2. **Nextcloud** - Admin password, MySQL passwords
3. **Bugsink** - Secret key
4. **Paperless** - Secret key
5. **Hoarder** - NextAuth secret, MeiliSearch master key
6. **Immich** - Database passwords

## Migration Notes

- Default values are still provided in `values.yaml` for convenience
- Users should change all default passwords before production deployment
- Rancher will prompt for password values during installation
- Secrets are created automatically when applications are enabled

## Verification

To verify Secrets are created correctly:

```bash
# List all secrets
kubectl get secrets

# View a specific secret (base64 encoded)
kubectl get secret bugsink-secrets -o yaml

# Decode a secret value
kubectl get secret bugsink-secrets -o jsonpath='{.data.secret-key}' | base64 -d
```

## Backward Compatibility

⚠️ **Breaking Change**: If you have existing deployments using the old structure, you'll need to:
1. Update your values.yaml to use the new `secrets:` structure
2. Redeploy the applications
3. The old environment variables will no longer work

## Next Steps

1. Review and update all default passwords in `values.yaml`
2. Consider using external secret management (Vault, Sealed Secrets) for production
3. Rotate all secrets after initial deployment
4. Document secret rotation procedures

