# Tutorial curto: subir a stack na AWS

Este guia segue uma ordem simples de execucao para subir a stack completa do projeto:

- `auth-service`
- `flag-service`
- `targeting-service`
- `evaluation-service`
- `analytics-service`

A ideia e deixar o fluxo fechado do inicio ao fim:

1. autenticar a AWS com um profile que nao seja o `default`
2. criar o cluster EKS
3. criar os repositorios no ECR e subir as imagens
4. criar RDS, ElastiCache, DynamoDB e SQS
5. configurar `ConfigMap`, `Secret` e IRSA
6. aplicar os manifests no Kubernetes
7. habilitar KEDA para o `analytics-service`

## 1. Pre-requisitos

Antes de comecar, tenha:

- AWS CLI configurado
- `kubectl` instalado
- `eksctl` instalado
- uma conta AWS com permissao para criar EKS, RDS, ElastiCache, DynamoDB, SQS, ECR, IAM e Load Balancer
- um profile AWS diferente do `default`, por exemplo `meu-profile`

Se ainda nao configurou esse profile:

```bash
aws configure --profile meu-profile
```

Teste a autenticacao com:

```bash
aws sts get-caller-identity --profile meu-profile
```

## 2. Criar o cluster EKS

Use um cluster simples com node group gerenciado:

```bash
eksctl create cluster \
  --name tech-challenge-2 \
  --region us-east-1 \
  --profile meu-profile \
  --managed \
  --nodes 2 \
  --node-type t3.micro
```

`t3.micro` e uma opcao compativel com Free Tier para varias contas AWS, mas o plano de controle do EKS continua fora do Free Tier.

Valide o acesso:

```bash
kubectl get nodes
```

## 3. Criar o ECR e subir as imagens

Crie um repositorio para cada servico:

```bash
aws ecr create-repository --repository-name auth-service --region us-east-1 --profile meu-profile
aws ecr create-repository --repository-name flag-service --region us-east-1 --profile meu-profile
aws ecr create-repository --repository-name targeting-service --region us-east-1 --profile meu-profile
aws ecr create-repository --repository-name evaluation-service --region us-east-1 --profile meu-profile
aws ecr create-repository --repository-name analytics-service --region us-east-1 --profile meu-profile
```

Autentique o Docker no ECR:

```bash
aws ecr get-login-password --region us-east-1 --profile meu-profile | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com
```

Faça build, tag e push:

```bash
docker build -t auth-service ./auth-service
docker tag auth-service:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/auth-service:latest
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/auth-service:latest

docker build -t flag-service ./flag-service
docker tag flag-service:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/flag-service:latest
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/flag-service:latest

docker build -t targeting-service ./targeting-service
docker tag targeting-service:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/targeting-service:latest
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/targeting-service:latest

docker build -t evaluation-service ./evaluation-service
docker tag evaluation-service:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/evaluation-service:latest
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/evaluation-service:latest

docker build -t analytics-service ./analytics-service
docker tag analytics-service:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/analytics-service:latest
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/analytics-service:latest
```

## 4. Criar os recursos da AWS

Crie os recursos nesta ordem:

1. 3 bancos RDS PostgreSQL
2. 1 cluster ElastiCache for Redis
3. 1 tabela DynamoDB
4. 1 fila SQS Standard

### Mapeamento por servico

| Recurso | Servico |
| --- | --- |
| RDS PostgreSQL 1 | `auth-service` |
| RDS PostgreSQL 2 | `flag-service` |
| RDS PostgreSQL 3 | `targeting-service` |
| ElastiCache Redis | `evaluation-service` |
| DynamoDB | `analytics-service` |
| SQS Standard | `evaluation-service` e `analytics-service` |

### Sugestao de nomes

- `auth-db`
- `flag-db`
- `targeting-db`
- `evaluation-redis`
- `togglemaster-analytics`
- `evaluation-events`

Use subnets privadas e security groups que liberem acesso apenas a partir dos nodes do EKS.

## 5. Como salvar as strings de conexao

Regra simples:

- `Secret` para credenciais, senhas, tokens e strings com usuario e senha
- `ConfigMap` para URLs, nomes de recursos e valores nao sensiveis

### Exemplo de `Secret`

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: auth-secrets
  namespace: tech-challenge-2
type: Opaque
stringData:
  DATABASE_URL: postgresql://auth_user:SenhaForte@auth-db.xxxxx.us-east-1.rds.amazonaws.com:5432/auth_db?sslmode=require
  MASTER_KEY: admin-secreto-123
```

### Exemplo de `ConfigMap`

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
  REDIS_URL: redis://evaluation-redis.xxxxx.cache.amazonaws.com:6379
  AWS_SQS_URL: https://sqs.us-east-1.amazonaws.com/123456789012/evaluation-events
  AWS_DYNAMODB_TABLE: togglemaster-analytics
```

### Como fica por servico

| Servico | Variavel | Onde guardar | Exemplo |
| --- | --- | --- | --- |
| `auth-service` | `DATABASE_URL` | `Secret` | `postgresql://auth_user:Senha@auth-db.xxxxx.rds.amazonaws.com:5432/auth_db?sslmode=require` |
| `auth-service` | `MASTER_KEY` | `Secret` | `admin-secreto-123` |
| `flag-service` | `DATABASE_URL` | `Secret` | `postgresql://flag_user:Senha@flag-db.xxxxx.rds.amazonaws.com:5432/flag_db?sslmode=require` |
| `targeting-service` | `DATABASE_URL` | `Secret` | `postgresql://target_user:Senha@targeting-db.xxxxx.rds.amazonaws.com:5432/targeting_db?sslmode=require` |
| `evaluation-service` | `REDIS_URL` | `ConfigMap` | `redis://evaluation-redis.xxxxx.cache.amazonaws.com:6379` |
| `evaluation-service` | `AWS_SQS_URL` | `ConfigMap` | `https://sqs.us-east-1.amazonaws.com/123456789012/evaluation-events` |
| `evaluation-service` | `SERVICE_API_KEY` | `Secret` | chave gerada pelo `auth-service` |
| `analytics-service` | `AWS_SQS_URL` | `ConfigMap` | `https://sqs.us-east-1.amazonaws.com/123456789012/evaluation-events` |
| `analytics-service` | `AWS_DYNAMODB_TABLE` | `ConfigMap` | `togglemaster-analytics` |

### Se usar Redis com senha

Se o ElastiCache for configurado com autenticacao, a URL pode ir para `Secret`:

```text
rediss://:SENHA_DO_REDIS@evaluation-redis.xxxxx.cache.amazonaws.com:6379/0
```

## 6. Configurar IRSA

Com IRSA, o pod recebe credenciais temporarias via service account anotada. Isso evita guardar `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` e `AWS_SESSION_TOKEN` em `Secret`.

### Servicos que usam IRSA

- `evaluation-service`, para publicar mensagens no SQS
- `analytics-service`, para consumir SQS e gravar no DynamoDB

### Associar o OIDC ao cluster

```bash
eksctl utils associate-iam-oidc-provider \
  --cluster tech-challenge-2 \
  --region us-east-1 \
  --approve \
  --profile meu-profile
```

### Criar as service accounts com role

```bash
eksctl create iamserviceaccount \
  --cluster tech-challenge-2 \
  --namespace tech-challenge-2 \
  --name evaluation-service-sa \
  --attach-policy-arn arn:aws:iam::<account-id>:policy/ToggleMasterEvaluationSqsPolicy \
  --approve \
  --profile meu-profile

eksctl create iamserviceaccount \
  --cluster tech-challenge-2 \
  --namespace tech-challenge-2 \
  --name analytics-service-sa \
  --attach-policy-arn arn:aws:iam::<account-id>:policy/ToggleMasterAnalyticsPolicy \
  --approve \
  --profile meu-profile
```

### Permissoes minimas

- `evaluation-service`: `sqs:SendMessage`
- `analytics-service`: `sqs:ReceiveMessage`, `sqs:DeleteMessage` e `dynamodb:PutItem`

### O que muda nos manifests

Os `Deployment`s desses servicos devem usar `serviceAccountName`:

```yaml
spec:
  serviceAccountName: evaluation-service-sa
```

Com IRSA, remova as variaveis AWS estaticas dos `Secrets` e dos `Deployment`s.

## 7. Criar o namespace

```bash
kubectl apply -f k8s/namespace.yaml
```

## 8. Aplicar ConfigMaps e Secrets

Depois de criar o namespace, aplique os manifestos de configuracao:

```bash
kubectl apply -f k8s/configmaps/
kubectl apply -f k8s/secrets/
```

Observacoes:

- os `Secrets` precisam estar em base64 se voce usar `data`
- se voce usar `stringData`, o Kubernetes converte na aplicacao
- com IRSA, as credenciais AWS do `analytics-service` nao precisam estar em `Secret`

## 9. Aplicar os Deployments e Services

Os 5 workloads do projeto sao:

| Servico | Porta |
| --- | --- |
| `auth-service` | `8001` |
| `flag-service` | `8002` |
| `targeting-service` | `8003` |
| `evaluation-service` | `8004` |
| `analytics-service` | `8005` |

Antes de aplicar, ajuste os manifests para apontar para o ECR.

Depois aplique:

```bash
kubectl apply -f k8s/deployments/
kubectl apply -f k8s/services/
```

## 10. Configurar KEDA

Para a conta pessoal, a recomendacao e usar KEDA no `analytics-service` em vez de HPA por CPU.

### Fluxo simples

1. instalar o KEDA no cluster
2. criar um `ScaledObject` para o `analytics-service`
3. configurar o scaler para monitorar a fila SQS

### Ideia do ScaledObject

O `ScaledObject` deve observar a fila e escalar de `0` ate `N` replicas conforme o `queueDepth`.

Exemplo de intencao:

```yaml
spec:
  scaleTargetRef:
    name: analytics-service
  minReplicaCount: 0
  maxReplicaCount: 5
```

## 11. Expor a aplicacao

O `Ingress` do projeto roteia os caminhos principais:

- `/auth`
- `/flags`
- `/rules`
- `/evaluate`

Aplique com:

```bash
kubectl apply -f k8s/ingress.yaml
```

## 12. Validar tudo

```bash
kubectl get all -n tech-challenge-2
kubectl get ingress -n tech-challenge-2
kubectl logs -n tech-challenge-2 deploy/evaluation-service
kubectl describe pod -n tech-challenge-2
```

## 13. Ordem recomendada

1. criar o cluster
2. criar os repositrios no ECR
3. subir as imagens no ECR
4. criar os 3 RDS PostgreSQL
5. criar o ElastiCache Redis
6. criar a tabela DynamoDB
7. criar a fila SQS
8. associar o OIDC e configurar IRSA
9. criar o namespace
10. aplicar `ConfigMaps`
11. aplicar `Secrets`
12. aplicar `Deployments`
13. aplicar `Services`
14. aplicar o `ScaledObject` do KEDA
15. aplicar `Ingress`

## 14. Observacao final

O `analytics-service` trabalha em background e depende de fila e banco externos, entao ele pode precisar de ajustes extras na AWS.

Se quiser, o proximo passo natural e eu transformar este guia em uma versao ainda mais pratica, com comandos separados por bloco: `infra`, `images` e `kubernetes`.
