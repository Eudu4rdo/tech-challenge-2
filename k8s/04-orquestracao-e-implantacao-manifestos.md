# 4 - Orquestracao e Implantacao (Manifestos)

Este guia documenta a camada de Kubernetes usada para implantar os 5 microsservicos do projeto ToggleMaster.

O objetivo e organizar os recursos em manifests separados, com:

- `Namespace` para isolar o ambiente
- `ConfigMap` para dados nao sensiveis
- `Secret` para credenciais, chaves e strings de conexao
- `Deployment` para controlar os Pods
- `Service` do tipo `ClusterIP` para acesso interno
- `Ingress` para expor apenas os endpoints publicos necessarios

## Estrutura sugerida

```text
k8s/
  namespace.yaml
  configmaps/
    app-config.yaml
    evaluation-config.yaml
    analytics-config.yaml
  secrets/
    dev/
      auth-service.yaml
      flag-service.yaml
      targeting-service.yaml
      evaluation-service.yaml
      analytics-service.yaml
    prod/
      auth-service.yaml
      flag-service.yaml
      targeting-service.yaml
      evaluation-service.yaml
      analytics-service.yaml
  deployments/
  services/
  ingress.yaml
```

## Padrao adotado

Todos os recursos devem usar o namespace `tech-challenge-2`.

Isso evita misturar a stack com outros ambientes e deixa mais claro quais objetos pertencem ao projeto.

## 1. Namespace

O primeiro arquivo a ser aplicado e o namespace:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: tech-challenge-2
```

Aplicacao:

```bash
kubectl apply -f k8s/namespace.yaml
```

## 2. ConfigMaps

Use `ConfigMap` apenas para dados nao sensiveis.

No projeto, os valores que entram aqui sao principalmente:

- URLs internas entre servicos
- porta padrao
- nome da tabela do DynamoDB
- nome da fila SQS
- regiao AWS

### Arquivos ja criados

- `k8s/configmaps/app-config.yaml`
- `k8s/configmaps/evaluation-config.yaml`
- `k8s/configmaps/analytics-config.yaml`

### Exemplo de uso

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
  namespace: tech-challenge-2
data:
  AWS_REGION: us-east-1
  AUTH_SERVICE_URL: http://auth-service:8001
  FLAG_SERVICE_URL: http://flag-service:8002
  TARGETING_SERVICE_URL: http://targeting-service:8003
```

### Aplicacao

```bash
kubectl apply -f k8s/configmaps/
```

## 3. Secrets

`Secret` deve ser usado para tudo que nao pode ficar em texto puro.

No projeto, os segredos que precisam entrar aqui sao:

- `DATABASE_URL`
- `MASTER_KEY`
- `SERVICE_API_KEY`
- credenciais AWS do `analytics-service`

### Regra obrigatoria

Os valores do `Secret` devem estar em base64.

Exemplo:

```bash
echo -n "master-key-local" | base64
```

### Arquivos ja criados

Ambiente de dev:

- `k8s/secrets/dev/auth-service.yaml`
- `k8s/secrets/dev/flag-service.yaml`
- `k8s/secrets/dev/targeting-service.yaml`
- `k8s/secrets/dev/evaluation-service.yaml`
- `k8s/secrets/dev/analytics-service.yaml`

Ambiente de prod:

- `k8s/secrets/prod/auth-service.yaml`
- `k8s/secrets/prod/flag-service.yaml`
- `k8s/secrets/prod/targeting-service.yaml`
- `k8s/secrets/prod/evaluation-service.yaml`
- `k8s/secrets/prod/analytics-service.yaml`

### Mapeamento por servico

| Servico | Secret | Campos |
| --- | --- | --- |
| `auth-service` | `dev-auth-secrets` / `prod-auth-secrets` | `DATABASE_URL`, `MASTER_KEY` |
| `flag-service` | `dev-flag-secrets` / `prod-flag-secrets` | `DATABASE_URL` |
| `targeting-service` | `dev-targeting-secrets` / `prod-targeting-secrets` | `DATABASE_URL` |
| `evaluation-service` | `dev-evaluation-secrets` / `prod-evaluation-secrets` | `SERVICE_API_KEY` |
| `analytics-service` | `dev-analytic-secrets` / `prod-analytic-secrets` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` |

### Aplicacao

```bash
kubectl apply -f k8s/secrets/dev/
```

Para producao, troque para:

```bash
kubectl apply -f k8s/secrets/prod/
```

## 4. Deployments

Cada microsservico deve ter seu proprio `Deployment`.

Pontos obrigatorios:

- usar a imagem publicada no ECR
- definir `resources.requests` e `resources.limits`
- declarar `readinessProbe` e `livenessProbe` sempre que possivel
- injetar variaveis por `env` ou `envFrom`
- apontar o `selector` para o `app` correto

### Imagem do ECR

Use o padrao:

```yaml
image: <account-id>.dkr.ecr.<region>.amazonaws.com/<image-name>:<tag>
```

### Porta por servico

| Servico | Porta |
| --- | --- |
| `auth-service` | `8001` |
| `flag-service` | `8002` |
| `targeting-service` | `8003` |
| `evaluation-service` | `8004` |
| `analytics-service` | `8005` |

### Variaveis por servico

#### `auth-service`

- `PORT`
- `DATABASE_URL` via Secret
- `MASTER_KEY` via Secret

#### `flag-service`

- `PORT`
- `DATABASE_URL` via Secret
- `AUTH_SERVICE_URL` via ConfigMap

#### `targeting-service`

- `PORT`
- `DATABASE_URL` via Secret
- `AUTH_SERVICE_URL` via ConfigMap

#### `evaluation-service`

- `PORT`
- `REDIS_URL` via ConfigMap
- `FLAG_SERVICE_URL` via ConfigMap
- `TARGETING_SERVICE_URL` via ConfigMap
- `AWS_REGION` via ConfigMap
- `AWS_SQS_URL` via ConfigMap
- `AWS_SQS_ENDPOINT_URL` via ConfigMap
- `SERVICE_API_KEY` via Secret

#### `analytics-service`

- `PORT`
- `AWS_REGION` via ConfigMap
- `AWS_SQS_URL` via ConfigMap
- `AWS_SQS_ENDPOINT_URL` via ConfigMap
- `AWS_DYNAMODB_TABLE` via ConfigMap
- `AWS_DYNAMODB_ENDPOINT_URL` via ConfigMap
- `AWS_ACCESS_KEY_ID` via Secret
- `AWS_SECRET_ACCESS_KEY` via Secret
- `AWS_SESSION_TOKEN` via Secret

### Exemplo de template de Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: auth-service
  namespace: tech-challenge-2
spec:
  replicas: 2
  selector:
    matchLabels:
      app: auth-service
  template:
    metadata:
      labels:
        app: auth-service
    spec:
      containers:
        - name: auth-service
          image: <account-id>.dkr.ecr.<region>.amazonaws.com/auth-service:<tag>
          ports:
            - containerPort: 8001
          env:
            - name: PORT
              value: "8001"
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: dev-auth-secrets
                  key: DATABASE_URL
            - name: MASTER_KEY
              valueFrom:
                secretKeyRef:
                  name: dev-auth-secrets
                  key: MASTER_KEY
          readinessProbe:
            httpGet:
              path: /health
              port: 8001
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /health
              port: 8001
            initialDelaySeconds: 15
            periodSeconds: 20
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 250m
              memory: 256Mi
```

### Boas praticas de recursos

Recomendacao base:

- Go services: requests menores, limits moderados
- Python services: requests um pouco maiores por causa da inicializacao
- worker (`analytics-service`): manter limites mais conservadores

## 5. Services

Cada Deployment deve ter um `Service` do tipo `ClusterIP`.

Isso permite acesso interno via DNS do Kubernetes, sem expor os pods diretamente.

### Exemplo

```yaml
apiVersion: v1
kind: Service
metadata:
  name: auth-service
  namespace: tech-challenge-2
spec:
  type: ClusterIP
  selector:
    app: auth-service
  ports:
    - port: 8001
      targetPort: 8001
```

### Observacao

O `analytics-service` tambem pode ter `Service`, mesmo sendo worker, para manter o health check padronizado.

## 6. Ingress

O `Ingress` deve ser o ponto de entrada externo da aplicacao.

Como regra pratica:

- `/auth` -> `auth-service`
- `/flags` -> `flag-service`
- `/rules` -> `targeting-service`
- `/evaluate` -> `evaluation-service`

O `analytics-service` normalmente nao precisa de exposicao publica, porque ele trabalha em background consumindo fila.

### Exemplo de roteamento

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: togglemaster-ingress
  namespace: tech-challenge-2
spec:
  rules:
    - http:
        paths:
          - path: /auth
            pathType: Prefix
            backend:
              service:
                name: auth-service
                port:
                  number: 8001
          - path: /flags
            pathType: Prefix
            backend:
              service:
                name: flag-service
                port:
                  number: 8002
          - path: /rules
            pathType: Prefix
            backend:
              service:
                name: targeting-service
                port:
                  number: 8003
          - path: /evaluate
            pathType: Prefix
            backend:
              service:
                name: evaluation-service
                port:
                  number: 8004
```

## 7. Ordem de aplicacao

A ordem abaixo evita erro por dependencia entre objetos:

1. Namespace
2. ConfigMaps
3. Secrets
4. Deployments
5. Services
6. Ingress

### Comandos

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmaps/
kubectl apply -f k8s/secrets/dev/
kubectl apply -f k8s/deployments/
kubectl apply -f k8s/services/
kubectl apply -f k8s/ingress.yaml
```

## 8. Validacao

Depois de aplicar, valide com:

```bash
kubectl get ns
kubectl get all -n tech-challenge-2
kubectl get ingress -n tech-challenge-2
kubectl describe pod -n tech-challenge-2
kubectl logs -n tech-challenge-2 deploy/auth-service
```

## 9. Checklist final

- Namespace criado
- Secrets em base64
- ConfigMaps com URLs internas corretas
- Imagens apontando para o ECR
- Requests e limits definidos em todos os Deployments
- Readiness e liveness probes configuradas
- Services do tipo `ClusterIP`
- Ingress com rotas publicas definidas

## 10. Observacao sobre separacao por namespace

Neste projeto, a estrategia recomendada e usar um namespace dedicado para toda a stack, porque os microsservicos precisam se comunicar entre si com menos complexidade.

Se no futuro for necessario isolar mais ainda por ambiente, a mesma estrutura pode ser replicada com namespaces diferentes, por exemplo:

- `tech-challenge-2-dev`
- `tech-challenge-2-prod`

