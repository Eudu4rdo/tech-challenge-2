# Provisionamento dos recursos AWS

Este guia mostra o passo a passo para criar os recursos usados pela stack no ambiente `us-east-1`.

## 0. O que voce precisa ter em maos

- `aws cli` configurado com um profile, por exemplo `meu-profile`
- `eksctl` instalado
- um cluster EKS ja criado
- a VPC do cluster
- as subnets privadas da VPC
- o security group dos nodes do EKS

Se ainda nao tiver o profile:

```bash
aws configure --profile meu-profile
```

## 1. Defina as variaveis

Use estes nomes como base:

```bash
REGION=us-east-1
PROFILE=meu-profile
RDS_DB_NAME_AUTH=auth_db
RDS_DB_NAME_FLAG=flag_db
RDS_DB_NAME_TARGETING=targeting_db
RDS_MASTER_USER=postgres
RDS_MASTER_PASSWORD=TroqueEstaSenha
REDIS_CLUSTER_ID=evaluation-redis
REDIS_SUBNET_GROUP=evaluation-redis-subnets
DYNAMODB_TABLE=ToggleMasterAnalytics
SQS_QUEUE_NAME=evaluation-events
```

Voce tambem vai precisar destes IDs:

```bash
VPC_ID=vpc-xxxxxxxx
PRIVATE_SUBNET_A=subnet-xxxxxxxx
PRIVATE_SUBNET_B=subnet-yyyyyyyy
EKS_NODE_SG=sg-xxxxxxxx
```

## 2. Criar o RDS

Os tres bancos sao independentes. A ordem sugerida e:

1. criar um DB subnet group
2. criar um security group para o banco
3. criar as tres instancias PostgreSQL
4. aguardar ficarem `available`

### 2.1 Criar o DB subnet group

Use as subnets privadas da VPC:

```bash
aws rds create-db-subnet-group \
  --db-subnet-group-name togglemaster-rds-subnets \
  --db-subnet-group-description "Subnets privadas para RDS do ToggleMaster" \
  --subnet-ids "$PRIVATE_SUBNET_A" "$PRIVATE_SUBNET_B" \
  --region "$REGION" \
  --profile "$PROFILE"
```

### 2.2 Criar o security group do RDS

```bash
aws ec2 create-security-group \
  --group-name togglemaster-rds-sg \
  --description "Acesso ao RDS apenas a partir dos nodes do EKS" \
  --vpc-id "$VPC_ID" \
  --region "$REGION" \
  --profile "$PROFILE"
```

Depois, libere a porta 5432 apenas para o security group dos nodes do EKS:

```bash
aws ec2 authorize-security-group-ingress \
  --group-id <rds-sg-id> \
  --protocol tcp \
  --port 5432 \
  --source-group "$EKS_NODE_SG" \
  --region "$REGION" \
  --profile "$PROFILE"
```

### 2.3 Criar as tres instancias PostgreSQL

Use `db.t3.micro`, `Single-AZ` e `no public access`:

```bash
aws rds create-db-instance \
  --db-instance-identifier auth-db \
  --db-instance-class db.t3.micro \
  --engine postgres \
  --allocated-storage 20 \
  --master-username "$RDS_MASTER_USER" \
  --master-user-password "$RDS_MASTER_PASSWORD" \
  --db-subnet-group-name togglemaster-rds-subnets \
  --vpc-security-group-ids <rds-sg-id> \
  --no-publicly-accessible \
  --backup-retention-period 1 \
  --region "$REGION" \
  --profile "$PROFILE"

aws rds create-db-instance \
  --db-instance-identifier flag-db \
  --db-instance-class db.t3.micro \
  --engine postgres \
  --allocated-storage 20 \
  --master-username "$RDS_MASTER_USER" \
  --master-user-password "$RDS_MASTER_PASSWORD" \
  --db-subnet-group-name togglemaster-rds-subnets \
  --vpc-security-group-ids <rds-sg-id> \
  --no-publicly-accessible \
  --backup-retention-period 1 \
  --region "$REGION" \
  --profile "$PROFILE"

aws rds create-db-instance \
  --db-instance-identifier targeting-db \
  --db-instance-class db.t3.micro \
  --engine postgres \
  --allocated-storage 20 \
  --master-username "$RDS_MASTER_USER" \
  --master-user-password "$RDS_MASTER_PASSWORD" \
  --db-subnet-group-name togglemaster-rds-subnets \
  --vpc-security-group-ids <rds-sg-id> \
  --no-publicly-accessible \
  --backup-retention-period 1 \
  --region "$REGION" \
  --profile "$PROFILE"
```

### 2.4 Confirmar os endpoints

```bash
aws rds describe-db-instances \
  --region "$REGION" \
  --profile "$PROFILE"
```

Anote os endpoints de:

- `auth-db`
- `flag-db`
- `targeting-db`

### 2.5 Como fica a string de conexao

```text
postgresql://USUARIO:SENHA@ENDPOINT:5432/NOME_DO_BANCO?sslmode=require
```

Exemplo:

```text
postgresql://postgres:TroqueEstaSenha@auth-db.xxxxx.us-east-1.rds.amazonaws.com:5432/auth_db?sslmode=require
```

## 3. Criar o ElastiCache Redis

### 3.1 Criar o cache subnet group

Use as mesmas subnets privadas:

```bash
aws elasticache create-cache-subnet-group \
  --cache-subnet-group-name "$REDIS_SUBNET_GROUP" \
  --cache-subnet-group-description "Subnets privadas para Redis do ToggleMaster" \
  --subnet-ids "$PRIVATE_SUBNET_A" "$PRIVATE_SUBNET_B" \
  --region "$REGION" \
  --profile "$PROFILE"
```

### 3.2 Criar o security group do Redis

```bash
aws ec2 create-security-group \
  --group-name togglemaster-redis-sg \
  --description "Acesso ao Redis apenas a partir dos nodes do EKS" \
  --vpc-id "$VPC_ID" \
  --region "$REGION" \
  --profile "$PROFILE"
```

Depois, libere a porta 6379 apenas para o security group dos nodes do EKS:

```bash
aws ec2 authorize-security-group-ingress \
  --group-id <redis-sg-id> \
  --protocol tcp \
  --port 6379 \
  --source-group "$EKS_NODE_SG" \
  --region "$REGION" \
  --profile "$PROFILE"
```

### 3.3 Criar o cluster Redis

Use um node pequeno para reduzir custo:

```bash
aws elasticache create-cache-cluster \
  --cache-cluster-id "$REDIS_CLUSTER_ID" \
  --engine redis \
  --cache-node-type cache.t3.micro \
  --num-cache-nodes 1 \
  --cache-subnet-group-name "$REDIS_SUBNET_GROUP" \
  --security-group-ids <redis-sg-id> \
  --port 6379 \
  --region "$REGION" \
  --profile "$PROFILE"
```

### 3.4 Confirmar o endpoint

```bash
aws elasticache describe-cache-clusters \
  --cache-cluster-id "$REDIS_CLUSTER_ID" \
  --show-cache-node-info \
  --region "$REGION" \
  --profile "$PROFILE"
```

### 3.5 Como fica a URL

Sem senha:

```text
redis://evaluation-redis.xxxxx.cache.amazonaws.com:6379
```

Com senha:

```text
rediss://:SENHA_DO_REDIS@evaluation-redis.xxxxx.cache.amazonaws.com:6379/0
```

## 4. Criar a tabela DynamoDB

O `analytics-service` usa a chave primaria `event_id`.

### 4.1 Criar a tabela

```bash
aws dynamodb create-table \
  --table-name "$DYNAMODB_TABLE" \
  --attribute-definitions AttributeName=event_id,AttributeType=S \
  --key-schema AttributeName=event_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --table-class STANDARD \
  --region "$REGION" \
  --profile "$PROFILE"
```

### 4.2 Confirmar que a tabela ficou ativa

```bash
aws dynamodb describe-table \
  --table-name "$DYNAMODB_TABLE" \
  --region "$REGION" \
  --profile "$PROFILE"
```

### 4.3 Nome que vai no ConfigMap

```text
ToggleMasterAnalytics
```

## 5. Criar a fila SQS

### 5.1 Criar a fila Standard

Se voce nao informar `FifoQueue`, o SQS cria uma fila Standard:

```bash
aws sqs create-queue \
  --queue-name "$SQS_QUEUE_NAME" \
  --region "$REGION" \
  --profile "$PROFILE"
```

### 5.2 Obter a URL da fila

```bash
aws sqs get-queue-url \
  --queue-name "$SQS_QUEUE_NAME" \
  --region "$REGION" \
  --profile "$PROFILE"
```

### 5.3 URL esperada

```text
https://sqs.us-east-1.amazonaws.com/123456789012/evaluation-events
```

## 6. Configurar IRSA

Use IRSA para evitar guardar credenciais AWS em `Secret`.

### 6.1 Associar o OIDC ao cluster

```bash
eksctl utils associate-iam-oidc-provider \
  --cluster tech-challenge-2 \
  --region "$REGION" \
  --approve \
  --profile "$PROFILE"
```

### 6.2 Criar as roles e service accounts

Crie uma policy para enviar mensagens ao SQS e outra para ler o SQS e gravar no DynamoDB. Depois associe as service accounts:

```bash
eksctl create iamserviceaccount \
  --cluster tech-challenge-2 \
  --namespace tech-challenge-2 \
  --name evaluation-service-sa \
  --attach-policy-arn arn:aws:iam::<account-id>:policy/ToggleMasterEvaluationSqsPolicy \
  --approve \
  --profile "$PROFILE"

eksctl create iamserviceaccount \
  --cluster tech-challenge-2 \
  --namespace tech-challenge-2 \
  --name analytics-service-sa \
  --attach-policy-arn arn:aws:iam::<account-id>:policy/ToggleMasterAnalyticsPolicy \
  --approve \
  --profile "$PROFILE"
```

## 7. O que vai em ConfigMap e Secret

### ConfigMap

- `AWS_REGION`
- `AWS_SQS_URL`
- `AWS_DYNAMODB_TABLE`
- `AUTH_SERVICE_URL`
- `FLAG_SERVICE_URL`
- `TARGETING_SERVICE_URL`
- `REDIS_URL` se nao tiver senha

### Secret

- `DATABASE_URL` dos 3 bancos
- `MASTER_KEY`
- `SERVICE_API_KEY`
- `REDIS_URL` se houver senha

### Exemplo de `DATABASE_URL`

```text
postgresql://auth_user:SenhaForte@auth-db.xxxxx.us-east-1.rds.amazonaws.com:5432/auth_db?sslmode=require
```

## 8. Checklist final

- RDS criado para `auth-service`, `flag-service` e `targeting-service`
- ElastiCache criado para `evaluation-service`
- DynamoDB criado para `analytics-service`
- SQS criado para `evaluation-service` e `analytics-service`
- endpoints anotados
- `ConfigMap` e `Secret` planejados
- IRSA configurado para os servicos que falam com AWS

## 9. Validacao rapida

```bash
aws rds describe-db-instances --region "$REGION" --profile "$PROFILE"
aws elasticache describe-cache-clusters --region "$REGION" --profile "$PROFILE"
aws dynamodb list-tables --region "$REGION" --profile "$PROFILE"
aws sqs list-queues --region "$REGION" --profile "$PROFILE"
```

## 10. Observacao final

Depois de provisionar estes recursos, o proximo passo e atualizar os manifests do Kubernetes com os endpoints reais e aplicar os `Deployments`.
