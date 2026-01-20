# Synchro iObeya-GitHub Helm Chart

This Helm chart deploys the Synchro iObeya-GitHub application on Kubernetes.

## Prerequisites

- Kubernetes 1.19+
- Helm 3.0+

## Installation

### Basic Installation

```bash
helm install synchro-iobeya-github ./synchro-iobeya-github \
  --set secret.env.ACCESS_KEY="your-access-key" \
  --set secret.env.GITHUB_TOKEN="your-github-token" \
  --set secret.env.IOBEYA_TOKEN="your-iobeya-token"
```

### Installation with Custom Configuration

```bash
helm install synchro-iobeya-github ./synchro-iobeya-github \
  --set-file config=./config.yaml \
  --values custom-values.yaml
```

### Using External Secrets

For production deployments, it's recommended to use an external secret management solution:

```yaml
# custom-values.yaml
secret:
  create: false
  existingSecret: "synchro-iobeya-github-secrets"  # Pre-created secret
```

## Configuration

The following table lists the configurable parameters and their default values:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `image.repository` | Docker image repository | `synchro-iobeya-github` |
| `image.tag` | Docker image tag | `latest` |
| `image.pullPolicy` | Image pull policy | `IfNotPresent` |
| `replicaCount` | Number of replicas | `1` |
| `service.type` | Kubernetes service type | `ClusterIP` |
| `service.port` | Service port | `80` |
| `service.targetPort` | Container target port | `28080` |
| `ingress.enabled` | Enable ingress | `false` |
| `resources.limits.cpu` | CPU limit | `500m` |
| `resources.limits.memory` | Memory limit | `512Mi` |
| `resources.requests.cpu` | CPU request | `100m` |
| `resources.requests.memory` | Memory request | `128Mi` |
| `securityContext.runAsNonRoot` | Run as non-root user | `true` |
| `securityContext.runAsUser` | User ID to run as | `10001` |
| `securityContext.fsGroup` | File system group ID | `10001` |
| `securityContext.seccompProfile.type` | Seccomp profile type | `RuntimeDefault` |
| `containerSecurityContext.allowPrivilegeEscalation` | Allow privilege escalation | `false` |
| `containerSecurityContext.capabilities.drop` | Capabilities to drop | `["ALL"]` |
| `containerSecurityContext.readOnlyRootFilesystem` | Read-only root filesystem | `false` |
| `podDisruptionBudget.enabled` | Enable PDB | `false` |
| `podDisruptionBudget.minAvailable` | Minimum available pods | `1` |
| `secret.create` | Create secret resource | `true` |
| `secret.existingSecret` | Use existing secret | `""` |

## Security Features

This chart implements several security best practices:

- **Pod Security Context**: Configurable non-root user (default UID 10001)
- **Container Security Context**: Drop all capabilities by default
- **No Privilege Escalation**: Prevents container from gaining additional privileges
- **Seccomp Profile**: RuntimeDefault profile for enhanced security
- **Resource Limits**: Prevents resource exhaustion
- **Health Probes**: Automatic pod health monitoring

### Customizing Security Context

You can customize the security settings:

```yaml
# values.yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1000  # Custom UID
  fsGroup: 1000    # Custom group

containerSecurityContext:
  allowPrivilegeEscalation: false
  capabilities:
    drop:
      - ALL
  readOnlyRootFilesystem: false  # Set to true if your app supports it
```

**Note**: Ensure the Docker image's user matches `runAsUser` or use a user that exists in the container.

## Health Checks

The deployment includes:

- **Liveness Probe**: Checks if the application is alive (30s initial delay)
- **Readiness Probe**: Checks if the application is ready to serve traffic (5s initial delay)

Both probes use the `/healthz` endpoint.

## Pod Disruption Budget

To enable PDB for production resilience:

```yaml
podDisruptionBudget:
  enabled: true
  minAvailable: 1
```

## Upgrading

```bash
helm upgrade synchro-iobeya-github ./synchro-iobeya-github \
  --values custom-values.yaml
```

## Uninstallation

```bash
helm uninstall synchro-iobeya-github
```

## Troubleshooting

### Check Pod Status

```bash
kubectl get pods -l app.kubernetes.io/name=synchro-iobeya-github
```

### View Logs

```bash
kubectl logs -l app.kubernetes.io/name=synchro-iobeya-github -f
```

### Test Health Endpoint

```bash
kubectl port-forward svc/synchro-iobeya-github 8080:80
curl http://localhost:8080/healthz
```

## Values Schema Validation

This chart includes a `values.schema.json` file that validates your configuration during installation. If you provide invalid values, Helm will reject the installation with a clear error message.

## External Secret Management

For production deployments, consider using:

- **Sealed Secrets**: Encrypt secrets in Git
- **External Secrets Operator**: Sync from external secret stores (Vault, AWS Secrets Manager, etc.)
- **Kubernetes Secrets CSI Driver**: Mount secrets from external sources

Example with External Secrets Operator:

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: synchro-iobeya-github-secrets
spec:
  secretStoreRef:
    name: vault-backend
  target:
    name: synchro-iobeya-github-secrets
  data:
    - secretKey: ACCESS_KEY
      remoteRef:
        key: synchro/access-key
    - secretKey: GITHUB_TOKEN
      remoteRef:
        key: synchro/github-token
    - secretKey: IOBEYA_TOKEN
      remoteRef:
        key: synchro/iobeya-token
```

## License

See the main project LICENSE file.
